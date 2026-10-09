#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
mcd-coupon-butler / 麦麦羊毛管家 —— 零依赖命令行工具

只用 Python 标准库实现麦当劳 MCP（Streamable HTTP）的最小客户端，
把「券包体检」「积分体检」两件事做成一键可跑的本地脚本。

用法:
    export MCD_MCP_TOKEN="你的 MCP Token"

    python3 scripts/mcd_wool.py doctor            # 连通性自检 + 列出可用工具
    python3 scripts/mcd_wool.py tools             # 打印工具清单
    python3 scripts/mcd_wool.py coupons           # 券包体检
    python3 scripts/mcd_wool.py points            # 积分体检
    python3 scripts/mcd_wool.py bind              # 一键领取麦麦省全部券
    python3 scripts/mcd_wool.py report            # 券包 + 积分 合并体检报告（Markdown）
    python3 scripts/mcd_wool.py mall              # 麦麦商城商品列表
    python3 scripts/mcd_wool.py call <tool> '{...}'   # 直接调用任意 Tool

Token 读取优先级:
    1) --token 参数
    2) 环境变量 MCD_MCP_TOKEN
    3) 本地文件 ~/.mcd-coupon-butler/MCD_MCP_TOKEN
"""

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone, timedelta

DEFAULT_URL = "https://mcp.mcd.cn"
TOKEN_FILE = os.path.expanduser("~/.mcd-coupon-butler/MCD_MCP_TOKEN")
CLIENT_NAME = "mcd-coupon-butler"
CLIENT_VERSION = "1.0.0"
PROTOCOL_VERSION = "2025-06-18"
CST = timezone(timedelta(hours=8))


class McpError(RuntimeError):
    """MCP 调用或传输层错误。"""


class McdMcpClient:
    """麦当劳 MCP 的极简 Streamable HTTP 客户端（仅标准库）。"""

    def __init__(self, url=DEFAULT_URL, token=None, timeout=30):
        if not token:
            raise McpError("缺少 MCP Token，请设置环境变量 MCD_MCP_TOKEN 或使用 --token。")
        self.url = url.rstrip("/") or DEFAULT_URL
        self.token = token
        self.timeout = timeout
        self.session_id = None
        self._req_id = 0
        self._initialized = False

    # ---------- 传输层 ----------

    def _post(self, payload, expect_response=True):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(self.url, data=body, method="POST")
        req.add_header("Content-Type", "application/json")
        # Streamable HTTP 网关要求同时声明接受 SSE，否则可能回 400
        req.add_header("Accept", "application/json, text/event-stream")
        req.add_header("Authorization", "Bearer " + self.token)
        req.add_header("User-Agent", "%s/%s" % (CLIENT_NAME, CLIENT_VERSION))
        if self.session_id:
            req.add_header("Mcp-Session-Id", self.session_id)

        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                sid = resp.headers.get("Mcp-Session-Id")
                if sid:
                    self.session_id = sid
                ctype = resp.headers.get("Content-Type", "") or ""
                raw = resp.read().decode("utf-8", "replace")
                status = resp.getcode()
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace") if exc.fp else ""
            raise McpError(_explain_http_error(exc.code, detail)) from None
        except urllib.error.URLError as exc:
            raise McpError("网络不可达：%s" % exc.reason) from None

        if not expect_response or status == 202 or not raw.strip():
            return None
        return _parse_body(raw, ctype)

    # ---------- 协议层 ----------

    def initialize(self):
        resp = self._post({
            "jsonrpc": "2.0",
            "id": self._next_id(),
            "method": "initialize",
            "params": {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": {"name": CLIENT_NAME, "version": CLIENT_VERSION},
            },
        })
        # 握手完成后按协议补发 initialized 通知（通知无响应体）
        self._post(
            {"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}},
            expect_response=False,
        )
        self._initialized = True
        return resp

    def list_tools(self):
        self._ensure_ready()
        resp = self._post({"jsonrpc": "2.0", "id": self._next_id(), "method": "tools/list", "params": {}})
        return _result_of(resp).get("tools", [])

    def call_tool(self, name, arguments=None):
        self._ensure_ready()
        resp = self._post({
            "jsonrpc": "2.0",
            "id": self._next_id(),
            "method": "tools/call",
            "params": {"name": name, "arguments": arguments or {}},
        })
        return _result_of(resp)

    # ---------- 内部 ----------

    def _next_id(self):
        self._req_id += 1
        return self._req_id

    def _ensure_ready(self):
        if not self._initialized:
            self.initialize()


# ---------- 响应解析 ----------


def _parse_body(raw, content_type):
    """兼容两种返回：纯 JSON，或 SSE（text/event-stream）。"""
    if "text/event-stream" in content_type or raw.lstrip().startswith(("event:", "data:", "id:")):
        return _parse_sse(raw)
    try:
        return json.loads(raw)
    except ValueError:
        raise McpError("无法解析服务端返回（既不是 JSON 也不是 SSE）：%s" % raw[:200]) from None


def _parse_sse(raw):
    """从 SSE 流中取出最后一个完整的 JSON-RPC 消息。"""
    events, buf = [], []
    for line in raw.splitlines():
        if line.startswith("data:"):
            buf.append(line[5:].lstrip())
        elif not line.strip() and buf:
            events.append("\n".join(buf))
            buf = []
    if buf:
        events.append("\n".join(buf))

    last = None
    for chunk in events:
        try:
            last = json.loads(chunk)
        except ValueError:
            continue
    if last is None:
        raise McpError("SSE 流中未找到可解析的 JSON-RPC 消息：%s" % raw[:200])
    return last


def _result_of(resp):
    if resp is None:
        raise McpError("服务端未返回内容。")
    if isinstance(resp, dict) and resp.get("error"):
        err = resp["error"]
        raise McpError("MCP 错误 %s：%s" % (err.get("code"), err.get("message")))
    if not isinstance(resp, dict) or "result" not in resp:
        raise McpError("返回结构异常：%s" % json.dumps(resp, ensure_ascii=False)[:200])
    return resp["result"]


def _explain_http_error(code, detail):
    hints = {
        400: "请求被网关拒绝，可能是 Accept 头缺失或 JSON 格式问题。",
        401: "MCP Token 无效、已过期或未提供，请重新申请或检查 Authorization。",
        403: "无权限访问该资源，请确认 Token 对应的账号状态。",
        404: "接口地址不存在，请确认 URL 是否为 https://mcp.mcd.cn 。",
        429: "触发限流（单 Token 上限 600 次/分钟），请降低调用频率后重试。",
    }
    hint = hints.get(code, "未知错误。")
    extra = ("｜服务端返回：%s" % detail[:200]) if detail else ""
    return "HTTP %s：%s%s" % (code, hint, extra)


def payload_of(result):
    """tools/call 的 result.content 里通常是一段 JSON 字符串，这里做统一解包。"""
    if result is None:
        return None
    if isinstance(result, dict) and "structuredContent" in result:
        return result["structuredContent"]

    content = result.get("content") if isinstance(result, dict) else None
    if not isinstance(content, list):
        return result

    texts = [c.get("text", "") for c in content if isinstance(c, dict) and c.get("type") == "text"]
    if not texts:
        return result
    joined = "\n".join(texts)
    try:
        return json.loads(joined)
    except ValueError:
        return joined


# ---------- 工具调用封装 ----------


def safe_call(client, tool, arguments=None):
    """调用失败时不中断整份报告，返回 (ok, payload_or_error)。"""
    try:
        return True, payload_of(client.call_tool(tool, arguments))
    except McpError as exc:
        return False, str(exc)


def fetch_now(client):
    ok, data = safe_call(client, "now-time-info")
    if ok and isinstance(data, dict):
        for key in ("time", "currentTime", "now", "datetime", "dateTime"):
            if data.get(key):
                return str(data[key])
    return datetime.now(CST).strftime("%Y-%m-%d %H:%M:%S")


def fetch_coupons(client):
    ok, data = safe_call(client, "query-my-coupons")
    if not ok:
        return None, data
    return _find_list(data, ("coupons", "couponList", "list", "data", "items")), None


def fetch_account(client):
    ok, data = safe_call(client, "query-my-account")
    if not ok:
        return None, data
    return data, None


def _find_list(node, keys, depth=0):
    """在嵌套结构里找出最可能承载"券列表"的那个数组。"""
    if depth > 4 or node is None:
        return None
    if isinstance(node, list):
        return node
    if isinstance(node, dict):
        for key in keys:
            if isinstance(node.get(key), list):
                return node[key]
        for value in node.values():
            found = _find_list(value, keys, depth + 1)
            if found is not None:
                return found
    return None


# ---------- 字段读取（防御式，字段名缺失就返回 None） ----------


def pick(node, *names):
    if not isinstance(node, dict):
        return None
    for name in names:
        if node.get(name) not in (None, "", []):
            return node[name]
    return None


def as_int(value):
    if value is None:
        return None
    try:
        return int(float(str(value).strip()))
    except (TypeError, ValueError):
        return None


def parse_date(value):
    """尽量把各种日期写法解析成标准日期串。"""
    if value in (None, ""):
        return None
    text = str(value).strip()
    if text.isdigit() and len(text) >= 10:
        ts = int(text[:10])
        if ts > 10 ** 9:
            return datetime.fromtimestamp(ts, CST).strftime("%Y-%m-%d")
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d", "%Y/%m/%d", "%Y.%m.%d"):
        try:
            return datetime.strptime(text[:19], fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return text[:10] if len(text) >= 10 else text


def days_left(expiry, now_text):
    if not expiry:
        return None
    try:
        end = datetime.strptime(expiry, "%Y-%m-%d")
    except ValueError:
        return None
    try:
        start = datetime.strptime(now_text[:10], "%Y-%m-%d")
    except ValueError:
        start = datetime.now(CST).replace(tzinfo=None)
    return (end - start).days


# ---------- 渲染 ----------


def render_coupons(coupons, now_text, limit=40):
    lines = []
    if coupons is None:
        return "> 未能获取券列表。\n"
    if not coupons:
        return "> 当前券包是空的，先去「一键领券」薅一波吧。\n"

    rows = []
    for c in coupons:
        expiry = parse_date(pick(c, "expireTime", "expireDate", "endTime", "validEndTime", "endDate", "expireAt"))
        rows.append({
            "name": pick(c, "couponName", "name", "title", "couponTitle") or "未命名券",
            "value": pick(c, "discountDesc", "couponDesc", "description", "subTitle", "benefit") or "-",
            "expiry": expiry or "-",
            "left": days_left(expiry, now_text) if expiry else None,
        })

    rows.sort(key=lambda r: (r["left"] is None, r["left"] if r["left"] is not None else 0))

    urgent = [r for r in rows if r["left"] is not None and r["left"] <= 3]
    if urgent:
        lines.append("### 🚨 临期告急（≤3 天）")
        lines.append("| 券名 | 权益 | 到期日 | 剩余 |")
        lines.append("|---|---|---|---|")
        for r in urgent:
            left = "今天到期" if r["left"] == 0 else "%d 天" % r["left"]
            lines.append("| %s | %s | %s | **%s** |" % (r["name"], r["value"], r["expiry"], left))
        lines.append("")

    lines.append("### 📅 有效券（按到期排序）")
    lines.append("| 券名 | 权益 | 到期日 | 剩余 |")
    lines.append("|---|---|---|---|")
    for r in rows[:limit]:
        left = "-" if r["left"] is None else ("今天到期" if r["left"] == 0 else "%d 天" % r["left"])
        lines.append("| %s | %s | %s | %s |" % (r["name"], r["value"], r["expiry"], left))
    if len(rows) > limit:
        lines.append("\n> 仅展示前 %d 张，共 %d 张。" % (limit, len(rows)))
    return "\n".join(lines) + "\n"


def render_points(account):
    if not account:
        return "> 未能获取积分信息。\n"
    if isinstance(account, str):
        return "```json\n%s\n```\n" % account

    available = as_int(pick(account, "availablePoints", "usablePoints", "points", "availableScore", "score"))
    total = as_int(pick(account, "totalPoints", "accumulatePoints", "totalScore"))
    frozen = as_int(pick(account, "frozenPoints", "freezePoints", "frozenScore"))
    expiring = as_int(pick(account, "expiringPoints", "expirePoints", "expiringScore", "willExpirePoints"))

    if all(v is None for v in (available, total, frozen, expiring)):
        return "```json\n%s\n```\n" % json.dumps(account, ensure_ascii=False, indent=2)

    def fmt(v):
        return "未返回" if v is None else "%d 积分" % v

    lines = ["| 项目 | 数值 |", "|---|---|",
             "| 可用积分 | **%s** |" % fmt(available),
             "| 即将过期 | %s |" % fmt(expiring),
             "| 冻结积分 | %s |" % fmt(frozen),
             "| 累计积分 | %s |" % fmt(total)]
    if expiring:
        lines.append("\n> ⚠️ 有 %d 积分即将过期，建议尽快兑换或抽奖消化。" % expiring)
    return "\n".join(lines) + "\n"


# ---------- 命令 ----------


def cmd_doctor(client, _args):
    resp = client.initialize()
    server = ""
    if isinstance(resp, dict) and isinstance(resp.get("result"), dict):
        info = resp["result"].get("serverInfo") or {}
        server = "（服务端：%s %s）" % (info.get("name", "?"), info.get("version", "?"))
    tools = client.list_tools()
    print("✅ MCP 连接正常%s" % server)
    print("   会话 ID：%s" % (client.session_id or "未下发"))
    print("   可用工具：%d 个" % len(tools))
    return 0


def cmd_tools(client, _args):
    for tool in client.list_tools():
        print("- %-26s %s" % (tool.get("name", "?"), (tool.get("description") or "").strip().splitlines()[0][:60]))
    return 0


def cmd_coupons(client, _args):
    now = fetch_now(client)
    coupons, err = fetch_coupons(client)
    if err:
        print("⚠️ 获取失败：%s" % err, file=sys.stderr)
    print(render_coupons(coupons, now))
    return 0


def cmd_points(client, _args):
    account, err = fetch_account(client)
    if err:
        print("⚠️ 获取失败：%s" % err, file=sys.stderr)
    print(render_points(account))
    return 0


def cmd_bind(client, _args):
    ok, data = safe_call(client, "auto-bind-coupons")
    if not ok:
        print("⚠️ 领券失败：%s" % data, file=sys.stderr)
        return 1
    print("✅ 已发起一键领券。")
    if data is not None:
        print("```json\n%s\n```" % json.dumps(data, ensure_ascii=False, indent=2))
    return 0


def cmd_mall(client, args):
    ok, data = safe_call(client, "mall-points-products", {"pageIndex": 1, "pageSize": args.size})
    if not ok:
        print("⚠️ 获取失败：%s" % data, file=sys.stderr)
        return 1
    print("```json\n%s\n```" % json.dumps(data, ensure_ascii=False, indent=2))
    return 0


def cmd_report(client, args):
    now = fetch_now(client)
    coupons, c_err = fetch_coupons(client)
    account, p_err = fetch_account(client)

    print("## 🍟 麦麦羊毛体检报告 · %s\n" % now[:10])
    print("### 一、券包\n")
    if c_err:
        print("> ⚠️ %s\n" % c_err)
    print(render_coupons(coupons, now))
    print("### 二、积分\n")
    if p_err:
        print("> ⚠️ %s\n" % p_err)
    print(render_points(account))

    if args.with_mall:
        print("### 三、麦麦商城\n")
        ok, data = safe_call(client, "mall-points-products", {"pageIndex": 1, "pageSize": 20})
        print("```json\n%s\n```\n" % json.dumps(data, ensure_ascii=False, indent=2) if ok else "> ⚠️ %s\n" % data)
    return 0


def cmd_call(client, args):
    if not args.tool:
        print("用法：mcd_wool.py call <tool> '{...}'", file=sys.stderr)
        return 2
    raw = args.arguments or "{}"
    try:
        arguments = json.loads(raw)
    except ValueError:
        print("参数必须是合法 JSON，例如 '{\"pageIndex\":1}'", file=sys.stderr)
        return 2
    result = client.call_tool(args.tool, arguments)
    print(json.dumps(payload_of(result), ensure_ascii=False, indent=2))
    return 0


COMMANDS = {
    "doctor": cmd_doctor,
    "tools": cmd_tools,
    "coupons": cmd_coupons,
    "points": cmd_points,
    "bind": cmd_bind,
    "mall": cmd_mall,
    "report": cmd_report,
    "call": cmd_call,
}


def resolve_token(cli_token=None):
    if cli_token:
        return cli_token.strip()
    env = os.environ.get("MCD_MCP_TOKEN", "").strip()
    if env:
        return env
    if os.path.exists(TOKEN_FILE):
        try:
            with open(TOKEN_FILE, "r", encoding="utf-8") as fh:
                return fh.read().strip()
        except OSError:
            return ""
    return ""


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="mcd_wool.py",
        description="麦麦羊毛管家 · 麦当劳 MCP 命令行工具",
    )
    parser.add_argument("command", choices=sorted(COMMANDS), help="要执行的操作")
    parser.add_argument("tool", nargs="?", help="call 命令要调用的 Tool 名称")
    parser.add_argument("arguments", nargs="?", help="call 命令的 JSON 参数")
    parser.add_argument("--token", help="MCP Token（默认读环境变量 MCD_MCP_TOKEN）")
    parser.add_argument("--url", default=os.environ.get("MCD_MCP_URL", DEFAULT_URL), help="MCP 接入地址")
    parser.add_argument("--size", type=int, default=20, help="mall 命令返回的商品数量")
    parser.add_argument("--with-mall", action="store_true", help="report 命令附带商城商品")
    args = parser.parse_args(argv)

    token = resolve_token(args.token)
    if not token:
        print("❌ 未找到 MCP Token。\n"
              "   1) 访问 https://open.mcd.cn/mcp 登录并申请 Token\n"
              "   2) export MCD_MCP_TOKEN=\"你的Token\"\n"
              "   3) 或写入 %s" % TOKEN_FILE, file=sys.stderr)
        return 2

    try:
        client = McdMcpClient(url=args.url, token=token)
        return COMMANDS[args.command](client, args)
    except McpError as exc:
        print("❌ %s" % exc, file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\n已中断。", file=sys.stderr)
        return 130


if __name__ == "__main__":
    sys.exit(main())
