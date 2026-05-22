from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session
from sqlalchemy import extract, func
from typing import Optional
from app.database import get_db
from app.models import Transaction, Category, User, AuditLog
from app.schemas import TransactionCreate
from app.auth import get_current_user, require_admin
from app.utils.encryption import encrypt, decrypt

router = APIRouter()


def _serialize(t: Transaction) -> dict:
    return {
        "id": t.id,
        "amount": t.amount,
        "category_id": t.category_id,
        "category_name": t.category.name if t.category else None,
        "handler": t.handler,
        "description": decrypt(t.description) if t.description else None,
        "transaction_date": t.transaction_date.isoformat(),
        "created_by": t.created_by,
        "created_by_name": t.creator.username if t.creator else None,
        "created_at": t.created_at.isoformat(),
    }


@router.get("/")
def list_transactions(
    handler: Optional[str] = Query(None),
    category_id: Optional[int] = Query(None),
    year: Optional[int] = Query(None),
    month: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    q = db.query(Transaction).filter(Transaction.is_deleted == False)
    if handler:
        q = q.filter(Transaction.handler == handler)
    if category_id:
        q = q.filter(Transaction.category_id == category_id)
    if year:
        q = q.filter(extract("year", Transaction.transaction_date) == year)
    if month:
        q = q.filter(extract("month", Transaction.transaction_date) == month)

    return [_serialize(t) for t in q.order_by(Transaction.transaction_date.desc()).limit(500)]


@router.get("/summary")
def get_summary(
    year: Optional[int] = Query(None),
    month: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    q = db.query(Transaction).filter(Transaction.is_deleted == False)
    if year:
        q = q.filter(extract("year", Transaction.transaction_date) == year)
    if month:
        q = q.filter(extract("month", Transaction.transaction_date) == month)

    rows = q.all()
    total = sum(t.amount for t in rows)

    by_category: dict[str, float] = {}
    by_handler: dict[str, float] = {}
    max_amount = 0.0

    for t in rows:
        name = t.category.name if t.category else "未分类"
        by_category[name] = by_category.get(name, 0) + t.amount
        by_handler[t.handler] = by_handler.get(t.handler, 0) + t.amount
        if t.amount > max_amount:
            max_amount = t.amount

    return {
        "total": total,
        "count": len(rows),
        "max_amount": max_amount,
        "by_category": by_category,
        "by_handler": by_handler,
    }


@router.post("/")
def create_transaction(
    body: TransactionCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    cat = db.query(Category).filter(Category.id == body.category_id).first()
    if not cat:
        raise HTTPException(status_code=404, detail="分类不存在")

    t = Transaction(
        amount=body.amount,
        category_id=body.category_id,
        handler=body.handler,
        description=encrypt(body.description) if body.description else None,
        transaction_date=body.transaction_date,
        created_by=current_user.id,
    )
    db.add(t)
    ip = request.client.host if request.client else "unknown"
    db.add(AuditLog(
        user_id=current_user.id,
        action="create_transaction",
        resource_type="transaction",
        details=f"¥{body.amount} {cat.name} {body.handler}",
        ip_address=ip,
    ))
    db.commit()
    db.refresh(t)
    return _serialize(t)


@router.delete("/{transaction_id}")
def delete_transaction(
    transaction_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    t = db.query(Transaction).filter(Transaction.id == transaction_id).first()
    if not t:
        raise HTTPException(status_code=404, detail="记录不存在")

    t.is_deleted = True
    ip = request.client.host if request.client else "unknown"
    db.add(AuditLog(
        user_id=current_user.id,
        action="delete_transaction",
        resource_type="transaction",
        resource_id=transaction_id,
        ip_address=ip,
    ))
    db.commit()
    return {"ok": True}
