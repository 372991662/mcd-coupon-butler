# 🍟 麦麦羊毛管家 · mcd-coupon-butler

> 把麦当劳 App 里散落各处的 **优惠券、积分、抽奖机会、商城兑换** 收拢成一个入口：
> 该领的时候自动领，要过期的时候提前喊，能兑换的时候帮你算清「哪一笔最值」。

[![MCP](https://img.shields.io/badge/MCP-麦当劳中国-yellow)](https://open.mcd.cn/mcp)
[![Skill](https://img.shields.io/badge/WorkBuddy-Skill-blue)](https://www.workbuddy.cn/)
[![Python](https://img.shields.io/badge/Python-3.8%2B%20零依赖-green)](scripts/mcd_wool.py)
[![License](https://img.shields.io/badge/License-MIT-lightgrey)](LICENSE)

---

## 😫 为什么需要它

麦当劳的会员权益散落在至少 5 个地方：麦麦省要手动领券、券包要翻半天才知道什么快过期、积分躺在账户里没人记得、抽奖机会白白作废、商城兑换要一页页比价。

**结果是：券过期了、积分清零了、抽奖机会浪费了 —— 全是你自己的钱。**

麦麦羊毛管家做的事很简单：**把"记得薅"这件事交给 AI，你只管吃。**

---

## ✨ 它能做什么

| 能力 | 一句话说明 | 背后的 MCP Tool |
|---|---|---|
| 🎁 **一键薅券** | 一次调用领走麦麦省当前全部可领券，不用再逐张点 | `available-coupons` `auto-bind-coupons` |
| 🚨 **临期预警** | 券包按到期时间排序，≤3 天的单独置顶标红 | `query-my-coupons` `now-time-info` |
| 💎 **积分体检** | 可用 / 累计 / 冻结 / 即将过期，四档一次看清 | `query-my-account` |
| 🎰 **抽奖管家** | 查活动、看可用次数、代抽、汇总战绩 | `query-lottery-info` `draw-lottery` `query-my-prizes` |
| 💰 **积分最优兑换** | 按「每积分价值」排序，告诉你积分换什么最划算 | `mall-points-products` `mall-product-detail` |
| 🍔 **点餐用券** | 查当前门店可用券，帮你试算最省的下单组合 | `query-store-coupons` `calculate-price` |

---

## 👥 目标用户

- **高频麦门人**：每周至少吃一次麦当劳，会员账户里攒着券和积分。
- **羊毛党 / 精算派**：不想错过任何一张券，也不接受积分白白过期。
- **打工人**：午餐决策已经够累了，不想再研究"今天的券怎么用"。
- **AI 工具用户**：习惯把重复劳动交给智能体，只用一句话下指令。

---

## 🚀 快速开始

### 第一步：申请麦当劳 MCP Token

1. 打开 <https://open.mcd.cn/mcp>
2. 点击右上角【登录】，用手机号完成验证
3. 点击右上角【控制台】→【激活】申请 MCP Token
4. 阅读并同意服务协议后，一键复制 Token

> 每个 Token 每分钟最多 600 次请求，个人使用绰绰有余。

### 第二步：配置 MCP 连接器

把下面的 JSON 填进你的 MCP 客户端（WorkBuddy / Cursor / Cherry Studio / Trae 等），
**记得把 `${MCD_MCP_TOKEN}` 换成你自己的 Token**：

```json
{
  "mcpServers": {
    "mcd-mcp": {
      "type": "streamablehttp",
      "url": "https://mcp.mcd.cn",
      "headers": {
        "Authorization": "Bearer ${MCD_MCP_TOKEN}"
      }
    }
  }
}
```

完整的脱敏配置示例见 [`mcp-config.example.json`](mcp-config.example.json)。

<details>
<summary><b>在 WorkBuddy 中配置（点开）</b></summary>

1. 左侧边栏进入【专家·技能·连接器】→【连接器】页签
2. 右上角【自定义连接器】→【配置 MCP】
3. 粘贴上面的 JSON（替换 Token 占位符）→【保存】
4. 回到【自定义连接器】，把 `mcd-mcp` 设为【启用】
5. 在对话框直接说需求即可

</details>

### 第三步：装技能，开始薅

把本仓库的 `SKILL.md` 放进你的技能目录即可。然后在对话框里直接说人话：

```text
帮我薅一下麦当劳的羊毛
```

---

## 💬 使用示例

### 示例 1：一键薅券 + 券包体检

> **你**：帮我薅一下麦麦的羊毛
>
> **管家**：## 🍟 麦麦券包体检 · 2026-10-09
> **本次新领到 6 张券，券包共 11 张**
>
> ### 🚨 临期告急（≤3 天）
> | 券名 | 权益 | 到期日 | 剩余 |
> |---|---|---|---|
> | 麦辣鸡腿堡券 | 立减 ¥8 | 2026-10-11 | **2 天** |
> | 薯条(中)券 | 免费中薯 | 2026-10-12 | **3 天** |
>
> ### 📅 有效券（按到期排序）
> | 券名 | 权益 | 到期日 | 剩余 |
> |---|---|---|---|
> | 麦乐送满 30 减 8 | 立减 ¥8 | 2026-10-18 | 9 天 |
> | ... | | | |
>
> ### 💎 积分状况
> 可用 1,860 · 即将过期 320 · 累计 5,420
>
> **建议**：先把 2 张临期券用掉（合计省 ¥13），再拿 320 即将过期积分去抽奖，避免清零。

### 示例 2：积分换什么最值

> **你**：我有 1800 积分，换什么最划算？
>
> **管家**：按「每积分价值」排序，你的积分范围内 Top 3：
>
> | 商品 | 消耗积分 | 参考价值 | 每积分价值 |
> |---|---:|---:|---:|
> | 巨无霸兑换券 | 500 | ¥25.5 | **¥0.051** ⭐ |
> | 麦咖啡中杯 | 800 | ¥22.0 | ¥0.028 |
> | 麦乐送免配送费券 | 300 | ¥6.0 | ¥0.020 |
>
> **建议**：换 3 张巨无霸券最划算。需要我帮你下单兑换吗？会消耗 1500 积分。

### 示例 3：命令行直接用（不依赖任何客户端）

```bash
export MCD_MCP_TOKEN="你的Token"

python3 scripts/mcd_wool.py doctor     # 连通性自检
python3 scripts/mcd_wool.py coupons    # 只看券包
python3 scripts/mcd_wool.py points     # 只看积分
python3 scripts/mcd_wool.py bind       # 一键领券
python3 scripts/mcd_wool.py report     # 合并体检报告
```

---

## 🗂️ 项目结构

```text
.
├── SKILL.md                  # 技能主文件：触发词、工作流编排、约束
├── scripts/
│   └── mcd_wool.py           # 零依赖 MCP 客户端（仅用 Python 标准库）
├── README.md                 # 你正在看的这份
├── MCP_INTEGRATION.md        # 实际使用的 MCP Server / Tool / 调用流程 / 业务价值
├── CONTEST_DECLARATION.md    # 参赛声明
├── mcp-config.example.json   # 脱敏后的 MCP 配置示例
├── workbuddy.md              # WorkBuddy 开发对话上下文
└── LICENSE
```

---

## 🔐 安全与隐私

- **不保存、不上传任何个人数据**：所有调用都是发往麦当劳官方 MCP 服务 `https://mcp.mcd.cn` 的实时请求，本项目不自建服务端、不做数据落地。
- **Token 只存在你本机**：优先读环境变量 `MCD_MCP_TOKEN`；如需本地缓存，写入 `~/.mcd-coupon-butler/MCD_MCP_TOKEN` 并 `chmod 600`，且**必须经你明确同意**。
- **消耗类操作需二次确认**：唯一会扣积分的是 `mall-create-order`（积分兑换下单），执行前必须向你复述消耗与所得。
- **不要把 Token 提交到仓库**：仓库内所有配置文件仅使用环境变量占位符。

---

## ⚠️ 免责声明

本项目为**麦当劳程序员节创意开发大赛参赛作品**，由参赛者独立开发，**非麦当劳官方产品**。
项目输出仅供参考，不构成医疗、营养或其他专业建议；餐品信息、价格及供应状态以麦当劳官方渠道的实时结果为准。

---

## 📄 License

[MIT](LICENSE)
