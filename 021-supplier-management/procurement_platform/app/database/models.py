from sqlalchemy import Column, Integer, String, Boolean, ForeignKey, DateTime, Float, Text, Enum
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from datetime import datetime, timedelta
import enum

from .base import Base

class UserRole(str, enum.Enum):
    ADMIN = "Admin"
    BUYER = "Buyer"

class Priority(str, enum.Enum):
    LOW = "Low"
    MEDIUM = "Medium"
    HIGH = "High"
    URGENT = "Urgent"

class RFQStatus(str, enum.Enum):
    AWAITING_QUOTES = "Awaiting Quotes"
    READY_FOR_REVIEW = "Ready for Review"
    WINNER_SELECTED = "Winner Selected"
    CANCELLED = "Cancelled"
    OVERDUE = "Overdue"

class OrderStatus(str, enum.Enum):
    PENDING = "Pending"
    CONFIRMED = "Confirmed"
    SHIPPED = "Shipped"
    DELIVERED = "Delivered"

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    email = Column(String(100), unique=True, nullable=False)
    full_name = Column(String(100))
    is_active = Column(Boolean, default=True)
    role = Column(Enum(UserRole), default=UserRole.BUYER)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

class Category(Base):
    __tablename__ = "categories"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), unique=True, nullable=False)
    description = Column(Text)
    created_at = Column(DateTime, default=func.now())

class KanbanStage(Base):
    __tablename__ = "kanban_stages"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    color = Column(String(50), default="#000000")
    order_index = Column(Integer, default=0)
    is_default = Column(Boolean, default=False)
    created_at = Column(DateTime, default=func.now())

class Supplier(Base):
    __tablename__ = "suppliers"
    id = Column(Integer, primary_key=True, index=True)
    company_name = Column(String(100), nullable=False)
    tax_id = Column(String(50), unique=True, nullable=False)
    email = Column(String(100), unique=True, nullable=False)
    contact_person = Column(String(100))
    phone = Column(String(50))
    address = Column(Text)
    is_active = Column(Boolean, default=True)
    punctuality_score = Column(Float, default=0)
    quality_score = Column(Float, default=0)
    reliability_score = Column(Float, default=0)
    overall_score = Column(Float, default=0)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

class SupplierCategory(Base):
    __tablename__ = "supplier_categories"
    id = Column(Integer, primary_key=True, index=True)
    supplier_id = Column(Integer, ForeignKey("suppliers.id"), nullable=False)
    category_id = Column(Integer, ForeignKey("categories.id"), nullable=False)

class PurchaseRequest(Base):
    __tablename__ = "purchase_requests"
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(200), nullable=False)
    description = Column(Text)
    priority = Column(Enum(Priority), default=Priority.MEDIUM)
    deadline = Column(DateTime)
    notes = Column(Text)
    category_id = Column(Integer, ForeignKey("categories.id"))
    stage_id = Column(Integer, ForeignKey("kanban_stages.id"))
    created_by_id = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

class LineItem(Base):
    __tablename__ = "line_items"
    id = Column(Integer, primary_key=True, index=True)
    description = Column(String(200), nullable=False)
    quantity = Column(Float, nullable=False, default=1)
    unit = Column(String(50))
    purchase_request_id = Column(Integer, ForeignKey("purchase_requests.id"))
    created_at = Column(DateTime, default=func.now())

class RFQ(Base):
    __tablename__ = "rfqs"
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(200), nullable=False)
    description = Column(Text)
    deadline = Column(DateTime, nullable=False)
    status = Column(Enum(RFQStatus), default=RFQStatus.AWAITING_QUOTES)
    purchase_request_id = Column(Integer, ForeignKey("purchase_requests.id"))
    created_by_id = Column(Integer, ForeignKey("users.id"))
    winner_quote_id = Column(Integer, ForeignKey("quotes.id"))
    justification = Column(Text)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

class RFQSupplier(Base):
    __tablename__ = "rfq_suppliers"
    id = Column(Integer, primary_key=True, index=True)
    rfq_id = Column(Integer, ForeignKey("rfqs.id"), nullable=False)
    supplier_id = Column(Integer, ForeignKey("suppliers.id"), nullable=False)
    quote_submission_token = Column(String(64), unique=True, nullable=False)
    has_submitted = Column(Boolean, default=False)

class Quote(Base):
    __tablename__ = "quotes"
    id = Column(Integer, primary_key=True, index=True)
    rfq_supplier_id = Column(Integer, ForeignKey("rfq_suppliers.id"), nullable=False)
    rfq_id = Column(Integer, ForeignKey("rfqs.id"), nullable=False)
    revision_number = Column(Integer, default=1)
    unit_price_total = Column(Float, default=0)
    delivery_time_days = Column(Integer, nullable=False)
    payment_terms = Column(String(200))
    notes = Column(Text)
    submission_reference = Column(String(50), unique=True)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

class QuoteItem(Base):
    __tablename__ = "quote_items"
    id = Column(Integer, primary_key=True, index=True)
    quote_id = Column(Integer, ForeignKey("quotes.id"), nullable=False)
    line_item_id = Column(Integer, ForeignKey("line_items.id"), nullable=False)
    unit_price = Column(Float, nullable=False)
    created_at = Column(DateTime, default=func.now())

class Order(Base):
    __tablename__ = "orders"
    id = Column(Integer, primary_key=True, index=True)
    order_number = Column(String(50), unique=True, nullable=False)
    supplier_id = Column(Integer, ForeignKey("suppliers.id"), nullable=False)
    rfq_id = Column(Integer, ForeignKey("rfqs.id"), nullable=False)
    expected_delivery = Column(DateTime)
    payment_terms = Column(String(200))
    total_amount = Column(Float, default=0)
    status = Column(Enum(OrderStatus), default=OrderStatus.PENDING)
    created_by_id = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

class OrderLineItem(Base):
    __tablename__ = "order_line_items"
    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=False)
    description = Column(String(200), nullable=False)
    quantity = Column(Float, nullable=False)
    unit = Column(String(50))
    unit_price = Column(Float, nullable=False)
    created_at = Column(DateTime, default=func.now())

class StageHistory(Base):
    __tablename__ = "stage_history"
    id = Column(Integer, primary_key=True, index=True)
    purchase_request_id = Column(Integer, ForeignKey("purchase_requests.id"), nullable=False)
    previous_stage_id = Column(Integer, ForeignKey("kanban_stages.id"))
    new_stage_id = Column(Integer, ForeignKey("kanban_stages.id"), nullable=False)
    changed_by_id = Column(Integer, ForeignKey("users.id"))
    change_reason = Column(Text)
    created_at = Column(DateTime, default=func.now())

class OrderStatusHistory(Base):
    __tablename__ = "order_status_history"
    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=False)
    previous_status = Column(Enum(OrderStatus))
    new_status = Column(Enum(OrderStatus), nullable=False)
    changed_by_id = Column(Integer, ForeignKey("users.id"))
    change_reason = Column(Text)
    created_at = Column(DateTime, default=func.now())

class SupplierRating(Base):
    __tablename__ = "supplier_ratings"
    id = Column(Integer, primary_key=True, index=True)
    supplier_id = Column(Integer, ForeignKey("suppliers.id"), nullable=False)
    rated_by_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=False)
    punctuality = Column(Integer, nullable=False)
    quality = Column(Integer, nullable=False)
    reliability = Column(Integer, nullable=False)
    notes = Column(Text)
    created_at = Column(DateTime, default=func.now())
