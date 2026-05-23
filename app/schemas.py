from pydantic import BaseModel
from typing import Optional
from datetime import date, datetime


class UserLogin(BaseModel):
    username: str
    password: str


class PasswordChange(BaseModel):
    old_password: str
    new_password: str


class Token(BaseModel):
    access_token: str
    token_type: str
    user: dict


class CategoryBase(BaseModel):
    name: str
    description: Optional[str] = None
    color: Optional[str] = "#3B82F6"
    category_type: Optional[str] = "expense"


class CategoryCreate(CategoryBase):
    pass


class CategoryOut(CategoryBase):
    id: int
    is_system: bool
    category_type: str
    created_at: datetime

    model_config = {"from_attributes": True}


class TransactionCreate(BaseModel):
    amount: float
    transaction_type: str = "expense"
    category_id: int
    handler: str
    description: Optional[str] = None
    transaction_date: date


class AIParseRequest(BaseModel):
    text: str


class AIQueryRequest(BaseModel):
    question: str


class ReportRequest(BaseModel):
    date_from: date
    date_to: date
    transaction_type: str = "all"   # all | income | expense
    password: Optional[str] = None
