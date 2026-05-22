from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from app.database import get_db
from app.models import User
from app.auth import get_password_hash, require_admin

router = APIRouter()


class UserCreate(BaseModel):
    username: str
    password: str
    role: str = "readonly"  # admin | readonly


class UserPasswordReset(BaseModel):
    new_password: str


@router.get("/")
def list_users(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    users = db.query(User).order_by(User.id).all()
    return [
        {"id": u.id, "username": u.username, "role": u.role, "created_at": u.created_at}
        for u in users
    ]


@router.post("/")
def create_user(body: UserCreate, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    if len(body.username.strip()) < 2:
        raise HTTPException(status_code=400, detail="用户名至少2个字符")
    if len(body.password) < 6:
        raise HTTPException(status_code=400, detail="密码至少6位")
    if body.role not in ("admin", "readonly"):
        raise HTTPException(status_code=400, detail="角色只能是 admin 或 readonly")
    if db.query(User).filter(User.username == body.username.strip()).first():
        raise HTTPException(status_code=400, detail="用户名已存在")

    user = User(
        username=body.username.strip(),
        password_hash=get_password_hash(body.password),
        role=body.role,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return {"id": user.id, "username": user.username, "role": user.role}


@router.put("/{user_id}/password")
def reset_password(
    user_id: int,
    body: UserPasswordReset,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    if len(body.new_password) < 6:
        raise HTTPException(status_code=400, detail="密码至少6位")
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    user.password_hash = get_password_hash(body.new_password)
    db.commit()
    return {"ok": True}


@router.put("/{user_id}/role")
def update_role(
    user_id: int,
    body: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    role = body.get("role")
    if role not in ("admin", "readonly"):
        raise HTTPException(status_code=400, detail="角色只能是 admin 或 readonly")
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    if user.id == current_user.id:
        raise HTTPException(status_code=400, detail="不能修改自己的角色")
    user.role = role
    db.commit()
    return {"ok": True}


@router.delete("/{user_id}")
def delete_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    if user_id == current_user.id:
        raise HTTPException(status_code=400, detail="不能删除当前登录账号")
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    if db.query(User).count() <= 1:
        raise HTTPException(status_code=400, detail="系统至少保留一个账号")
    db.delete(user)
    db.commit()
    return {"ok": True}
