"""中国大陆纳税申报期限日历。

数据来源：国家税务总局办公厅《关于明确2026年度申报纳税期限的通知》
          （税总办征科函〔2025〕64号）
          https://fgk.chinatax.gov.cn/zcfgk/c102424/c5245729/content.html

每年年底国家税务总局会公布次年的申报期限（因法定节假日顺延），
需要在 OFFICIAL_MONTHLY_DEADLINES 中补充新年度数据。
未收录的年度自动回退为"当月15日，遇周末顺延"，并标记 official=False。
"""
from datetime import date, timedelta

# {年份: {月份: 截止日}} —— 实行按月/按季期满后15日内申报的各税种
OFFICIAL_MONTHLY_DEADLINES: dict[int, dict[int, int]] = {
    2026: {1: 20, 2: 24, 3: 16, 4: 20, 5: 22, 6: 15,
           7: 15, 8: 17, 9: 15, 10: 26, 11: 16, 12: 15},
}

# 申报期限所依据的法定文件，展示给用户以证明数据来源
DEADLINE_SOURCE: dict[int, str] = {
    2026: "税总办征科函〔2025〕64号",
}


def _roll_off_weekend(d: date) -> date:
    """遇周六/周日顺延至下一个工作日（不含法定节假日，仅作回退估算）。"""
    while d.weekday() >= 5:
        d += timedelta(days=1)
    return d


def monthly_deadline(year: int, month: int) -> tuple[date, bool]:
    """返回 (该月申报截止日, 是否为税务总局官方公布数据)。"""
    table = OFFICIAL_MONTHLY_DEADLINES.get(year)
    if table and month in table:
        return date(year, month, table[month]), True
    return _roll_off_weekend(date(year, month, 15)), False


# ── 税种定义 ────────────────────────────────────────────────
# period: monthly | quarterly | annual
# applies_to: 该税种在什么条件下需要申报（由纳税人档案决定）

TAX_TYPES = [
    {
        "code": "vat",
        "name": "增值税及附加税费",
        "period": "by_profile",          # 随纳税人申报周期（月报/季报）
        "detail": "增值税、城市维护建设税、教育费附加、地方教育附加",
        "legal_basis": "《中华人民共和国增值税暂行条例》第二十三条",
    },
    {
        "code": "cit_prepay",
        "name": "企业所得税（预缴）",
        "period": "quarterly",
        "detail": "季度终了后15日内预缴申报，期限随当月征期顺延",
        "legal_basis": "《中华人民共和国企业所得税法》第五十四条",
    },
    {
        "code": "iit_withhold",
        "name": "个人所得税（代扣代缴）",
        "period": "monthly",
        "detail": "扣缴义务人应在次月15日内办理全员全额扣缴申报",
        "legal_basis": "《中华人民共和国个人所得税法》第十一条",
        "requires": "has_employees",
    },
    {
        "code": "stamp_duty",
        "name": "印花税",
        "period": "quarterly",
        "detail": "按季申报的，季度终了后15日内申报缴纳",
        "legal_basis": "《中华人民共和国印花税法》第十六条",
    },
    {
        "code": "cit_annual",
        "name": "企业所得税汇算清缴",
        "period": "annual",
        "fixed_date": (5, 31),
        "detail": "纳税年度终了后5个月内汇算清缴，结清应补应退税款",
        "legal_basis": "《中华人民共和国企业所得税法》第五十四条",
    },
    {
        "code": "iit_business_annual",
        "name": "个人所得税经营所得汇算清缴",
        "period": "annual",
        "fixed_date": (3, 31),
        "detail": "取得经营所得的，次年3月31日前办理汇算清缴",
        "legal_basis": "《中华人民共和国个人所得税法》第十二条",
        "requires": "has_business_income",
    },
    {
        "code": "iit_comprehensive",
        "name": "个人所得税综合所得年度汇算",
        "period": "annual",
        "fixed_date": (6, 30),
        "start_date": (3, 1),
        "detail": "办理时间为次年3月1日至6月30日",
        "legal_basis": "《中华人民共和国个人所得税法》第十一条",
    },
    {
        "code": "business_annual_report",
        "name": "工商年报公示",
        "period": "annual",
        "fixed_date": (6, 30),
        "start_date": (1, 1),
        "detail": "市场主体须于6月30日前报送年度报告并公示，逾期列入经营异常名录",
        "legal_basis": "《企业信息公示暂行条例》第八条",
    },
    {
        "code": "disability_fund",
        "name": "残疾人就业保障金",
        "period": "annual",
        "fixed_date": (11, 30),
        "detail": "各省申报期不同（多为每年8—11月），请以当地税务机关通知为准",
        "legal_basis": "《残疾人就业保障金征收使用管理办法》",
        "local_variance": True,
    },
]

