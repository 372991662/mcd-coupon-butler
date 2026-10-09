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
    python3 scripts/mcd_wool.py available         # 可领取的麦麦省优惠券
    python3 scripts/mcd_wool.py points            # 积分体检
    python3 scripts/mcd_wool.py lottery           # 积分抽奖信息 + 奖池
    python3 scripts/mcd_wool.py campaign          # 麦麦活动雷达（上新/联名/限定）
    python3 scripts/mcd_wool.py badge             # 24节气徽章日历（无需 Token，纯本地推算）
    python3 scripts/mcd_wool.py bind              # 一键领取麦麦省全部券
    python3 scripts/mcd_wool.py report            # 券包+积分+活动+徽章+抽奖 合并体检报告
    python3 scripts/mcd_wool.py mall              # 麦麦商城商品列表
    python3 scripts/mcd_wool.py call <tool> '{...}'   # 直接调用任意 Tool

⚠️ 资产保护：凡**消耗积分/金钱**的操作（draw-lottery 抽奖、mall-create-order
   积分兑换、create-order / party-order-create 下单）默认一律被拦截、不会自动执行。
   确认代价后需显式加 --confirm 才会放行：
       python3 scripts/mcd_wool.py call mall-create-order '{...}' --confirm

Token 读取优先级:
    1) --token 参数
    2) 环境变量 MCD_MCP_TOKEN
    3) 本地文件 ~/.mcd-coupon-butler/MCD_MCP_TOKEN
