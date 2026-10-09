# 🍟 mcd-coupon-butler · McDonald's Membership Butler

> **English** | [中文](README.md)

> One single entry point for everything scattered across the McDonald's China App:
> **coupons, points, lottery draws, mall redemptions, campaigns, and solar-term badges**.
> Claim what's claimable, get warned before anything expires, see which redemption is worth the most,
> hear about new drops and collabs the day they launch, and never miss a solar-term badge again.

[![MCP](https://img.shields.io/badge/MCP-McDonald's%20China-yellow)](https://open.mcd.cn/mcp)
[![Skill](https://img.shields.io/badge/WorkBuddy-Skill-blue)](https://www.workbuddy.cn/)
[![Python](https://img.shields.io/badge/Python-3.8%2B%20zero--dependency-green)](scripts/mcd_wool.py)
[![License](https://img.shields.io/badge/License-MIT-lightgrey)](LICENSE)
[![Verified](https://img.shields.io/badge/MCP-live%20API%20verified-brightgreen)](MCP_INTEGRATION.md)

> ✅ **Verified against the live API.** Every core flow — connectivity, coupon claiming, coupon wallet,
> points, lottery, campaign radar, and mall — has been run end-to-end against the real service at
> `mcp.mcd.cn` with a real membership token. See the test log in
> [`MCP_INTEGRATION.md`](MCP_INTEGRATION.md).

---

## 😫 Why you need this

McDonald's membership perks are scattered across at least 7 places. You have to claim coupons in
"Maisheng" by hand. You have to dig through your wallet to find out what's about to expire. Points sit
in your account and nobody remembers them. Lottery chances silently go to waste. Redeeming points means
comparing item after item. **Limited drops and collabs you only notice after seeing them on someone
else's feed.** And **the 24-solar-term badges require a qualifying order during each window — the exact
day you keep forgetting to eat McDonald's.**

**The result: coupons expire, points reset to zero, lottery chances are wasted, limited merch sells out,
and your badge wall has holes in it. That's your own money and your own bragging rights.**

mcd-coupon-butler does one simple thing: **it hands "remember to claim it" over to an AI. You just eat.**

---

## ✨ What it does

| Capability | In one line | MCP tools used |
|---|---|---|
| 🎁 **One-tap claiming** | Claim every currently available Maisheng coupon in a single call — no more tapping one by one | `available-coupons` `auto-bind-coupons` |
| 🚨 **Expiry alerts** | Sort your wallet by expiry; anything within 3 days gets pinned to the top and flagged | `query-my-coupons` `now-time-info` |
| 💎 **Points checkup** | Available / lifetime / frozen / expiring — all four at a glance | `query-my-account` |
| 🎰 **Lottery butler** | Check the draw, see remaining chances, draw on your behalf, tally the winnings | `query-lottery-info` `draw-lottery` `query-my-prizes` |
| 💰 **Best redemption** | Ranked by value-per-point, so you know exactly what your points are worth | `mall-points-products` `mall-product-detail` |
| 🍔 **Coupons for ordering** | See which coupons work at a given store and find the cheapest combo | `query-store-coupons` `calculate-price` |
| 📡 **Campaign radar** | Read the monthly campaign calendar and surface what's **available today** — new items, collabs, limited drops | `campaign-calendar` `now-time-info` `query-meals` |
| 🏅 **Solar-term badge alerts** | Derive the claim **window and rules** for the "24 Solar Terms" badges, with expiry warnings | `now-time-info` + local solar-term engine (**works offline**) |

---

## 👥 Who it's for

- **Frequent customers**: Eat McDonald's at least once a week, with coupons and points piling up in the account.
- **Deal hunters / optimizers**: Won't miss a single coupon, and won't accept points expiring for nothing.
- **Collab and limited-edition collectors**: The worst feeling is finding out a collab dropped — or that the merch already sold out — from someone else's post.
- **Badge collectors**: Want all 24 solar-term digital badges for 2026, but keep forgetting to order inside the window.
- **Office workers**: Lunch is already a hard decision; you don't want to also figure out today's coupons.
- **AI tool users**: Used to delegating repetitive work to an agent with a single sentence.

---

## 🚀 Quick start

### Step 1: Get a McDonald's MCP token

1. Open <https://open.mcd.cn/mcp>
2. Click **Sign in** (top right) and verify with your phone number
3. Click **Console** (top right) → **Activate** to request an MCP token
4. Accept the terms of service and copy the token

> Each token allows up to 600 requests per minute — more than enough for personal use.

### Step 2: Configure the MCP connector

Paste the JSON below into your MCP client (WorkBuddy / Cursor / Cherry Studio / Trae, etc.).
**Remember to replace `${MCD_MCP_TOKEN}` with your own token:**

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

A complete, sanitized example lives in [`mcp-config.example.json`](mcp-config.example.json).

<details>
<summary><b>Configuring inside WorkBuddy (click to expand)</b></summary>

1. In the left sidebar, go to **Experts · Skills · Connectors** → **Connectors**
2. Top right: **Custom connector** → **Configure MCP**
3. Paste the JSON above (with your token) → **Save**
4. Back in **Custom connector**, set `mcd-mcp` to **Enabled**
5. Just describe what you want in the chat box

</details>

### Step 3: Install the skill and start saving

Drop this repo's `SKILL.md` into your skills directory, then talk to it like a person:

```text
Help me claim my McDonald's coupons and check what's expiring
```

---

## 💬 Usage examples

### Example 1: One-tap claiming + wallet checkup

> **You**: Claim my McDonald's deals for me
>
> **Butler**: ## 🍟 Coupon wallet checkup · 2026-10-09
> **6 new coupons claimed, 11 in the wallet now**
>
> ### 🚨 Expiring soon (≤3 days)
> | Coupon | Value | Expires | Left |
> |---|---|---|---|
> | Spicy Chicken Burger | −¥8 | 2026-10-11 | **2 days** |
> | Medium Fries | Free medium fries | 2026-10-12 | **3 days** |
>
> ### 📅 Valid coupons (sorted by expiry)
> | Coupon | Value | Expires | Left |
> |---|---|---|---|
> | Delivery ¥8 off ¥30 | −¥8 | 2026-10-18 | 9 days |
> | ... | | | |
>
> ### 💎 Points
> Available 1,860 · Expiring 320 · Lifetime 5,420
>
> **Suggestion**: Use the two expiring coupons first (saves ¥13 total), then spend the 320 expiring points on the lottery before they reset.

### Example 2: What's the best thing to redeem?

> **You**: I have 1,800 points — what's the best thing to get?
>
> **Butler**: Ranked by value-per-point, here's your top 3 within budget:
>
> | Item | Points | Reference value | Value per point |
> |---|---:|---:|---:|
> | Big Mac voucher | 500 | ¥25.5 | **¥0.051** ⭐ |
> | McCafé medium | 800 | ¥22.0 | ¥0.028 |
> | Delivery fee waiver | 300 | ¥6.0 | ¥0.020 |
>
> **Suggestion**: Three Big Mac vouchers is the best value. Want me to redeem them? That will cost 1,500 points.

### Example 3: What's on today? (Campaign radar)

> **You**: What's happening at McDonald's today? Is the G-Dragon collab out yet?
>
> **Butler**: ## 📡 Campaign radar · 2026-10-09 (live data)
>
> ### 🔥 Available today (14)
> | Campaign | Highlight | From |
> |---|---|---|
> | **McDonald's X PEACEMINUSONE** | Grab the G-Dragon vintage baseball cap | - |
> | **McDonald's × G-DRAGON** | 8da888~Spicy~ | - |
> | **Korean-style dipping sauces** | A flaming new Korean line | - |
> | **Blueberry popping boba McFlurry** | Blueberry burst in every bite | - |
> | **Chocolate Thick Pancake Sausage & Egg** | Limited-edition chocolate flavour | - |
> | ... | 14 in total | |
>
> ### ⏰ Coming up (13)
> | Date | Campaign | Highlight | In |
> |---|---|---|---|
> | 2026-10-10 | Reserve the McJoy draw | Free-meal points prize | **1 day** |
> | 2026-10-15 | McDonald's X PEACEMINUSONE | Collab badges dropping soon | **6 days** |
> | 2026-10-22 | Week 3 merch drop | Limited-edition silk scarf | **13 days** |
>
> **Suggestion**: The G-DRAGON collab is live today. Collab merch is usually limited — go in the next day or two if you want it. Badges open on 10-15, so keep an eye on the App.

> 💡 **Never miss a drop**: Set "check McDonald's campaigns" as a WorkBuddy scheduled task to run every Monday morning, and new collabs or limited items get pushed straight to you.

### Example 4: When can I claim the solar-term badge?

McDonald's 2026 runs a year-round "**24 Solar Terms**" membership campaign. The rule for
"24-solar-term badge with every meal" is:
**during the solar term window, sign in to your membership account and place any order through the McDonald's App — the badge is granted once the order completes.**
The window pattern is "**the current solar term day → the day before the next solar term**".

> **You**: Which solar-term badge can I still claim? When does the Cold Dew one end?
>
> **Butler**: ## 🏅 24 Solar Terms badge calendar · 2026-10-09
>
> ### 🏅 Currently claimable: **Cold Dew** badge
> | Item | Detail |
> |---|---|
> | Window | 2026-10-08 ~ 2026-10-22 |
> | Progress | Day 1 · **13 days left** |
> | How to claim | Sign in → order any amount **in the McDonald's App** → badge granted on order completion |
>
> ### ⏰ Next: Frost's Descent badge
> Window 2026-10-23 ~ 2026-11-06 · starts in **14 days**
>
> ### 📅 2026 badge calendar (excerpt)
> | Solar term | Window | Days | Status |
> |---|---|---:|---|
> | White Dew | 2026-09-07 ~ 2026-09-22 | 16 | Ended |
> | Autumn Equinox | 2026-09-23 ~ 2026-10-07 | 15 | Ended |
> | Cold Dew | 2026-10-08 ~ 2026-10-22 | 15 | **🔥 Active** |
> | Frost's Descent | 2026-10-23 ~ 2026-11-06 | 15 | Not started |
>
> **Suggestion**: You have 13 days for this one — any single order **inside the McDonald's App** gets it. In the same campaign you can spend 24 points in the App's grand draw every Saturday.

> ⚠️ **Two honest disclosures**:
> 1. The badge requires an order **placed inside the McDonald's App**. Mini-programs and third-party delivery platforms generally do not count — ordering elsewhere means eating for nothing.
> 2. The McDonald's MCP **has no badge API**. This tool can only derive the **time window**; it **cannot read which badges you've already collected**. Check the badge wall in the App for your progress.

### Example 5: Straight from the command line (no client needed)

```bash
export MCD_MCP_TOKEN="your-token"

python3 scripts/mcd_wool.py doctor     # connectivity check (35 tools returned in testing)
python3 scripts/mcd_wool.py available  # what coupons can I claim
python3 scripts/mcd_wool.py bind       # claim them (wallet went 1 → 9 in testing)
python3 scripts/mcd_wool.py coupons    # wallet only (with expiry alerts)
python3 scripts/mcd_wool.py points     # points only
python3 scripts/mcd_wool.py lottery    # lottery + prize pool
python3 scripts/mcd_wool.py campaign   # campaign radar only
python3 scripts/mcd_wool.py mall       # points mall items
python3 scripts/mcd_wool.py report     # combined: wallet + points + campaigns + badges + lottery

# Badge calendar needs no token — pure local computation, runs offline
python3 scripts/mcd_wool.py badge
```

---

## 🗂️ Project structure

```text
.
├── SKILL.md                  # Skill entry: triggers, 8 usage modes, constraints
├── scripts/
│   ├── mcd_wool.py           # Zero-dependency MCP client (Python standard library only)
│   └── solar_terms.py        # 24-solar-term engine (Shouxing formula, with official-window self-test)
├── README.md                 # 中文版
├── README.en.md              # This file
├── MCP_INTEGRATION.md        # MCP server / tools / call flows / business value
├── CONTEST_DECLARATION.md    # Contest declaration
├── mcp-config.example.json   # Sanitized MCP config example
├── workbuddy.md              # WorkBuddy development conversation context
└── LICENSE
```

---

## 🔍 Data and rule sources

| Item | Source |
|---|---|
| MCP endpoint, auth, tool list | [McDonald's MCP Server official repo](https://github.com/M-China/mcd-mcp-server) |
| Coupon / points / campaign / mall data | Returned **live** by the McDonald's China MCP service at `https://mcp.mcd.cn` |
| "24 Solar Terms" campaign mechanics and claim rules | [McDonald's China official announcement](https://www.mcdonalds.com.cn/news/20251227-Nongqingmeiwei) and individual solar-term campaign pages |
| 24 solar-term dates | Computed locally with the Shouxing formula, **cross-checked against the 10 official badge windows** (`python3 scripts/solar_terms.py`) |

> All membership data comes live from McDonald's official MCP service. This project runs no backend of
> its own and stores no data. Item availability, prices, and stock are subject to McDonald's official
> channels in real time.

---

## 🔐 Security and privacy

- **No personal data is stored or uploaded.** Every call is a live request to the official McDonald's MCP service at `https://mcp.mcd.cn`. This project runs no backend and stores no data.
- **Your token stays on your machine.** It is read from the `MCD_MCP_TOKEN` environment variable; if cached locally, it goes to `~/.mcd-coupon-butler/MCD_MCP_TOKEN` with `chmod 600`, and **only with your explicit consent**.
- **Spending actions require confirmation.** The only action that consumes points is `mall-create-order`. It must restate what will be spent and received before it runs.
- **Never commit your token.** Every config file in this repo uses environment-variable placeholders only.

---

## ⚠️ Disclaimer

This project is an **entry for the McDonald's Programmer's Day Creative Development Contest**. It is
independently developed by the participant and is **not an official McDonald's product**. Output is for
reference only and does not constitute medical, nutritional, or other professional advice. Item
availability, prices, and stock are subject to McDonald's official channels in real time.

---

## 📄 License

[MIT](LICENSE)
