import json
from datetime import date, datetime
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional, List
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import User, TaxProfile, TaxFilingLog
from app.auth import get_current_user, require_admin
from app.utils.tax_calendar import upcoming_deadlines, TAX_TYPES, TAX_BY_CODE

router = APIRouter()


def _get_profile(db: Session) -> TaxProfile:
    p = db.query(TaxProfile).first()
    if not p:
        p = TaxProfile()
        db.add(p)
        db.commit()
        db.refresh(p)
    return p


def _profile_dict(p: TaxProfile) -> dict:
    enabled = None
    if p.enabled_taxes:
        try:
            enabled = json.loads(p.enabled_taxes)
        except Exception:
            enabled = None
    return {
        "filing_period": p.filing_period or "quarter",
        "has_employees": bool(p.has_employees),
        "has_business_income": bool(p.has_business_income),
        "enabled": enabled,
        "remind_days": p.remind_days or 7,
        "region": p.region or "",
    }


class TaxProfileBody(BaseModel):
    filing_period: str = "quarter"
    has_employees: bool = True
    has_business_income: bool = False
    enabled_taxes: Optional[List[str]] = None
    remind_days: int = 7
    region: Optional[str] = ""


@router.get("/types")
def list_tax_types(_: User = Depends(get_current_user)):
    """所有支持的税种及其法律依据。"""
    return [
        {k: v for k, v in t.items() if k != "requires"}
        for t in TAX_TYPES
    ]


@router.get("/profile")
def get_profile(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return _profile_dict(_get_profile(db))


@router.put("/profile")
def update_profile(
    body: TaxProfileBody,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    if body.filing_period not in ("month", "quarter"):
        raise HTTPException(status_code=400, detail="申报周期只能是 month 或 quarter")
    if not 0 <= body.remind_days <= 60:
        raise HTTPException(status_code=400, detail="提醒天数需在 0—60 之间")
    if body.enabled_taxes is not None:
        unknown = [c for c in body.enabled_taxes if c not in TAX_BY_CODE]
        if unknown:
            raise HTTPException(status_code=400, detail=f"未知税种：{'、'.join(unknown)}")

    p = _get_profile(db)
    p.filing_period = body.filing_period
    p.has_employees = body.has_employees
    p.has_business_income = body.has_business_income
    p.remind_days = body.remind_days
    p.region = (body.region or "").strip()
    p.enabled_taxes = json.dumps(body.enabled_taxes, ensure_ascii=False) if body.enabled_taxes is not None else None
    db.commit()
    return _profile_dict(p)


@router.get("/reminders")
def get_reminders(
    days_ahead: int = 120,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """返回申报事项列表，含状态（已申报 / 已逾期 / 紧急 / 即将到期 / 未开始）。"""
    days_ahead = max(1, min(days_ahead, 400))
    p = _get_profile(db)
    prof = _profile_dict(p)
    today = date.today()

    items = upcoming_deadlines(prof, today, days_ahead)

    filed = {
        (log.tax_code, log.period_key): log
        for log in db.query(TaxFilingLog).all()
    }

    remind_days = prof["remind_days"]
    out = []
    for it in items:
        due = date.fromisoformat(it["due_date"])
        left = (due - today).days
        log = filed.get((it["code"], it["period_key"]))

        if log:
            status = "filed"
        elif left < 0:
            status = "overdue"
        elif left <= 3:
            status = "urgent"
        elif left <= remind_days:
            status = "due_soon"
        else:
            status = "upcoming"

        it = dict(it)
        it["days_left"] = left
        it["status"] = status
        it["filed_at"] = log.filed_at.isoformat() if log else None
        it["note"] = log.note if log else None
        out.append(it)

    active = [i for i in out if i["status"] in ("overdue", "urgent", "due_soon")]
    return {
        "today": today.isoformat(),
        "remind_days": remind_days,
        "alert_count": len(active),
        "overdue_count": sum(1 for i in out if i["status"] == "overdue"),
        "items": out,
    }


class FilingBody(BaseModel):
    tax_code: str
    period_key: str
    note: Optional[str] = None


@router.post("/filed")
def mark_filed(
    body: FilingBody,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    if body.tax_code not in TAX_BY_CODE:
        raise HTTPException(status_code=400, detail="未知税种")
    existing = db.query(TaxFilingLog).filter(
        TaxFilingLog.tax_code == body.tax_code,
        TaxFilingLog.period_key == body.period_key,
    ).first()
    if existing:
        existing.note = body.note
        existing.filed_at = datetime.utcnow()
        existing.filed_by = current_user.id
    else:
        db.add(TaxFilingLog(
            tax_code=body.tax_code,
            period_key=body.period_key,
            filed_by=current_user.id,
            note=body.note,
        ))
    db.commit()
    return {"ok": True}


@router.delete("/filed")
def unmark_filed(
    tax_code: str,
    period_key: str,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    log = db.query(TaxFilingLog).filter(
        TaxFilingLog.tax_code == tax_code,
        TaxFilingLog.period_key == period_key,
    ).first()
    if log:
        db.delete(log)
        db.commit()
    return {"ok": True}