TAX_BY_CODE = {t["code"]: t for t in TAX_TYPES}

_QUARTER_FILING_MONTH = {1: 4, 2: 7, 3: 10, 4: 1}   # 季度 → 申报所在月


def _period_label(code: str, period_key: str) -> str:
    t = TAX_BY_CODE[code]
    if t["period"] == "annual":
        return f"{period_key} 年度"
    if "-Q" in period_key:
        y, q = period_key.split("-Q")
        return f"{y}年第{q}季度"
    y, m = period_key.split("-")
    return f"{y}年{int(m)}月"


def upcoming_deadlines(profile: dict, today: date, days_ahead: int = 120) -> list[dict]:
    """生成从 today 起 days_ahead 天内的所有申报事项。

    profile: {"filing_period": "month"|"quarter", "has_employees": bool,
              "has_business_income": bool, "enabled": [code, ...]}
    """
    enabled = set(profile.get("enabled") or TAX_BY_CODE.keys())
    horizon = today + timedelta(days=days_ahead)
    # 往前多看一点，便于展示"已逾期"的事项
    start = today - timedelta(days=45)
    out: list[dict] = []

    for t in TAX_TYPES:
        code = t["code"]
        if code not in enabled:
            continue
        req = t.get("requires")
        if req and not profile.get(req, True):
            continue

        if t["period"] == "annual":
            for year in {start.year, horizon.year}:
                mm, dd = t["fixed_date"]
                due = date(year, mm, dd)
                if not (start <= due <= horizon):
                    continue
                out.append(_item(t, due, str(year - 1), True, t.get("start_date"), year))
            continue

        period = t["period"]
        if period == "by_profile":
            period = "quarterly" if profile.get("filing_period") == "quarter" else "monthly"

        if period == "monthly":
            cur = date(start.year, start.month, 1)
            while cur <= horizon:
                due, official = monthly_deadline(cur.year, cur.month)
                if start <= due <= horizon:
                    # 申报的是上一个月的税款所属期
                    prev = cur - timedelta(days=1)
                    out.append(_item(t, due, f"{prev.year}-{prev.month:02d}", official))
                cur = (cur.replace(day=28) + timedelta(days=7)).replace(day=1)
        else:  # quarterly
            for year in range(start.year, horizon.year + 1):
                for q in (1, 2, 3, 4):
                    fm = _QUARTER_FILING_MONTH[q]
                    fy = year + 1 if q == 4 else year
                    due, official = monthly_deadline(fy, fm)
                    if start <= due <= horizon:
                        out.append(_item(t, due, f"{year}-Q{q}", official))

    out.sort(key=lambda x: x["due_date"])
    return out


def _item(t: dict, due: date, period_key: str, official: bool,
          start_date=None, start_year=None) -> dict:
    d = {
        "code": t["code"],
        "name": t["name"],
        "detail": t["detail"],
        "legal_basis": t.get("legal_basis", ""),
        "local_variance": t.get("local_variance", False),
        "due_date": due.isoformat(),
        "period_key": period_key,
        "period_label": _period_label(t["code"], period_key),
        "official_deadline": official,
        "source_doc": DEADLINE_SOURCE.get(due.year, ""),
    }
    if start_date and start_year:
        d["window_start"] = date(start_year, start_date[0], start_date[1]).isoformat()
    return d
