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

# macOS 上按优先级查找中文字体
_FONT_CANDIDATES = [
    "/System/Library/Fonts/PingFang.ttc",
    "/System/Library/Fonts/Supplemental/PingFang.ttc",
    "/Library/Fonts/Arial Unicode MS.ttf",
    "/System/Library/Fonts/STHeiti Light.ttc",
    "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
]

_FONT_NAME = "Helvetica"

for _path in _FONT_CANDIDATES:
    if os.path.exists(_path):
        try:
            pdfmetrics.registerFont(TTFont("CJK", _path))
            _FONT_NAME = "CJK"
            break
        except Exception:
            continue


def _style(name: str, parent_name: str, **kwargs) -> ParagraphStyle:
    base = getSampleStyleSheet()[parent_name]
    return ParagraphStyle(name, parent=base, fontName=_FONT_NAME, **kwargs)


def generate_monthly_report(transactions: list, year: int, month: int) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=2 * cm, bottomMargin=2 * cm,
                            leftMargin=2 * cm, rightMargin=2 * cm)

    title_s = _style("T", "Title", fontSize=18, spaceAfter=4, alignment=1)
    sub_s = _style("S", "Normal", fontSize=12, spaceAfter=16, alignment=1, textColor=colors.HexColor("#475569"))
    h2_s = _style("H2", "Heading2", fontSize=12, spaceBefore=14, spaceAfter=6)
    body_s = _style("B", "Normal", fontSize=10)

    def tbl(data, col_widths, header_color="#1E40AF"):
        t = Table(data, colWidths=col_widths)
        t.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (-1, -1), _FONT_NAME),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(header_color)),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), _FONT_NAME),
            ("FONTSIZE", (0, 0), (-1, 0), 10),
            ("ALIGN", (1, 1), (-1, -1), "RIGHT"),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.HexColor("#F8FAFC"), colors.white]),
            ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#CBD5E1")),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ("LEFTPADDING", (0, 0), (-1, -1), 7),
        ]))
        return t

    story = []

    story.append(Paragraph("湛诺财务月度报告", title_s))
    story.append(Paragraph(f"{year} 年 {month} 月", sub_s))

    total = sum(t["amount"] for t in transactions)
    story.append(Paragraph(f"本月支出合计：¥{total:,.2f}　　记录笔数：{len(transactions)} 笔", body_s))
    story.append(Spacer(1, 0.3 * cm))

    # 分类汇总
    story.append(Paragraph("分类汇总", h2_s))
    by_cat: dict[str, float] = {}
    for t in transactions:
        by_cat[t.get("category_name", "未分类")] = by_cat.get(t.get("category_name", "未分类"), 0) + t["amount"]

    cat_data = [["分类", "金额（元）", "占比"]]
    for name, amt in sorted(by_cat.items(), key=lambda x: -x[1]):
        pct = amt / total * 100 if total else 0
        cat_data.append([name, f"¥{amt:,.2f}", f"{pct:.1f}%"])
    cat_data.append(["合　计", f"¥{total:,.2f}", "100%"])
    story.append(tbl(cat_data, [8 * cm, 5 * cm, 3 * cm]))

    # 人员汇总
    story.append(Paragraph("人员汇总", h2_s))
    by_handler: dict[str, float] = {}
    for t in transactions:
        h = t.get("handler", "未知")
        by_handler[h] = by_handler.get(h, 0) + t["amount"]

    h_data = [["经手人", "金额（元）"]]
    for name, amt in sorted(by_handler.items()):
        h_data.append([name, f"¥{amt:,.2f}"])
    story.append(tbl(h_data, [8 * cm, 8 * cm]))

    # 明细
    story.append(Paragraph("明细记录", h2_s))
    d_data = [["日期", "分类", "经手人", "备注", "金额（元）"]]
    for t in sorted(transactions, key=lambda x: x["transaction_date"]):
        desc = (t.get("description") or "")[:18]
        d_data.append([
            t["transaction_date"],
            t.get("category_name", ""),
            t.get("handler", ""),
            desc,
            f"¥{t['amount']:,.2f}",
        ])
    story.append(tbl(d_data, [2.5 * cm, 4 * cm, 2 * cm, 5 * cm, 2.5 * cm]))

    story.append(Spacer(1, 0.8 * cm))
    story.append(Paragraph(f"报告生成时间：{date.today().strftime('%Y年%m月%d日')}　　仅供内部使用", body_s))

    doc.build(story)
    return buf.getvalue()


def protect_pdf(pdf_bytes: bytes, password: str) -> bytes:
    reader = PdfReader(io.BytesIO(pdf_bytes))
    writer = PdfWriter()
    for page in reader.pages:
        writer.add_page(page)
    writer.encrypt(user_password=password, owner_password=password + "_owner", algorithm="AES-256")
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()
