from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy import extract
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import Transaction, User
from app.schemas import ReportRequest
from app.auth import get_current_user
from app.utils.encryption import decrypt
from app.utils.pdf_gen import generate_monthly_report, protect_pdf

router = APIRouter()


@router.post("/monthly")
def generate_report(
    req: ReportRequest,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    rows = (
        db.query(Transaction)
        .filter(
            Transaction.is_deleted == False,
            extract("year", Transaction.transaction_date) == req.year,
            extract("month", Transaction.transaction_date) == req.month,
        )
        .all()
    )
    if not rows:
        raise HTTPException(status_code=404, detail="该月份暂无记录")

    data = [
        {
            "amount": t.amount,
            "category_name": t.category.name if t.category else "未分类",
            "handler": t.handler,
            "description": decrypt(t.description) if t.description else "",
            "transaction_date": t.transaction_date.strftime("%Y-%m-%d"),
        }
        for t in rows
    ]

    pdf = generate_monthly_report(data, req.year, req.month)
    if req.password:
        pdf = protect_pdf(pdf, req.password)

    filename = f"zhanno_{req.year}_{req.month:02d}.pdf"
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