"""

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from datetime import date, datetime, timezone, timedelta

# 节气徽章模块与本文件同目录；用脚本方式运行时 sys.path[0] 即为该目录
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from solar_terms import BADGE_RULES, badge_windows, current_badge
except ImportError:  # 理论上不会发生，兜底避免整体不可用
    badge_windows = current_badge = None
    BADGE_RULES = []

DEFAULT_URL = "https://mcp.mcd.cn"
TOKEN_FILE = os.path.expanduser("~/.mcd-coupon-butler/MCD_MCP_TOKEN")
CLIENT_NAME = "mcd-coupon-butler"
CLIENT_VERSION = "1.0.0"
PROTOCOL_VERSION = "2025-06-18"
CST = timezone(timedelta(hours=8))


class McpError(RuntimeError):
    """MCP 调用或传输层错误。"""


# ---------- 资产保护闸门（硬约束） ----------
# 会**消耗用户资产**（积分 / 金钱）的工具：默认一律禁止调用。
# 必须在用户明确确认后，显式追加 --confirm 才允许执行。
# 注意：本清单是"默认拒绝"策略 —— 宁可不执行，也不能自动替用户花掉积分。
GUARDED_TOOLS = {
    "draw-lottery": "消耗积分抽奖（单次 24 积分，扣减后不可撤销）",
    "mall-create-order": "消耗积分兑换商品（积分扣减后不可撤销）",
    "create-order": "提交订单，将产生实际支付",
    "party-order-create": "提交聚会订单，将产生实际支付",
}

# 不消耗任何资产、可安全自动执行的写操作（白名单）
ALLOWED_WRITE_TOOLS = {
    "auto-bind-coupons",  # 领券：只增不减，无成本
}


class GuardError(RuntimeError):
    """命中资产保护闸门：该操作会消耗积分/金钱，未经确认不得执行。

    刻意**不继承** McpError —— 因为 safe_call 会吞掉 McpError 并降级为普通错误，
    而本闸门必须一路抛出到入口、给出明确提示与退出码。
    """

    def __init__(self, tool):
        self.tool = tool
        self.reason = GUARDED_TOOLS.get(tool, "可能消耗用户积分/金钱")
        super().__init__(
            "⛔ 已拦截【%s】：%s。\n"
            "   本工具**不会自动执行**任何消耗积分的操作 —— 这是硬约束。\n"
            "   如果你（用户）确实要执行，请先确认下面的代价，再显式加 --confirm：\n"
            "\n"
            "     确认代价：%s\n"
            "     确认执行：python3 scripts/mcd_wool.py call %s '<参数>' --confirm\n"
            % (tool, self.reason, self.reason, tool)
        )


class McdMcpClient:
    """麦当劳 MCP 的极简 Streamable HTTP 客户端（仅标准库）。"""

    def __init__(self, url=DEFAULT_URL, token=None, timeout=30, allow_guarded=False):
        if not token:
            raise McpError("缺少 MCP Token，请设置环境变量 MCD_MCP_TOKEN 或使用 --token。")
        self.url = url.rstrip("/") or DEFAULT_URL
        self.token = token
        self.timeout = timeout
        # allow_guarded 必须由用户显式确认（CLI --confirm）后才会置为 True
        self.allow_guarded = allow_guarded
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
        # 资产保护闸门：消耗积分/金钱的工具，未经显式确认一律拒绝
        if name in GUARDED_TOOLS and not self.allow_guarded:
            raise GuardError(name)
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


def call_with_fallback(client, tool, arg_candidates):
    """按候选参数依次尝试调用。

    部分 Tool 的参数形态官方文档未完全固定（例如 activity 日历可能接受
    {year, month}、{date:"YYYY-MM"} 或空参数），这里做一次温和的降级探测，
    避免因参数猜错而整体失败。
    """
    last_err = "未提供可用参数"
    for args in arg_candidates:
        try:
            return True, payload_of(client.call_tool(tool, args)), args
        except McpError as exc:
            last_err = str(exc)
    return False, last_err, None


def fetch_campaign(client, now_text):
    """查询当月营销活动日历。"""
    year = now_text[:4]
    month = now_text[5:7]
    candidates = [
        {"year": as_int(year), "month": as_int(month)},
        {"date": "%s-%s" % (year, month)},
        {"year": year, "month": month},
        {},
    ]
    ok, data, _used = call_with_fallback(client, "campaign-calendar", candidates)
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


def unwrap(payload):
    """剥离麦当劳 MCP 的统一信封 {success, code, message, traceId, data}。

    绝大多数 Tool 把真正的业务数据放在 `data` 里；少数（如 available-coupons）
    `data` 本身就是数组。没有信封时原样返回，避免误伤。
    """
    if isinstance(payload, dict) and "data" in payload:
        if any(k in payload for k in ("success", "code", "traceId", "message", "datetime")):
            return payload["data"]
    return payload


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


_ORDER_TYPE_TEXT = {1: "到店", 2: "外送"}


def _coupon_channel(c):
    """从 tags / instructions / orderTypes 里拼出「到店 / 外送」渠道标签。"""
    labels = []
    for t in (c.get("tags") or []):
        if isinstance(t, dict) and t.get("label"):
            labels.append(str(t["label"]))
    for t in ((c.get("instructions") or {}).get("labels") or []):
        if isinstance(t, dict) and t.get("text"):
            labels.append(str(t["text"]))
    if not labels:
        ots = c.get("orderTypes")
        if not isinstance(ots, list):
            ots = [c.get("orderType")] if c.get("orderType") else []
        labels = [_ORDER_TYPE_TEXT[x] for x in ots if x in _ORDER_TYPE_TEXT]
    return "/".join(dict.fromkeys(labels)) or "-"


def _coupon_value(c, name=None):
    """券的权益文案。

    真实字段优先级：
      1) discountInfo.discountValue —— 「用券价格」，形如 {"discountDesc":"用券价格",
         "discountValue":"9.9","discountTypeText":"¥"}  → 展示为「用券价 ¥9.9」
      2) denomination / tenderAmount —— 单位为**分**，仅在有值时换算（2990 → ¥29.90）
      3) 现成文案兜底

    注意：不少券的 subtitle 与 title 完全一致（等于没给信息），这类要跳过。
    """
    di = c.get("discountInfo") if isinstance(c.get("discountInfo"), dict) else {}
    val = str(di.get("discountValue") or "").strip()
    unit = str(di.get("discountTypeText") or "").strip() or "¥"
    desc = str(di.get("discountDesc") or "").strip().replace("价格", "价")
    if val and val not in ("0", "0.0", "0.00", "-"):
        price = "%s%s" % (unit, val)
        return ("%s %s" % (desc, price)) if desc else price

    cents = as_int(pick(c, "denomination", "tenderAmount"))
    if cents:
        return "¥%.2f" % (cents / 100.0)
    for key in ("reducePriceText", "subtitle", "subTitle",
                "couponDesc", "description", "benefit"):
        text = c.get(key)
        if text and str(text).strip() and str(text).strip() != name:
            return str(text).strip()
    return "-"


def _coupon_row(c, now_text):
    name = pick(c, "title", "couponName", "name", "couponTitle") or "未命名券"
    expiry = parse_date(pick(c, "tradeEndDateTime", "tradeEndDate", "expireTime", "expireDate",
                             "endTime", "validEndTime", "endDate", "expireAt"))
    return {
        "name": name,
        "value": _coupon_value(c, name),
        "channel": _coupon_channel(c),
        "status": pick(c, "couponStatus", "label"),
        "expiry": expiry or "-",
        "left": days_left(expiry, now_text) if expiry else None,
    }


def render_coupons(coupons, now_text, limit=40):
    lines = []
    if coupons is None:
        return "> 未能获取券列表。\n"
    if not coupons:
        return "> 当前券包是空的，先去「一键领券」薅一波吧。\n"

    rows = [_coupon_row(c, now_text) for c in coupons if isinstance(c, dict)]
    if not rows:
        return "> 券列表返回了数据，但结构无法识别。\n"

    # 「可领券」列表（available-coupons）结构更简单：无到期日、无渠道，
    # 只关心「能不能领」，此时渲染成紧凑清单比空表格更清楚。
    if all(r["expiry"] == "-" and r["channel"] == "-" for r in rows):
        lines.append("| 券名 | 状态 |")
        lines.append("|---|---|")
        for r in rows[:limit]:
            status = r["status"] or "-"
            mark = "✅" if str(status) in ("可领取", "CAN_GET") else status
            lines.append("| %s | %s |" % (r["name"], mark))
        if len(rows) > limit:
            lines.append("\n> 仅展示前 %d 张，共 %d 张。" % (limit, len(rows)))
        lines.append("\n> 💡 用 `bind` 命令可以把这些券一次性全领到券包里。")
        return "\n".join(lines) + "\n"

    # 有到期日的按剩余天数升序；无到期日的排最后，但仍参与展示
    rows.sort(key=lambda r: (r["left"] is None, r["left"] if r["left"] is not None else 0))

    urgent = [r for r in rows if r["left"] is not None and r["left"] <= 3]
    if urgent:
        lines.append("### 🚨 临期告急（≤3 天）")
        lines.append("| 券名 | 权益 | 渠道 | 到期日 | 剩余 |")
        lines.append("|---|---|---|---|---|")
        for r in urgent:
            left = "今天到期" if r["left"] == 0 else "%d 天" % r["left"]
            lines.append("| %s | %s | %s | %s | **%s** |" % (
                r["name"], r["value"], r["channel"], r["expiry"], left))
        lines.append("")

    lines.append("### 📅 券包明细（按到期排序）")
    lines.append("| 券名 | 权益 | 渠道 | 到期日 | 剩余 |")
    lines.append("|---|---|---|---|---|")
    for r in rows[:limit]:
        left = "-" if r["left"] is None else ("今天到期" if r["left"] == 0 else "%d 天" % r["left"])
        lines.append("| %s | %s | %s | %s | %s |" % (
            r["name"], r["value"], r["channel"], r["expiry"], left))
    if len(rows) > limit:
        lines.append("\n> 仅展示前 %d 张，共 %d 张。" % (limit, len(rows)))
    return "\n".join(lines) + "\n"


def render_points(account):
    if not account:
        return "> 未能获取积分信息。\n"
    if isinstance(account, str):
        return "```json\n%s\n```\n" % account

    body = unwrap(account)
    if not isinstance(body, dict):
        return "```json\n%s\n```\n" % json.dumps(account, ensure_ascii=False, indent=2)

    # 真实字段来自 query-my-account：availablePoint / accumulativePoint /
    # expiredPoint / usedPoint / currentMouthExpirePoint / nextMouthExpirePoint / frozenPoint
    available = as_int(pick(body, "availablePoint", "availablePoints", "usablePoints", "points", "score"))
    total = as_int(pick(body, "accumulativePoint", "accumulatePoints", "totalPoints", "totalScore"))
    frozen = as_int(pick(body, "frozenPoint", "frozenPoints", "freezePoints", "frozenScore"))
    used = as_int(pick(body, "usedPoint", "usedPoints", "usedScore"))
    expired = as_int(pick(body, "expiredPoint", "expiredPoints", "expiredScore"))
    this_month = as_int(pick(body, "currentMouthExpirePoint", "currentMonthExpirePoint"))
    next_month = as_int(pick(body, "nextMouthExpirePoint", "nextMonthExpirePoint"))

    if all(v is None for v in (available, total, frozen, used, expired, this_month, next_month)):
        return "```json\n%s\n```\n" % json.dumps(account, ensure_ascii=False, indent=2)

    def fmt(v, suffix=" 积分"):
        return "未返回" if v is None else ("%g%s" % (v, suffix) if isinstance(v, float) else "%d%s" % (v, suffix))

    lines = ["| 项目 | 数值 |", "|---|---|",
             "| 可用积分 | **%s** |" % fmt(available),
             "| 累计获得 | %s |" % fmt(total),
             "| 本月将过期 | %s |" % fmt(this_month),
             "| 下月将过期 | %s |" % fmt(next_month),
             "| 冻结中 | %s |" % fmt(frozen),
             "| 已使用 | %s |" % fmt(used),
             "| 已过期作废 | %s |" % fmt(expired)]

    warn = (this_month or 0) + (next_month or 0)
    if warn:
        lines.append("\n> ⚠️ 共 %d 积分即将过期，建议尽快到「积分抽奖」或「麦麦商城」消化。" % warn)
    if expired:
        lines.append("\n> 📉 已累计有 %d 积分作废 —— 这正是本工具想帮你避免的部分。" % expired)
    return "\n".join(lines) + "\n"


def render_badge(now_text, compact=False):
    """渲染「麦麦24节气」徽章日历。

    注意：麦当劳 MCP 未提供徽章查询接口，因此本模块**只推算领取时间窗口**，
    不声称能读出用户"已收集了哪些徽章"。收集进度仍需到麦当劳 App 徽章墙查看。
    """
    if current_badge is None:
        return "> 节气模块不可用。\n"

    today = date(*[int(x) for x in now_text[:10].split("-")])
    cur, nxt = current_badge(today)

    lines = []
    if cur:
        passed = (today - cur["start"]).days
        left = (cur["end"] - today).days
        lines.append("### 🏅 当前可领：**%s** 徽章" % cur["name"])
        lines.append("")
        lines.append("| 项目 | 内容 |")
        lines.append("|---|---|")
        lines.append("| 领取窗口 | %s ~ %s |" % (cur["start"], cur["end"]))
        lines.append("| 进度 | 已进行 %d 天 · **还剩 %d 天** |" % (passed, left))
        lines.append("| 领取条件 | %s |" % " → ".join(BADGE_RULES))
        lines.append("")
        if left <= 2:
            lines.append("> 🚨 **快到期了**，今天不下单这枚徽章就错过了。\n")
    else:
        lines.append("> 今天不在任何节气徽章窗口内（理论上不会发生，请检查日期）。\n")

    if nxt and not compact:
        start_in = (nxt["start"] - today).days
        lines.append("### ⏰ 下一个：%s 徽章" % nxt["name"])
        lines.append("")
        lines.append("窗口 %s ~ %s · 还有 **%d 天**开始" % (nxt["start"], nxt["end"], start_in))
        lines.append("")

    if not compact:
        lines.append("### 📅 %d 全年节气徽章日历" % today.year)
        lines.append("")
        lines.append("| 节气 | 领取窗口 | 天数 | 状态 |")
        lines.append("|---|---|---:|---|")
        for w in badge_windows(today.year):
            span = (w["end"] - w["start"]).days + 1
            if w["end"] < today:
                stage = "已结束"
            elif w["start"] > today:
                stage = "未开始"
            else:
                stage = "**🔥 进行中**"
            tail = "（跨年）" if w["cross_year"] else ""
            lines.append("| %s | %s ~ %s%s | %d | %s |" % (w["name"], w["start"], w["end"], tail, span, stage))
        lines.append("")
        lines.append("> ℹ️ 同系列另有两项机制：每周六 App【大抽奖】消耗 **24 积分**抽节气大奖；"
                     "限定期间 **100 积分**兑麦麦美食。")
        lines.append("> ℹ️ 麦当劳 MCP 暂无徽章查询接口，本表为**时间窗口推算**；"
                     "已收集哪些徽章请到麦当劳 App 徽章墙查看，具体以活动页说明为准。")
        lines.append("")

    return "\n".join(lines) + "\n"


def _collect_dict_lists(node, depth=0, acc=None):
    """把嵌套结构里所有"由字典组成的数组"都收集起来。

    活动日历可能按「进行中 / 往期 / 未来」分组返回，因此不能只取第一个数组。
    """
    if acc is None:
        acc = []
    if depth > 5 or node is None:
        return acc
    if isinstance(node, list):
        dict_items = [x for x in node if isinstance(x, dict)]
        if dict_items:
            acc.append(dict_items)
        else:
            for child in node:
                _collect_dict_lists(child, depth + 1, acc)
        return acc
    if isinstance(node, dict):
        for value in node.values():
            _collect_dict_lists(value, depth + 1, acc)
    return acc


def _activity_of(item):
    """从一条活动记录里抽出通用字段（字段名不确定，多候选尝试）。"""
    name = pick(item, "activityName", "campaignName", "name", "title", "activityTitle", "subject")
    desc = pick(item, "description", "desc", "summary", "activityDesc", "subTitle", "content", "remark")
    start = parse_date(pick(item, "startTime", "startDate", "beginTime", "beginDate", "startAt", "start", "from"))
    end = parse_date(pick(item, "endTime", "endDate", "finishTime", "expireTime", "endAt", "end", "to"))
    status = pick(item, "status", "statusDesc", "state", "activityStatus", "campaignStatus")
    return {
        "name": name or "未命名活动",
        "desc": desc or "-",
        "start": start,
        "end": end,
        "status": status,
    }


def _classify(act, today):
    """判断活动处于 进行中 / 即将开始 / 已结束。"""
    text = str(act.get("status") or "")
    if any(k in text for k in ("进行", "进行中", "上线", "在线", "ongoing", "active")):
        return "ongoing"
    if any(k in text for k in ("未开始", "即将", "预告", "upcoming", "soon")):
        return "upcoming"
    if any(k in text for k in ("结束", "已下线", "过期", "ended", "expired", "offline")):
        return "ended"

    start, end = act.get("start"), act.get("end")
    if start and end:
        if start <= today <= end:
            return "ongoing"
        return "upcoming" if start > today else "ended"
    if end:
        return "ended" if end < today else "ongoing"
    if start:
        return "upcoming" if start > today else "ongoing"
    return "ongoing"


def _span(act):
    if act.get("start") and act.get("end"):
        return "%s ~ %s" % (act["start"], act["end"])
    return act.get("end") or act.get("start") or "-"


def _event_of(event):
    """从 campaign-calendar 的一条 event 抽出展示信息。

    真实结构：event.articleDto.{title,content,highlights} 承载文案，
    event.activityTitle / activitySubTitle 常为空串，需以 articleDto 为主。
    """
    ad = event.get("articleDto") if isinstance(event.get("articleDto"), dict) else {}
    name = (ad.get("title") or event.get("activityTitle") or event.get("activitySubTitle") or "").strip()
    highlight = (ad.get("highlights") or "").strip()
    content = (ad.get("content") or event.get("activitySubTitle") or "").strip()
    desc = highlight or content or "-"
    desc = re.sub(r"\s+", " ", desc)
    if len(desc) > 60:
        desc = desc[:58] + "…"
    return {
        "name": name or "未命名活动",
        "desc": desc,
        "price": event.get("price") if str(event.get("price") or "0") not in ("0", "") else None,
        "price_suffix": event.get("priceSuffix") or "",
        "tag": (event.get("activityTag") or "").strip(),
        "jump": ad.get("appJumpUrl") or "",
        "code": event.get("activityCode") or "",
    }


def _campaign_from_daily(body, today):
    """按 dailyList（按日期分组，带 today 标记）分组。

    注意：activityStage 的语义并不可靠（今天的活动同样是 stage=3），
    因此一律以「日期与今天比较 + today 标记」作为分组依据。
    """
    daily = body.get("dailyList") if isinstance(body, dict) else None
    if not isinstance(daily, list):
        return None

    groups = {"today": [], "upcoming": [], "past": []}
    for day in daily:
        if not isinstance(day, dict):
            continue
        d = parse_date(day.get("date")) or str(day.get("date") or "")
        if day.get("today") or d == today:
            stage = "today"
        elif d and d > today:
            stage = "upcoming"
        else:
            stage = "past"
        for event in (day.get("events") or []):
            if not isinstance(event, dict):
                continue
            item = _event_of(event)
            item["date"] = d
            groups[stage].append(item)

    # 同一活动可能在多天重复出现（跨天活动），按名称去重并保留最早日期
    for key in groups:
        seen, deduped = set(), []
        for item in sorted(groups[key], key=lambda x: x["date"] or "9999"):
            if item["name"] in seen:
                continue
            seen.add(item["name"])
            deduped.append(item)
        groups[key] = deduped
    return groups


def render_campaign(data, now_text):
    today = now_text[:10]
    if data is None:
        return "> 未能获取活动日历。\n"
    if isinstance(data, str):
        return "```json\n%s\n```\n" % data

    body = unwrap(data)
    groups = _campaign_from_daily(body, today)

    if groups is None:
        # 非预期结构时的降级路径：沿用旧的通用解析
        acts, seen = [], set()
        for group in _collect_dict_lists(body if body is not None else data):
            for item in group:
                act = _activity_of(item)
                key = (act["name"], act.get("start"), act.get("end"))
                if key in seen:
                    continue
                seen.add(key)
                act["stage"] = _classify(act, today)
                acts.append(act)
        groups = {
            "today": [a for a in acts if a["stage"] == "ongoing"],
            "upcoming": sorted([a for a in acts if a["stage"] == "upcoming"],
                               key=lambda a: a.get("start") or "9999"),
            "past": [a for a in acts if a["stage"] == "ended"],
        }

    ongoing, upcoming, past = groups["today"], groups["upcoming"], groups["past"]
    if not (ongoing or upcoming or past):
        return ("> 本月活动日历未返回可解析的数据。\n"
                "> 可到麦当劳 App 首页或麦麦日历查看，或稍后重试。\n")

    lines = []
    if ongoing:
        lines.append("### 🔥 今天就能吃（%d 个）" % len(ongoing))
        # 若日历未返回任何有效价格，则不展示「起价」列，避免整列都是「-」
        show_price = any(a.get("price") for a in ongoing)
        if show_price:
            lines.append("| 活动 | 亮点 | 起价 |")
            lines.append("|---|---|---|")
        else:
            lines.append("| 活动 | 亮点 |")
            lines.append("|---|---|")
        for a in ongoing:
            head = "**%s**%s" % (
                a["name"], (" `%s`" % a["tag"]) if a.get("tag") else "")
            if show_price:
                price = ("¥%s%s" % (a["price"], a["price_suffix"])) if a.get("price") else "-"
                lines.append("| %s | %s | %s |" % (head, a["desc"], price))
            else:
                lines.append("| %s | %s |" % (head, a["desc"]))
        lines.append("")

    if upcoming:
        lines.append("### ⏰ 后续档期（%d 个）" % len(upcoming))
        lines.append("| 日期 | 活动 | 亮点 | 还有 |")
        lines.append("|---|---|---|---|")
        for a in upcoming:
            left = days_left(a["date"], today) if a.get("date") else None
            lines.append("| %s | %s | %s | %s |" % (
                a["date"] or "-", a["name"], a["desc"],
                ("**%d 天**" % left) if left is not None else "-"))
        lines.append("")

    if past:
        lines.append("<details><summary>往期回顾（%d 个）</summary>\n" % len(past))
        for a in sorted(past, key=lambda x: x["date"], reverse=True):
            lines.append("- %s（%s）" % (a["name"], a["date"] or "-"))
        lines.append("\n</details>\n")

    lines.append("> ℹ️ 活动日历反映的是**营销档期**，不代表门店当前库存；"
                 "具体是否可售请以麦当劳 App 内门店页为准。")
    return "\n".join(lines) + "\n"


def render_mall(data, limit=20):
    """渲染麦麦商城（积分兑换）商品列表，标出所需积分与价格。"""
    if data is None:
        return "> 未能获取商城商品。\n"
    if isinstance(data, str):
        return "```json\n%s\n```\n" % data

    body = unwrap(data)
    items = body if isinstance(body, list) else (body.get("list") if isinstance(body, dict) else None)
    if not isinstance(items, list):
        return "```json\n%s\n```\n" % json.dumps(data, ensure_ascii=False, indent=2)

    rows = []
    for it in items:
        if not isinstance(it, dict):
            continue
        point = as_int(pick(it, "point", "points", "needPoint", "exchangePoint")) or 0
        price = pick(it, "price")
        rows.append({
            "name": pick(it, "spuName", "name", "title") or "未命名商品",
            "cat": pick(it, "catName", "category", "type") or "-",
            "point": point,
            "price": ("¥%s" % price) if price not in (None, "", "0") else "-",
            "desc": re.sub(r"\s+", " ", str(pick(it, "selling", "desc", "description") or "-"))[:40],
        })
    if not rows:
        return "> 商城返回了数据，但没有可兑换商品。\n"

    # 能纯积分兑换的（point>0）优先，其次按所需积分升序
    rows.sort(key=lambda r: (r["point"] == 0, r["point"]))

    lines = ["| 商品 | 分类 | 所需积分 | 价格 | 说明 |", "|---|---|---:|---|---|"]
    for r in rows[:limit]:
        pt = "**%d**" % r["point"] if r["point"] else "现金"
        lines.append("| %s | %s | %s | %s | %s |" % (r["name"], r["cat"], pt, r["price"], r["desc"]))
    if len(rows) > limit:
        lines.append("\n> 仅展示前 %d 个，共 %d 个。" % (limit, len(rows)))
    return "\n".join(lines) + "\n"


def render_lottery(data, now_text):
    """渲染积分抽奖信息：消耗规则、剩余次数、奖品池。"""
    if data is None:
        return "> 未能获取抽奖信息。\n"
    if isinstance(data, str):
        return "```json\n%s\n```\n" % data

    body = unwrap(data)
    if not isinstance(body, dict):
        return "```json\n%s\n```\n" % json.dumps(data, ensure_ascii=False, indent=2)

    name = pick(body, "activityName", "name") or "积分抽奖"
    status = pick(body, "activityStatusText", "statusText") or "-"
    cost = as_int(pick(body, "drawPoint", "costPoint", "singleCost"))
    available = as_int(pick(body, "availablePoint", "availablePoints"))
    begin = parse_date(pick(body, "beginTime", "startTime"))
    end = parse_date(pick(body, "endTime", "finishTime"))
    decision = body.get("drawDecision") if isinstance(body.get("drawDecision"), dict) else {}
    eligible = decision.get("resourceEligible")
    next_cost = as_int((decision.get("nextConsumption") or {}).get("points"))

    lines = ["| 项目 | 内容 |", "|---|---|",
             "| 活动 | %s |" % name,
             "| 状态 | **%s** |" % status,
             "| 单次消耗 | %s |" % (("**%d 积分**" % cost) if cost else "未返回"),
             "| 我的可用积分 | %s |" % (("**%d**" % available) if available is not None else "未返回"),
             "| 活动周期 | %s ~ %s |" % (begin or "-", end or "-")]
    if eligible is not None:
        lines.append("| 是否可抽 | %s |" % ("✅ 可以" if eligible else "❌ 不可抽（积分不足或次数用尽）"))

    can_draw = None
    if cost and available is not None:
        can_draw = available // cost if cost else None
    if can_draw is not None:
        lines.append("| 大约还能抽 | **%d 次** |" % can_draw)

    prizes = body.get("prizes") if isinstance(body.get("prizes"), list) else []
    if prizes:
        lines.append("")
        lines.append("### 🎁 奖池")
        lines.append("| 奖品 | 类型 |")
        lines.append("|---|---|")
        for p in prizes[:15]:
            if isinstance(p, dict):
                lines.append("| %s | %s |" % (p.get("name") or "-", p.get("typeText") or "-"))

    if can_draw is not None and can_draw == 0:
        lines.append("\n> ⚠️ 当前积分不足以抽一次，先攒积分或换券。")
    if next_cost and cost and next_cost != cost:
        lines.append("\n> ℹ️ 下一次将消耗 %d 积分（服务端规则可能随进度变化）。" % next_cost)
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


def cmd_campaign(client, _args):
    now = fetch_now(client)
    data, err = fetch_campaign(client, now)
    print("## 📡 麦麦活动雷达 · %s\n" % now[:10])
    if err:
        print("> ⚠️ %s\n" % err)
    print(render_campaign(data, now))
    return 0


def cmd_badge(client, _args):
    """节气徽章日历。优先用 MCP 的 now-time-info 取当前时间，失败则退回本机时间。"""
    now = fetch_now(client) if client else datetime.now(CST).strftime("%Y-%m-%d %H:%M:%S")
    print("## 🏅 麦麦24节气徽章日历 · %s\n" % now[:10])
    print(render_badge(now))
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
    print("## 🛍️ 麦麦商城 · 可兑换商品\n")
    print(render_mall(data, limit=args.size))
    return 0


def cmd_lottery(client, _args):
    now = fetch_now(client)
    ok, data = safe_call(client, "query-lottery-info")
    print("## 🎰 积分抽奖 · %s\n" % now[:10])
    if not ok:
        print("> ⚠️ %s\n" % data)
        return 1
    print(render_lottery(data, now))
    return 0


def cmd_available(client, args):
    """查看当前「可领取」的麦麦省优惠券（未领取前）。"""
    ok, data = safe_call(client, "available-coupons")
    if not ok:
        print("⚠️ 获取失败：%s" % data, file=sys.stderr)
        return 1
    print("## 🎁 可领取的麦麦省优惠券\n")
    print(render_coupons(unwrap(data), "", limit=args.size))
    return 0


def cmd_report(client, args):
    now = fetch_now(client)
    coupons, c_err = fetch_coupons(client)
    account, p_err = fetch_account(client)
    campaign, a_err = fetch_campaign(client, now)

    print("## 🍟 麦麦羊毛体检报告 · %s\n" % now[:10])
    print("### 一、券包\n")
    if c_err:
        print("> ⚠️ %s\n" % c_err)
    print(render_coupons(coupons, now))
    print("### 二、积分\n")
    if p_err:
        print("> ⚠️ %s\n" % p_err)
    print(render_points(account))
    print("### 三、麦麦活动雷达\n")
    if a_err:
        print("> ⚠️ %s\n" % a_err)
    print(render_campaign(campaign, now))

    print("### 四、节气徽章\n")
    print(render_badge(now, compact=True))

    print("### 五、积分抽奖\n")
    ok, lot = safe_call(client, "query-lottery-info")
    print(render_lottery(lot, now) if ok else "> ⚠️ %s\n" % lot)

    if args.with_mall:
        print("### 六、麦麦商城\n")
        ok, data = safe_call(client, "mall-points-products", {"pageIndex": 1, "pageSize": 20})
        print(render_mall(data, limit=20) if ok else "> ⚠️ %s\n" % data)
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
    "available": cmd_available,
    "points": cmd_points,
    "lottery": cmd_lottery,
    "campaign": cmd_campaign,
    "badge": cmd_badge,
    "bind": cmd_bind,
    "mall": cmd_mall,
    "report": cmd_report,
    "call": cmd_call,
}

# 无需 MCP Token 即可运行的命令（纯本地计算）
OFFLINE_COMMANDS = {"badge"}


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
    parser.add_argument("--confirm", action="store_true",
                        help="确认执行会消耗积分/金钱的操作（抽奖、积分兑换、下单）。"
                             "不加此开关时，这类操作一律被拦截。")
    args = parser.parse_args(argv)

    token = resolve_token(args.token)
    # 节气徽章是纯本地推算，不需要 MCP Token 也能跑
    offline = args.command in OFFLINE_COMMANDS
    if not token and not offline:
        print("❌ 未找到 MCP Token。\n"
              "   1) 访问 https://open.mcd.cn/mcp 登录并申请 Token\n"
              "   2) export MCD_MCP_TOKEN=\"你的Token\"\n"
              "   3) 或写入 %s\n"
              "   （只有 badge 命令可以不带 Token 离线运行）" % TOKEN_FILE, file=sys.stderr)
        return 2

    try:
        client = None if (offline and not token) else McdMcpClient(
            url=args.url, token=token, allow_guarded=args.confirm)
        return COMMANDS[args.command](client, args)
    except GuardError as exc:
        # 资产保护闸门：单独提示，退出码 3 便于自动化区分"被拦截"与"调用失败"
        print(str(exc), file=sys.stderr)
        return 3
    except McpError as exc:
        print("❌ %s" % exc, file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\n已中断。", file=sys.stderr)
        return 130


if __name__ == "__main__":
    sys.exit(main())
