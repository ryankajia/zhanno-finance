from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import User, AuditLog
from app.schemas import UserLogin, PasswordChange, Token
from app.auth import verify_password, get_password_hash, create_access_token, get_current_user

router = APIRouter()


@router.post("/login", response_model=Token)
def login(form: UserLogin, request: Request, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == form.username).first()
    ip = request.client.host if request.client else "unknown"

    if not user or not verify_password(form.password, user.password_hash):
        db.add(AuditLog(action="login_failed", details=f"username={form.username}", ip_address=ip))
        db.commit()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户名或密码错误")

    db.add(AuditLog(user_id=user.id, action="login_success", ip_address=ip))
    db.commit()

    token = create_access_token({"sub": user.username})
    return {
        "access_token": token,
        "token_type": "bearer",
        "user": {"id": user.id, "username": user.username, "role": user.role},
    }


@router.get("/me")
def get_me(current_user: User = Depends(get_current_user)):
    return {"id": current_user.id, "username": current_user.username, "role": current_user.role}


@router.post("/change-password")
def change_password(
    body: PasswordChange,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not verify_password(body.old_password, current_user.password_hash):
        raise HTTPException(status_code=400, detail="原密码错误")
    if len(body.new_password) < 6:
        raise HTTPException(status_code=400, detail="新密码至少6位")

    current_user.password_hash = get_password_hash(body.new_password)
    ip = request.client.host if request.client else "unknown"
    db.add(AuditLog(user_id=current_user.id, action="change_password", ip_address=ip))
    db.commit()
    return {"ok": True, "message": "密码已修改"}
