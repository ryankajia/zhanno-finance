from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import Transaction, User
from app.schemas import ReportRequest
from app.auth import get_current_user
from app.utils.encryption import decrypt
from app.utils.pdf_gen import generate_report, protect_pdf

router = APIRouter()


@router.post("/monthly")
def generate_report_endpoint(
    req: ReportRequest,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    q = db.query(Transaction).filter(
        Transaction.is_deleted == False,
        Transaction.transaction_date >= req.date_from,
        Transaction.transaction_date <= req.date_to,
    )
    if req.transaction_type in ("income", "expense"):
        q = q.filter(Transaction.transaction_type == req.transaction_type)

    rows = q.order_by(Transaction.transaction_date).all()
    if not rows:
        raise HTTPException(status_code=404, detail="所选时间段暂无记录")

    data = [
        {
            "amount": t.amount,
            "transaction_type": t.transaction_type or "expense",
            "category_name": t.category.name if t.category else "未分类",
            "handler": t.handler,
            "description": decrypt(t.description) if t.description else "",
            "transaction_date": t.transaction_date.strftime("%Y-%m-%d"),
        }
        for t in rows
    ]

    pdf = generate_report(data, req.date_from, req.date_to, req.transaction_type)
    if req.password:
        pdf = protect_pdf(pdf, req.password)

    fname = f"zhanno_{req.date_from.strftime('%Y%m%d')}_{req.date_to.strftime('%Y%m%d')}.pdf"
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )
