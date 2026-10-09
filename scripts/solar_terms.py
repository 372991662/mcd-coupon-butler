#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
二十四节气计算模块（零依赖）

用途：为「麦麦羊毛管家」推算麦当劳「麦麦24节气」徽章的领取时间窗口。

背景（已核实的官方规则）：
    麦当劳中国 2026 年推出贯穿全年的「麦麦24节气」会员活动，其中
    「24节气徽章餐餐领」规则为 —— 节气期间内，用户需登录麦当劳会员账号，
    并通过**麦当劳 App 下单任意金额，完成订单后**即可获得当期节气数字徽章 1 枚。

    从官方已公布的多期活动看，每一期徽章的领取窗口为：
        当期节气日  →  下一个节气日的前一天

算法：
    「寿星公式」（21 世纪适用）：day = int(Y × 0.2422 + C) − int(Y / 4)
    其中 Y 为年份后两位，C 为该节气常数，另有个别年份需要 ±1 天的例外修正。
    该公式在 2000—2099 年区间对绝大多数年份给出与官方发布一致的日期，
    本项目已用 2026 年 10 个官方公布日期完成校验（见文件末尾自检）。
"""

from datetime import date, timedelta

# (节气名, 所在月, 21 世纪常数 C, 例外修正 {公历年: 天数偏移})
# 常数与例外取自通用的 21 世纪寿星公式修正表。
SOLAR_TERMS = [
    ("小寒", 1, 5.4055, {}),
    ("大寒", 1, 20.12, {2082: 1}),
    ("立春", 2, 3.87, {}),
    ("雨水", 2, 18.73, {2026: -1}),
    ("惊蛰", 3, 5.63, {}),
    ("春分", 3, 20.646, {2084: 1}),
    ("清明", 4, 4.81, {}),
    ("谷雨", 4, 20.1, {}),
    ("立夏", 5, 5.52, {1911: 1}),
    ("小满", 5, 21.04, {2008: 1}),
    ("芒种", 6, 5.678, {1902: 1}),
    ("夏至", 6, 21.37, {1928: 1}),
    ("小暑", 7, 7.108, {1925: 1, 2016: 1}),
    ("大暑", 7, 22.83, {1922: 1}),
    ("立秋", 8, 7.5, {2002: 1}),
    ("处暑", 8, 23.13, {}),
    ("白露", 9, 7.646, {1927: 1}),
    ("秋分", 9, 23.042, {1942: 1}),
    ("寒露", 10, 8.318, {2088: 1}),
    ("霜降", 10, 23.438, {2089: 1}),
    ("立冬", 11, 7.438, {2089: 1}),
    ("小雪", 11, 22.36, {1978: 1}),
    ("大雪", 12, 7.18, {1954: 1}),
    ("冬至", 12, 21.94, {1918: -1, 2021: -1}),
]

# 麦当劳「麦麦24节气」期间的固定玩法
BADGE_RULES = [
    "登录麦当劳会员账号",
    "通过【麦当劳 App】下单任意金额",
    "完成订单后自动获得当期数字徽章 1 枚",
]


def _term_day(year, c, fixups):
    """按寿星公式计算某节气在当月的日号。"""
    y = year % 100
    day = int(y * 0.2422 + c) - int(y / 4)
    day += fixups.get(year, 0)
    return day


def solar_term_dates(year):
    """返回该年 24 个节气，形如 [("小寒", date(2026,1,5)), ...]，按时间升序。"""
    result = []
    for name, month, c, fixups in SOLAR_TERMS:
        result.append((name, date(year, month, _term_day(year, c, fixups))))
    result.sort(key=lambda x: x[1])
    return result


def badge_windows(year):
    """返回该年 24 个节气徽章的领取窗口。

    窗口 = 当期节气日 → 下一个节气日的前一天。
    冬至之后的下一个节气是次年的小寒，因此跨年窗口也会被正确生成。

    每项字段：节气名 / 开始日 / 结束日 / 是否跨年
    """
    terms = solar_term_dates(year)
    nxt = solar_term_dates(year + 1)[0]  # 次年的小寒
    chain = terms + [nxt]

    windows = []
    for i in range(len(terms)):
        name, start = chain[i]
        _, next_start = chain[i + 1]
        end = next_start - timedelta(days=1)
        windows.append({
            "name": name,
            "start": start,
            "end": end,
            "cross_year": end.year != start.year,
        })
    return windows


def current_badge(today=None, year=None):
    """定位"今天"对应的徽章窗口。

    返回 (当前窗口, 下一个窗口)；若今天恰在年末且已过冬至窗口，则下一个
    为次年小寒徽章（跨年窗口）。
    两者都可能为 None。
    """
    today = today or date.today()
    year = year or today.year

    # 今天的窗口既可能落在本年，也可能落在上一年生成的跨年窗口里
    for y in (year - 1, year, year + 1):
        windows = badge_windows(y)
        for idx, w in enumerate(windows):
            if w["start"] <= today <= w["end"]:
                nxt = windows[idx + 1] if idx + 1 < len(windows) else None
                if nxt is None:
                    nxt = badge_windows(y + 1)[0]
                return w, nxt
    return None, None


def days_between(start, end):
    return (end - start).days


def _self_test():
    """用麦当劳官方 2026 年已公布的徽章窗口校验本模块。"""
    confirmed = {
        "惊蛰": ("2026-03-05", "2026-03-19"),
        "春分": ("2026-03-20", "2026-04-04"),
        "清明": ("2026-04-05", "2026-04-19"),
        "谷雨": ("2026-04-20", "2026-05-04"),
        "立夏": ("2026-05-05", "2026-05-20"),
        "小满": ("2026-05-21", "2026-06-04"),
        "芒种": ("2026-06-05", "2026-06-20"),
        "夏至": ("2026-06-21", "2026-07-06"),
        "立秋": ("2026-08-07", "2026-08-22"),
        "处暑": ("2026-08-23", "2026-09-06"),
    }
    got = {w["name"]: (w["start"].isoformat(), w["end"].isoformat()) for w in badge_windows(2026)}
    ok = 0
    for name, expect in confirmed.items():
        actual = got.get(name)
        flag = "✅" if actual == expect else "❌"
        if actual == expect:
            ok += 1
        else:
            print("  %s %s 期望 %s 实际 %s" % (flag, name, expect, actual))
    print("官方公布窗口校验：%d/%d 通过" % (ok, len(confirmed)))
    return ok == len(confirmed)


if __name__ == "__main__":
    _self_test()
