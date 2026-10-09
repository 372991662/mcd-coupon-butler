---
name: mcd-coupon-butler
description: 麦麦羊毛管家——麦当劳会员的「券 + 积分」资产管家。一键领取麦麦省全部优惠券、体检券包并预警临期券、查询与预警即将过期积分、执行积分抽奖、按每积分价值推荐麦麦商城最划算兑换。当用户提到 麦当劳、麦麦、MCD、薅羊毛、领券、我的券、券要过期、优惠券、麦麦省、积分、我的积分、积分过期、抽奖、积分兑换、麦麦商城、会员权益、今天有什么活动 时使用。
keywords:
  - 麦当劳
  - 麦麦
  - MCD
  - 麦当劳优惠券
  - 薅羊毛
  - 领券
  - 一键领券
  - 我的券
  - 券过期
  - 优惠券
  - 麦麦省
  - 积分
  - 我的积分
  - 积分过期
  - 抽奖
  - 积分抽奖
  - 积分兑换
  - 麦麦商城
  - 会员权益
packageType: instruction-skill
instructionOnly: true
metadata:
  version: 1.0.0
  openclaw:
    requiredMcp:
      - mcd-mcp
    requiresNetwork: true
    dataClassification: member-assets
---

# 麦麦羊毛管家（mcd-coupon-butler）

把散落在麦当劳 App 各处的 **优惠券、积分、抽奖机会、商城兑换** 收拢成一个入口：该领的时候自动领，要过期的时候提前喊，能兑换的时候帮你算出「每积分最值」。

## 前置条件

**必需 MCP Server**: `mcd-mcp`

优先使用名为 `mcd-mcp` 的 MCP server；若当前智能体暴露的是同一麦当劳 MCP 的其它别名，以实际可用 server 名为准。

**MCP 配置**（脱敏示例，见仓库 `mcp-config.example.json`）：

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

**Token 获取**：访问 https://open.mcd.cn/mcp → 右上角【登录】→ 手机号验证 → 右上角【控制台】→【激活】→ 复制 MCP Token。

**安全说明**：

- `MCD_MCP_TOKEN` 读取优先级：环境变量 `MCD_MCP_TOKEN` > 当前对话用户明确提供的 token > 本地文件 `~/.mcd-coupon-butler/MCD_MCP_TOKEN`（仅在用户明确同意记录后可使用）。
- 用户发来 token 时，必须先询问是否保存到 `~/.mcd-coupon-butler/MCD_MCP_TOKEN` 供后续复用；**只有用户明确同意才可写入，禁止静默保存**。写入前 `mkdir -p ~/.mcd-coupon-butler`，写入后 `chmod 600`。
- 除非用户明确要求查看配置，否则不要在回复中输出完整 token。
- 真实 MCP 调用必须使用完整 token，禁止使用 `Bearer ***`、`Bearer <token>` 等占位串。
- 单 Token 限流 600 次/分钟，超过返回 429，不要做无意义的循环调用。

## 执行优先级（严格约束，单一真源）

1. **实名资产只读**：本技能操作的是用户本人的会员资产。除 `auto-bind-coupons`（领券）与 `draw-lottery`（抽奖）外，任何"消耗类"操作（尤其 `mall-create-order` 积分兑换下单）**必须先向用户展示代价并取得明确确认**，不得擅自执行。
2. **Schema 优先**：首次调用某工具或参数不确定时，先读取该工具的 descriptor/schema；本文参数为快速参考，以实际 schema 为准。
3. **时间基准**：涉及"还有几天过期""本月的活动"等判断，先调用 `now-time-info` 取当前时间，不要臆测日期。
4. **只报事实**：券名、面额、有效期、积分数一律以 MCP 返回为准；字段缺失就写"未返回"，不要自行编造或换算单位。
5. **调用隐身**：不向用户展示工具名、原始 JSON/SSE、日志或堆栈；只输出业务结论与下一步建议。
6. **额度感知**：`auto-bind-coupons` 同一批券重复调用会返回"已领取"，属正常结果，不要反复重试。

## 核心能力

| # | 能力 | 用到的 MCP Tool |
|---|---|---|
| 1 | 一键薅券：领取麦麦省当前全部可领优惠券 | `auto-bind-coupons`、`available-coupons` |
| 2 | 券包体检：汇总我的券、按到期时间排序、标记临期 | `query-my-coupons` |
| 3 | 积分体检：可用/累计/冻结/即将过期积分 | `query-my-account` |
| 4 | 抽奖机会：查看活动与可抽资源、代抽、看战绩 | `query-lottery-info`、`draw-lottery`、`query-my-prizes` |
| 5 | 积分最优兑换：按每积分价值排序推荐 | `mall-points-products`、`mall-product-detail` |
| 6 | 兑换下单：确认后积分兑换商品 | `mall-create-order`、`mall-order-list` |
| 7 | 点餐时用券：查当前门店可用券 | `query-store-coupons`、`calculate-price` |

