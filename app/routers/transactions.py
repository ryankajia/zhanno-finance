from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session
from sqlalchemy import extract, func
from typing import Optional, List
from pydantic import BaseModel
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
        "transaction_type": t.transaction_type or "expense",
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
    total_income = sum(t.amount for t in rows if (t.transaction_type or "expense") == "income")
    total_expense = sum(t.amount for t in rows if (t.transaction_type or "expense") == "expense")

    by_category: dict[str, float] = {}
    by_handler: dict[str, float] = {}
    max_amount = 0.0

    for t in rows:
        name = t.category.name if t.category else "未分类"
        signed = t.amount if (t.transaction_type or "expense") == "income" else -t.amount
        by_category[name] = by_category.get(name, 0) + t.amount
        by_handler[t.handler] = by_handler.get(t.handler, 0) + signed
        if t.amount > max_amount:
            max_amount = t.amount

    return {
        "total_income": total_income,
        "total_expense": total_expense,
        "net": total_income - total_expense,
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
        transaction_type=body.transaction_type,
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


class BatchDeleteBody(BaseModel):
    ids: List[int]


@router.post("/batch-delete")
def batch_delete(
    body: BatchDeleteBody,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """批量软删除账目。返回实际删除条数。"""
    if not body.ids:
        raise HTTPException(status_code=400, detail="未选择任何记录")
    if len(body.ids) > 500:
        raise HTTPException(status_code=400, detail="单次最多删除 500 条")

    rows = db.query(Transaction).filter(
        Transaction.id.in_(body.ids),
        Transaction.is_deleted == False,
    ).all()
    if not rows:
        raise HTTPException(status_code=404, detail="所选记录不存在或已删除")

    for t in rows:
        t.is_deleted = True

    ip = request.client.host if request.client else "unknown"
    db.add(AuditLog(
        user_id=current_user.id,
        action="batch_delete_transaction",
        resource_type="transaction",
        details=f"批量删除 {len(rows)} 条：{[t.id for t in rows]}",
        ip_address=ip,
    ))
    db.commit()
    return {"ok": True, "deleted": len(rows), "requested": len(body.ids)}


class BatchCreateBody(BaseModel):
    items: List[TransactionCreate]


@router.post("/batch")
def batch_create(
    body: BatchCreateBody,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """批量录入账目。任一条校验失败则整批回滚，避免录入一半。"""
    if not body.items:
        raise HTTPException(status_code=400, detail="没有要录入的记录")
    if len(body.items) > 200:
        raise HTTPException(status_code=400, detail="单次最多录入 200 条")

    valid_ids = {c.id for c in db.query(Category.id).all()}
    created = []
    for idx, item in enumerate(body.items, start=1):
        if item.amount <= 0:
            raise HTTPException(status_code=400, detail=f"第 {idx} 行：金额必须大于 0")
        if not item.handler.strip():
            raise HTTPException(status_code=400, detail=f"第 {idx} 行：经手人不能为空")
        if item.category_id not in valid_ids:
            raise HTTPException(status_code=400, detail=f"第 {idx} 行：分类不存在")

        t = Transaction(
            amount=item.amount,
            transaction_type=item.transaction_type,
            category_id=item.category_id,
            handler=item.handler.strip(),
            description=encrypt(item.description) if item.description else None,
            transaction_date=item.transaction_date,
            created_by=current_user.id,
        )
        db.add(t)
        created.append(t)

    ip = request.client.host if request.client else "unknown"
    db.add(AuditLog(
        user_id=current_user.id,
        action="batch_create_transaction",
        resource_type="transaction",
        details=f"批量录入 {len(created)} 条",
        ip_address=ip,
    ))
    db.commit()
    for t in created:
        db.refresh(t)
    return {"ok": True, "created": len(created), "items": [_serialize(t) for t in created]}
