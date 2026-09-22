import io
import os
from datetime import date
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from pypdf import PdfWriter, PdfReader

# 中文字体候选（按平台）。缺少中文字体时 PDF 里的汉字会变成空白/方块，
# 因此 Windows / Linux 的常见字体必须一并列出。
_WIN_FONTS = os.path.join(os.environ.get("WINDIR", r"C:\\Windows"), "Fonts")

_FONT_CANDIDATES = [
    # ── macOS ──
    "/System/Library/Fonts/PingFang.ttc",
    "/System/Library/Fonts/Supplemental/PingFang.ttc",
    "/System/Library/Fonts/STHeiti Light.ttc",
    "/Library/Fonts/Arial Unicode MS.ttf",
    # ── Windows ──
    os.path.join(_WIN_FONTS, "msyh.ttc"),      # 微软雅黑
    os.path.join(_WIN_FONTS, "msyh.ttf"),
    os.path.join(_WIN_FONTS, "msyhl.ttc"),
    os.path.join(_WIN_FONTS, "simhei.ttf"),    # 黑体
    os.path.join(_WIN_FONTS, "simsun.ttc"),    # 宋体
    os.path.join(_WIN_FONTS, "simkai.ttf"),    # 楷体
    os.path.join(_WIN_FONTS, "Deng.ttf"),      # 等线
    # ── Linux ──
    "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
    "/usr/share/fonts/truetype/arphic/uming.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
]

_FONT_NAME = "Helvetica"
_FONT_PATH = None
for _path in _FONT_CANDIDATES:
    if os.path.exists(_path):
        try:
            # .ttc 字体集合需指定子字体索引
            if _path.lower().endswith(".ttc"):
                pdfmetrics.registerFont(TTFont("CJK", _path, subfontIndex=0))
            else:
                pdfmetrics.registerFont(TTFont("CJK", _path))
            _FONT_NAME = "CJK"
            _FONT_PATH = _path
            break
        except Exception:
            continue


def font_status() -> dict:
    """供「系统设置」页自检：确认当前系统能否正确导出中文 PDF。"""
    return {
        "font_name": _FONT_NAME,
        "font_path": _FONT_PATH,
        "cjk_ok": _FONT_NAME == "CJK",
        "message": (
            f"中文字体已加载：{_FONT_PATH}" if _FONT_NAME == "CJK"
            else "未找到中文字体，导出的 PDF 中汉字可能显示为空白，请安装中文字体后重试"
        ),
    }


def _style(name: str, parent_name: str, **kwargs) -> ParagraphStyle:
    base = getSampleStyleSheet()[parent_name]
    return ParagraphStyle(name, parent=base, fontName=_FONT_NAME, **kwargs)


