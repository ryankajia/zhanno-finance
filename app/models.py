from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, Date, ForeignKey, Text
from sqlalchemy.orm import relationship
from datetime import datetime
from app.database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(10), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    role = Column(String(20), default="readonly")  # admin | readonly
    created_at = Column(DateTime, default=datetime.utcnow)

    transactions = relationship("Transaction", back_populates="creator")
    audit_logs = relationship("AuditLog", back_populates="user")


class Category(Base):
    __tablename__ = "categories"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), unique=True, nullable=False)
    description = Column(Text, nullable=True)
    color = Column(String(20), default="#3B82F6")
    category_type = Column(String(10), default="expense")  # expense | income
    is_system = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    transactions = relationship("Transaction", back_populates="category")


class Transaction(Base):
    __tablename__ = "transactions"

    id = Column(Integer, primary_key=True, index=True)
    amount = Column(Float, nullable=False)
    transaction_type = Column(String(10), default="expense")  # expense | income
    category_id = Column(Integer, ForeignKey("categories.id"), nullable=False)
    handler = Column(String(50), nullable=False)
    description = Column(Text, nullable=True)  # Fernet-encrypted
    transaction_date = Column(Date, nullable=False)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    is_deleted = Column(Boolean, default=False)

    category = relationship("Category", back_populates="transactions")
    creator = relationship("User", back_populates="transactions")


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    action = Column(String(100), nullable=False)
    resource_type = Column(String(50), nullable=True)
    resource_id = Column(Integer, nullable=True)
    details = Column(Text, nullable=True)
    ip_address = Column(String(50), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="audit_logs")


class TaxProfile(Base):
    """纳税人档案（单行配置，决定提醒哪些税种）。"""
    __tablename__ = "tax_profile"

    id = Column(Integer, primary_key=True, index=True)
    filing_period = Column(String(10), default="quarter")   # month | quarter
    has_employees = Column(Boolean, default=True)           # 是否需代扣代缴个税
    has_business_income = Column(Boolean, default=False)    # 是否有经营所得
    enabled_taxes = Column(Text, nullable=True)             # JSON 列表，空=全部
    remind_days = Column(Integer, default=7)                # 提前几天提醒
    region = Column(String(50), nullable=True)              # 备注所在省市
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class TaxFilingLog(Base):
    """某税种某所属期的申报完成记录。"""
    __tablename__ = "tax_filing_logs"

    id = Column(Integer, primary_key=True, index=True)
    tax_code = Column(String(50), nullable=False, index=True)
    period_key = Column(String(20), nullable=False, index=True)
    filed_at = Column(DateTime, default=datetime.utcnow)
    filed_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    note = Column(Text, nullable=True)
