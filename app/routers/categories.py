from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from app.database import get_db
from app.models import Category, AuditLog, User
from app.schemas import CategoryCreate, CategoryOut
from app.auth import get_current_user, require_admin

router = APIRouter()


@router.get("/", response_model=List[CategoryOut])
def list_categories(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return db.query(Category).all()


@router.post("/", response_model=CategoryOut)
def create_category(
    body: CategoryCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    if db.query(Category).filter(Category.name == body.name).first():
        raise HTTPException(status_code=400, detail="分类名称已存在")
    cat = Category(**body.model_dump(), is_system=False)
    db.add(cat)
    db.add(AuditLog(user_id=current_user.id, action="create_category", details=body.name))
    db.commit()
    db.refresh(cat)
    return cat


@router.put("/{category_id}", response_model=CategoryOut)
def update_category(
    category_id: int,
    body: CategoryCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    cat = db.query(Category).filter(Category.id == category_id).first()
    if not cat:
        raise HTTPException(status_code=404, detail="分类不存在")
    for k, v in body.model_dump().items():
        setattr(cat, k, v)
    db.add(AuditLog(user_id=current_user.id, action="update_category", resource_id=category_id))
    db.commit()
    db.refresh(cat)
    return cat


@router.delete("/{category_id}")
def delete_category(
    category_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    cat = db.query(Category).filter(Category.id == category_id).first()
    if not cat:
        raise HTTPException(status_code=404, detail="分类不存在")
    if cat.is_system:
        raise HTTPException(status_code=400, detail="系统内置分类不可删除")
    db.delete(cat)
    db.add(AuditLog(user_id=current_user.id, action="delete_category", resource_id=category_id))
    db.commit()
    return {"ok": True}