def _tbl(data, col_widths, header_color="#1E40AF"):
    t = Table(data, colWidths=col_widths)
    t.setStyle(TableStyle([
        ("FONTNAME",      (0, 0), (-1, -1), _FONT_NAME),
        ("FONTSIZE",      (0, 0), (-1, -1), 9),
        ("BACKGROUND",    (0, 0), (-1, 0),  colors.HexColor(header_color)),
        ("TEXTCOLOR",     (0, 0), (-1, 0),  colors.white),
        ("FONTSIZE",      (0, 0), (-1, 0),  10),
        ("ALIGN",         (1, 1), (-1, -1), "RIGHT"),
        ("ROWBACKGROUNDS",(0, 1), (-1, -1), [colors.HexColor("#F8FAFC"), colors.white]),
        ("GRID",          (0, 0), (-1, -1), 0.4, colors.HexColor("#CBD5E1")),
        ("TOPPADDING",    (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING",   (0, 0), (-1, -1), 7),
    ]))
    return t


def generate_report(transactions: list, date_from: date, date_to: date, tx_type: str = "all") -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=2*cm, bottomMargin=2*cm,
                            leftMargin=2*cm, rightMargin=2*cm)

    title_s = _style("T",  "Title",   fontSize=18, spaceAfter=4, alignment=1)
    sub_s   = _style("S",  "Normal",  fontSize=11, spaceAfter=4, alignment=1,
                     textColor=colors.HexColor("#475569"))
    h2_s    = _style("H2", "Heading2",fontSize=12, spaceBefore=14, spaceAfter=6)
    body_s  = _style("B",  "Normal",  fontSize=10)

    type_label = {"all": "收支全览", "income": "收入报告", "expense": "支出报告"}.get(tx_type, "财务报告")
    date_label = f"{date_from.strftime('%Y年%m月%d日')} — {date_to.strftime('%Y年%m月%d日')}"

    story = []
    story.append(Paragraph("湛诺财务报告", title_s))
    story.append(Paragraph(f"{type_label}　{date_label}", sub_s))
    story.append(Spacer(1, 0.3*cm))

    income_rows  = [t for t in transactions if t.get("transaction_type") == "income"]
    expense_rows = [t for t in transactions if t.get("transaction_type") != "income"]
    total_income  = sum(t["amount"] for t in income_rows)
    total_expense = sum(t["amount"] for t in expense_rows)
    net = total_income - total_expense

    if tx_type == "all":
        story.append(Paragraph(
            f"收入合计：¥{total_income:,.2f}　　支出合计：¥{total_expense:,.2f}　　净结余：¥{net:+,.2f}　　共 {len(transactions)} 笔",
            body_s))
    elif tx_type == "income":
        story.append(Paragraph(f"收入合计：¥{total_income:,.2f}　　共 {len(transactions)} 笔", body_s))
    else:
        story.append(Paragraph(f"支出合计：¥{total_expense:,.2f}　　共 {len(transactions)} 笔", body_s))
    story.append(Spacer(1, 0.3*cm))

    def cat_table(rows, header_color):
        total = sum(r["amount"] for r in rows)
        by_cat: dict[str, float] = {}
        for r in rows:
            k = r.get("category_name", "未分类")
            by_cat[k] = by_cat.get(k, 0) + r["amount"]
        data = [["分类", "金额（元）", "占比"]]
        for name, amt in sorted(by_cat.items(), key=lambda x: -x[1]):
            pct = amt / total * 100 if total else 0
            data.append([name, f"¥{amt:,.2f}", f"{pct:.1f}%"])
        data.append(["合　计", f"¥{total:,.2f}", "100%"])
        return _tbl(data, [8*cm, 5*cm, 3*cm], header_color)

    def handler_table(rows, header_color):
        by_h: dict[str, float] = {}
        for r in rows:
            h = r.get("handler", "未知")
            by_h[h] = by_h.get(h, 0) + r["amount"]
        data = [["经手人", "金额（元）"]]
        for name, amt in sorted(by_h.items()):
            data.append([name, f"¥{amt:,.2f}"])
        return _tbl(data, [8*cm, 8*cm], header_color)

    # 收入部分
    if tx_type in ("all", "income") and income_rows:
        story.append(Paragraph("收入 — 分类汇总", h2_s))
        story.append(cat_table(income_rows, "#065F46"))
        story.append(Spacer(1, 0.2*cm))
        story.append(Paragraph("收入 — 人员汇总", h2_s))
        story.append(handler_table(income_rows, "#065F46"))

    # 支出部分
    if tx_type in ("all", "expense") and expense_rows:
        story.append(Paragraph("支出 — 分类汇总", h2_s))
        story.append(cat_table(expense_rows, "#1E40AF"))
        story.append(Spacer(1, 0.2*cm))
        story.append(Paragraph("支出 — 人员汇总", h2_s))
        story.append(handler_table(expense_rows, "#1E40AF"))

    # 明细
    story.append(Paragraph("明细记录", h2_s))
    d_data = [["日期", "收/支", "分类", "经手人", "备注", "金额（元）"]]
    for t in transactions:
        ttype = "收入" if t.get("transaction_type") == "income" else "支出"
        desc = (t.get("description") or "")[:16]
        d_data.append([
            t["transaction_date"], ttype,
            t.get("category_name", ""), t.get("handler", ""),
            desc, f"¥{t['amount']:,.2f}",
        ])
    story.append(_tbl(d_data, [2.3*cm, 1.5*cm, 3.5*cm, 2*cm, 4.5*cm, 2.2*cm]))

    story.append(Spacer(1, 0.8*cm))
    story.append(Paragraph(
        f"报告生成时间：{date.today().strftime('%Y年%m月%d日')}　　仅供内部使用", body_s))

    doc.build(story)
    return buf.getvalue()


# 保留旧名称兼容（旧代码调用 generate_monthly_report）
def generate_monthly_report(transactions, year, month):
    from datetime import date
    import calendar
    last_day = calendar.monthrange(year, month)[1]
    return generate_report(transactions, date(year, month, 1), date(year, month, last_day))


def protect_pdf(pdf_bytes: bytes, password: str) -> bytes:
    reader = PdfReader(io.BytesIO(pdf_bytes))
    writer = PdfWriter()
    for page in reader.pages:
        writer.add_page(page)
    writer.encrypt(user_password=password, owner_password=password + "_owner", algorithm="AES-256")
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()