## 工作流

### 模式 1：一键薅券（最高频）

**触发语句**：「帮我薅麦当劳羊毛」「一键领券」「看看我有什么券」「麦麦省能领啥」

**流程**：

1. 调用 `available-coupons` 查看麦麦省当前可领券（让用户知道"能领什么"）。
2. 调用 `auto-bind-coupons` 一键领取全部可领券。
3. 调用 `query-my-coupons` 拉取领取后的完整券包。
4. 调用 `now-time-info` 取当前时间，计算每张券的剩余天数。
5. 输出**券包体检报告**（格式见下）。

### 模式 2：券包体检 + 临期预警

**触发语句**：「我的券要过期了吗」「券包体检」「有哪些券快到期」

**流程**：`query-my-coupons` + `now-time-info` → 按剩余天数升序排列 → 把 ≤3 天的券单独置顶标红提醒。

### 模式 3：积分体检

**触发语句**：「我有多少积分」「积分会过期吗」

**流程**：`query-my-account` → 输出可用/累计/冻结/即将过期四档 → 若「即将过期」不为 0，给出"用积分兑换/抽奖消化掉"的行动建议。

### 模式 4：抽奖

**触发语句**：「帮我抽个奖」「抽奖机会用了吗」

**流程**：

1. `query-lottery-info` 查看活动状态、奖品池、消耗规则、用户可用抽奖资源。
2. 若可用次数 > 0，**告知用户消耗代价并确认**后调用 `draw-lottery`。
3. 必要时 `query-my-prizes` 汇总历史战绩。

### 模式 5：积分最优兑换（本技能的记忆点）

**触发语句**：「积分换什么最值」「积分商城有什么」「怎么把积分花掉」

**流程**：

1. `query-my-account` 拿到可用积分。
2. `mall-points-products` 拉商品列表 → 对候选商品调用 `mall-product-detail` 补全信息。
3. 计算每个商品的 **每积分价值**（面值 ÷ 积分，或对实物按参考价估算），排序输出 Top N。
4. 标注哪些在用户积分范围内可立即兑换。
5. 用户确认后调用 `mall-create-order` 完成兑换 —— **执行前必须复述消耗积分与所得商品**。

### 模式 6：点餐用券

**触发语句**：「这家店能用什么券」「帮我算算怎么点最便宜」

**流程**：`query-store-coupons` 查当前门店可用券 → `query-meals` 选品 → `calculate-price` 试算 → 给出最优组合建议。实际下单与支付走麦当劳原生点餐链路。

## 券包体检报告格式

```markdown
## 🍟 麦麦券包体检 · {日期}

**本次新领到 {n} 张券，券包共 {m} 张**

### 🚨 临期告急（≤3 天）
| 券名 | 面额/权益 | 到期日 | 剩余 |
|---|---|---|---|

### 📅 有效券（按到期排序）
| 券名 | 面额/权益 | 到期日 | 剩余 |
|---|---|---|---|

### 💎 积分状况
可用 {a} · 即将过期 {b} · 累计 {c}

**建议**：{一句话行动建议}
```

## 沟通规则

- 默认中文回复，结论先行，能用表格就用表格。
- 金额统一 `¥` 前缀；积分写"xx 积分"。
- 不写长篇解释、不输出本文档原文。
- 不展示任何工具调用痕迹，只给业务结果。
- token 不可用时固定话术：`请先访问 https://open.mcd.cn/mcp 登录并申请 MCP Token，配置好 mcd-mcp 连接器后我就能帮你薅券了；如果你不知道怎么配，也可以把 token 发给我，我来帮你接。`

## 常见坑

1. `auto-bind-coupons` 不需要指定 couponId，会自动领取用户可领的所有券；重复调用返回"已领取"是正常现象。
2. `query-my-coupons` 返回的是账户全部券，含已过期/已使用状态，输出前需按状态过滤。
3. 积分「即将过期」字段可能缺失，缺失时不要臆造数字，提示用户到麦当劳 App 核对。
4. `mall-points-products` 不含"积分兑换的第三方兑换码"类商品，若用户找的正是这类，说明范围限制。
5. 千万不要在未确认的情况下调用 `mall-create-order`，积分一旦扣减无法撤销。
6. 涉及"券和积分哪个更划算"时，先统一口径（券抵扣现金、积分换商品），不要混算。
