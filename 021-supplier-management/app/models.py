from sqlalchemy import Column, Integer, String, Float, DateTime, Boolean, ForeignKey, Text, Date, UniqueConstraint
from sqlalchemy.orm import relationship
from app.database import Base
import datetime


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, nullable=False)
    password_hash = Column(String, nullable=False)
    is_admin = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)


class Category(Base):
    __tablename__ = "categories"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    requests = relationship("PurchaseRequest", back_populates="category")
    suppliers = relationship("SupplierCategory", back_populates="category")


class Stage(Base):
    __tablename__ = "stages"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    color = Column(String, default="#cccccc")
    order = Column(Integer, nullable=False, default=0)
    is_default = Column(Boolean, default=False)
    is_seed = Column(Boolean, default=False)


class PurchaseRequest(Base):
    __tablename__ = "purchase_requests"
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, nullable=False)
    priority = Column(String, default="Medium")  # Low, Medium, High, Urgent
    category_id = Column(Integer, ForeignKey("categories.id"), nullable=False)
    deadline = Column(DateTime, nullable=True)
    notes = Column(Text, nullable=True)
    current_stage_id = Column(Integer, ForeignKey("stages.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    cloned_from_id = Column(Integer, ForeignKey("purchase_requests.id"), nullable=True)
    is_deleted = Column(Boolean, default=False)
    
    category = relationship("Category", back_populates="requests")
    line_items = relationship("PurchaseRequestLineItem", back_populates="request", cascade="all, delete-orphan")
    rfqs = relationship("RFQ", back_populates="purchase_request")
    stage_history = relationship("StageHistory", back_populates="request", cascade="all, delete-orphan")
    orders = relationship("PurchaseOrder", back_populates="purchase_request")


class PurchaseRequestLineItem(Base):
    __tablename__ = "purchase_request_line_items"
    id = Column(Integer, primary_key=True, index=True)
    request_id = Column(Integer, ForeignKey("purchase_requests.id"), nullable=False)
    description = Column(String, nullable=False)
    quantity = Column(Integer, nullable=False)
    
    request = relationship("PurchaseRequest", back_populates="line_items")


class StageHistory(Base):
    __tablename__ = "stage_history"
    id = Column(Integer, primary_key=True, index=True)
    request_id = Column(Integer, ForeignKey("purchase_requests.id"), nullable=False)
    from_stage_id = Column(Integer, ForeignKey("stages.id"), nullable=True)
    to_stage_id = Column(Integer, ForeignKey("stages.id"), nullable=False)
    timestamp = Column(DateTime, default=datetime.datetime.utcnow)
    
    request = relationship("PurchaseRequest", back_populates="stage_history")


class Supplier(Base):
    __tablename__ = "suppliers"
    id = Column(Integer, primary_key=True, index=True)
    company_name = Column(String, nullable=False)
    tax_id = Column(String, unique=True, nullable=False)
    email = Column(String, unique=True, nullable=False)
    is_active = Column(Boolean, default=True)
    punctuality = Column(Integer, nullable=True)
    quality = Column(Integer, nullable=True)
    reliability = Column(Integer, nullable=True)
    
    categories = relationship("SupplierCategory", back_populates="supplier", cascade="all, delete-orphan")
    rfq_invitations = relationship("RFQSupplier", back_populates="supplier")
    quotes = relationship("Quote", back_populates="supplier")
    orders = relationship("PurchaseOrder", back_populates="supplier")


class SupplierCategory(Base):
    __tablename__ = "supplier_categories"
    id = Column(Integer, primary_key=True, index=True)
    supplier_id = Column(Integer, ForeignKey("suppliers.id"), nullable=False)
    category_id = Column(Integer, ForeignKey("categories.id"), nullable=False)
    
    supplier = relationship("Supplier", back_populates="categories")
    category = relationship("Category", back_populates="suppliers")


class RFQ(Base):
    __tablename__ = "rfqs"
    id = Column(Integer, primary_key=True, index=True)
    purchase_request_id = Column(Integer, ForeignKey("purchase_requests.id"), nullable=False)
    title = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    deadline = Column(DateTime, nullable=False)
    status = Column(String, default="Awaiting Quotes")  # Awaiting Quotes, Ready for Review, Winner Selected, Cancelled, Overdue
    winner_quote_id = Column(Integer, ForeignKey("quotes.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    
    purchase_request = relationship("PurchaseRequest", back_populates="rfqs")
    suppliers = relationship("RFQSupplier", back_populates="rfq", cascade="all, delete-orphan")
    quotes = relationship("Quote", back_populates="rfq", foreign_keys="Quote.rfq_id", cascade="all, delete-orphan")
    winner_quote = relationship("Quote", foreign_keys=[winner_quote_id])


class RFQSupplier(Base):
    __tablename__ = "rfq_suppliers"
    id = Column(Integer, primary_key=True, index=True)
    rfq_id = Column(Integer, ForeignKey("rfqs.id"), nullable=False)
    supplier_id = Column(Integer, ForeignKey("suppliers.id"), nullable=False)
    quote_token = Column(String, unique=True, nullable=False)
    
    rfq = relationship("RFQ", back_populates="suppliers")
    supplier = relationship("Supplier", back_populates="rfq_invitations")


class Quote(Base):
    __tablename__ = "quotes"
    id = Column(Integer, primary_key=True, index=True)
    rfq_id = Column(Integer, ForeignKey("rfqs.id"), nullable=False)
    supplier_id = Column(Integer, ForeignKey("suppliers.id"), nullable=False)
    revision_number = Column(Integer, default=1)
    payment_terms = Column(String, nullable=True)
    notes = Column(Text, nullable=True)
    submitted_at = Column(DateTime, default=datetime.datetime.utcnow)
    
    rfq = relationship("RFQ", back_populates="quotes", foreign_keys=[rfq_id])
    supplier = relationship("Supplier", back_populates="quotes")
    line_items = relationship("QuoteLineItem", back_populates="quote", cascade="all, delete-orphan")


class QuoteLineItem(Base):
    __tablename__ = "quote_line_items"
    id = Column(Integer, primary_key=True, index=True)
    quote_id = Column(Integer, ForeignKey("quotes.id"), nullable=False)
    request_line_item_id = Column(Integer, ForeignKey("purchase_request_line_items.id"), nullable=False)
    unit_price = Column(Float, nullable=False)
    delivery_time_days = Column(Integer, nullable=False)
    
    quote = relationship("Quote", back_populates="line_items")
    request_line_item = relationship("PurchaseRequestLineItem")


class PurchaseOrder(Base):
    __tablename__ = "purchase_orders"
    id = Column(Integer, primary_key=True, index=True)
    order_number = Column(String, unique=True, nullable=False)
    purchase_request_id = Column(Integer, ForeignKey("purchase_requests.id"), nullable=False)
    supplier_id = Column(Integer, ForeignKey("suppliers.id"), nullable=False)
    quote_id = Column(Integer, ForeignKey("quotes.id"), nullable=False)
    total = Column(Float, nullable=False)
    payment_terms = Column(String, nullable=True)
    expected_delivery = Column(Date, nullable=False)
    current_status = Column(String, default="Pending")  # Pending, Confirmed, Shipped, Delivered
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    
    purchase_request = relationship("PurchaseRequest", back_populates="orders")
    supplier = relationship("Supplier", back_populates="orders")
    quote = relationship("Quote")
    status_history = relationship("OrderStatusHistory", back_populates="order", cascade="all, delete-orphan")


class OrderStatusHistory(Base):
    __tablename__ = "order_status_history"
    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(Integer, ForeignKey("purchase_orders.id"), nullable=False)
    status = Column(String, nullable=False)
    timestamp = Column(DateTime, default=datetime.datetime.utcnow)
    
    order = relationship("PurchaseOrder", back_populates="status_history")
