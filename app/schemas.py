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


class CategoryCreate(CategoryBase):
    pass


class CategoryOut(CategoryBase):
    id: int
    is_system: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class TransactionCreate(BaseModel):
    amount: float
    category_id: int
    handler: str
    description: Optional[str] = None
    transaction_date: date


class AIParseRequest(BaseModel):
    text: str


class AIQueryRequest(BaseModel):
    question: str


class ReportRequest(BaseModel):
    year: int
    month: int
    password: Optional[str] = None
