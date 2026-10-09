# WorkBuddy 开发对话上下文

> 本文件记录「麦麦羊毛管家 / mcd-coupon-butler」在 **腾讯 WorkBuddy** 中的实际开发过程，
> 用于核验本项目是否符合「麦当劳程序员创意开发大赛」WorkBuddy 联动活动奖励条件。

---

## 一、开发环境

| 项目 | 内容 |
|---|---|
| 开发工具 | 腾讯 WorkBuddy（智能体开发模式） |
| 工作目录 | `~/WorkBuddy/MCD-China-dev` |
| 开发时间 | 2026-10-09 |
| MCP 接入 | 通过 WorkBuddy「自定义连接器 → 配置 MCP」接入麦当劳 MCP Server `mcd-mcp` |

---

## 二、开发过程关键对话

### 第 1 轮：确认活动规则与参赛路径

**我的指令**

```
我要参加 https://github.com/M-China/mcd-developer-innovation-challenge 这个活动
```

**WorkBuddy 做的事**

1. 抓取活动仓库 README、`activityGuidelines.md`、`CONTEST_DECLARATION.md` 原文，梳理出完整参赛规则；
2. 抓取麦当劳 MCP Server 仓库，整理出全部可用 Tool 清单；
3. 检查本地环境（`gh` 登录状态、git 配置），确认可直接发布到 GitHub；
4. 抓取实时 `RANKING.md`，得出关键结论：**排名完全由公开 Star 数决定，且当时全榜仅 4 个项目、第 1 名仅 11 星**，属于入场窗口期。

**产出**

- 参赛必交文件清单（README / CONTEST_DECLARATION / MCP_INTEGRATION / 源代码 / mcp-config.example.json / workbuddy.md）
- 选题方向选项与推荐排序

### 第 2 轮：确定选题

**我的选择**

```
券+积分羊毛管家
```

**WorkBuddy 做的事**：把选题收敛为「麦当劳会员的券 + 积分资产管家」，明确差异化记忆点是**积分最优兑换的每积分价值排序**，并规划出 6 个核心能力与对应的 MCP Tool 映射。

### 第 3 轮：落地项目骨架

**WorkBuddy 做的事**

1. 创建 `CONTEST_DECLARATION.md`（严格保持官方原文，一字未改）与 `mcp-config.example.json`（仅环境变量占位符）；
2. 编写 `SKILL.md`：包含触发词、执行优先级严格约束、6 个使用模式的工作流、券包体检报告格式、常见坑；
3. 编写 `scripts/mcd_wool.py`：零依赖 MCP 客户端，实现 initialize 握手、Session 保持、SSE/JSON 双形态解析、错误码翻译、防御式字段读取；
4. 本地校验脚本语法与命令行行为（`--help`、无 Token 时的引导提示）。

**关键设计决策（由 WorkBuddy 提出并被采纳）**

| 决策 | 理由 |
|---|---|
| 把 `mall-create-order` 隔离为「确认后动作」 | 积分扣减不可撤销，必须设硬闸门 |
| 券包体检必须先调 `now-time-info` | 没有可信当前时间，临期预警会失真 |
| 脚本坚持零依赖（仅标准库） | 队友/评委 clone 后可直接运行，降低复现门槛 |
| 字段读取采用多候选键名 + "未返回"兜底 | MCP 字段命名不完全固定，绝不臆造数据 |
| 券与门店绑定后再推荐 | 避免"这张券这家店用不了"的无效推荐 |

### 第 4 轮：撰写参赛文档

**WorkBuddy 做的事**：产出 `README.md`（含使用示例与目标用户）、`MCP_INTEGRATION.md`（含实际使用的 Server/Tool 清单、四条调用流程、业务价值）、`workbuddy.md`（本文件）。

### 第 5 轮：接入真实 MCP 并实测

**WorkBuddy 做的事**：接收 MCP Token → 在 WorkBuddy 中配置并启用 `mcd-mcp` 连接器 → 真实调用 `doctor` / `bind` / `coupons` / `points` / `mall` 等命令 → 把实测结果回填到 `MCP_INTEGRATION.md` 的「实测记录」一节。

### 第 6 轮：发布与报名

**WorkBuddy 做的事**：`git init` → 首次提交 → 通过 `gh` 创建**公开**仓库 → 推送 → 按标准格式在活动仓库提交【参赛申请】Issue。

---

## 三、WorkBuddy 在本项目中的具体作用

1. **规则解析**：把活动仓库多份文档一次性读完，输出可执行的参赛清单与策略判断，省去人工比对。
2. **方案设计**：基于麦当劳 MCP 的 Tool 清单反推合理选题，并给出推荐排序。
3. **代码生成**：产出可直接运行的零依赖 MCP 客户端，并在本地完成语法与行为校验。
4. **文档产出**：一次性产出 README、MCP_INTEGRATION、SKILL、参赛声明等全部参赛文件。
5. **工程落地**：完成 git 初始化、公开仓库创建、推送与报名 Issue 提交的完整链路。

---

## 四、声明

本项目的选题、设计、代码与文档均在与腾讯 WorkBuddy 的协作中完成，WorkBuddy 全程参与了从规则解析到仓库发布的开发过程。
