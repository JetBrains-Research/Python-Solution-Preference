from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime, date


# User schemas
class UserCreate(BaseModel):
    username: str
    password: str
    is_admin: bool = False


class UserUpdate(BaseModel):
    is_admin: Optional[bool] = None
    is_active: Optional[bool] = None


class UserOut(BaseModel):
    id: int
    username: str
    is_admin: bool
    is_active: bool
    created_at: datetime
    
    class Config:
        from_attributes = True


class UserLogin(BaseModel):
    username: str
    password: str


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


# Category schemas
class CategoryCreate(BaseModel):
    name: str


class CategoryUpdate(BaseModel):
    name: Optional[str] = None


class CategoryOut(BaseModel):
    id: int
    name: str
    
    class Config:
        from_attributes = True


# Stage schemas
class StageCreate(BaseModel):
    name: str
    color: str = "#cccccc"


class StageUpdate(BaseModel):
    name: Optional[str] = None
    color: Optional[str] = None
    order: Optional[int] = None


class StageOut(BaseModel):
    id: int
    name: str
    color: str
    order: int
    is_default: bool
    is_seed: bool
    
    class Config:
        from_attributes = True


# Line item schemas
class PurchaseRequestLineItemCreate(BaseModel):
    description: str
    quantity: int = Field(..., ge=1)


class PurchaseRequestLineItemOut(BaseModel):
    id: int
    description: str
    quantity: int
    
    class Config:
        from_attributes = True


# Purchase Request schemas
class PurchaseRequestCreate(BaseModel):
    title: str
    priority: str = "Medium"
    category_id: int
    deadline: Optional[datetime] = None
    notes: Optional[str] = None
    line_items: List[PurchaseRequestLineItemCreate]


class PurchaseRequestUpdate(BaseModel):
    title: Optional[str] = None
    priority: Optional[str] = None
    category_id: Optional[int] = None
    deadline: Optional[datetime] = None
    notes: Optional[str] = None
    line_items: Optional[List[PurchaseRequestLineItemCreate]] = None


class PurchaseRequestMove(BaseModel):
    stage_id: int


class PurchaseRequestOut(BaseModel):
    id: int
    title: str
    priority: str
    category_id: int
    category_name: Optional[str] = None
    deadline: Optional[datetime] = None
    notes: Optional[str] = None
    current_stage_id: int
    current_stage_name: Optional[str] = None
    created_at: datetime
    age_days: Optional[int] = None
    item_count: Optional[int] = None
    cloned_from_id: Optional[int] = None
    is_deleted: bool
    line_items: List[PurchaseRequestLineItemOut] = []
    
    class Config:
        from_attributes = True


class StageHistoryOut(BaseModel):
    id: int
    from_stage_id: Optional[int] = None
    to_stage_id: int
    timestamp: datetime
    
    class Config:
        from_attributes = True


# Supplier schemas
class SupplierCategoryCreate(BaseModel):
    category_id: int


class SupplierCreate(BaseModel):
    company_name: str
    tax_id: str
    email: str
    category_ids: List[int]


class SupplierUpdate(BaseModel):
    company_name: Optional[str] = None
    tax_id: Optional[str] = None
    email: Optional[str] = None
    category_ids: Optional[List[int]] = None
    is_active: Optional[bool] = None


class SupplierOut(BaseModel):
    id: int
    company_name: str
    tax_id: str
    email: str
    is_active: bool
    punctuality: Optional[int] = None
    quality: Optional[int] = None
    reliability: Optional[int] = None
    overall_score: Optional[int] = None
    categories: List[CategoryOut] = []
    
    class Config:
        from_attributes = True


class SupplierSearch(BaseModel):
    query: Optional[str] = None
    status: Optional[str] = None
    category_id: Optional[int] = None
    sort_by: Optional[str] = None  # name, score
    sort_order: Optional[str] = "asc"


# RFQ schemas
class RFQSupplierCreate(BaseModel):
    supplier_id: int


class RFQCreate(BaseModel):
    purchase_request_id: int
    title: str
    description: Optional[str] = None
    deadline: datetime
    supplier_ids: List[int]


class RFQUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    deadline: Optional[datetime] = None


class RFQExtendDeadline(BaseModel):
    deadline: datetime


class RFQSupplierOut(BaseModel):
    id: int
    supplier_id: int
    company_name: str
    has_submitted: bool = False
    quote_token: Optional[str] = None
    
    class Config:
        from_attributes = True


class RFQOut(BaseModel):
    id: int
    purchase_request_id: int
    title: str
    description: Optional[str] = None
    deadline: datetime
    status: str
    winner_quote_id: Optional[int] = None
    created_at: datetime
    suppliers: List[RFQSupplierOut] = []
    
    class Config:
        from_attributes = True


# Quote schemas
class QuoteLineItemCreate(BaseModel):
    request_line_item_id: int
    unit_price: float = Field(..., gt=0)
    delivery_time_days: int = Field(..., ge=1)


class QuoteLineItemOut(BaseModel):
    id: int
    request_line_item_id: int
    description: Optional[str] = None
    quantity: Optional[int] = None
    unit_price: float
    delivery_time_days: int
    line_total: Optional[float] = None
    
    class Config:
        from_attributes = True


class QuoteSubmit(BaseModel):
    line_items: List[QuoteLineItemCreate]
    payment_terms: Optional[str] = None
    notes: Optional[str] = None


class QuoteOut(BaseModel):
    id: int
    supplier_id: int
    supplier_name: Optional[str] = None
    revision_number: int
    total: Optional[float] = None
    payment_terms: Optional[str] = None
    notes: Optional[str] = None
    submitted_at: datetime
    line_items: List[QuoteLineItemOut] = []
    
    class Config:
        from_attributes = True


class QuoteComparisonOut(BaseModel):
    id: int
    supplier_id: int
    supplier_name: str
    supplier_score: Optional[int] = None
    line_items: List[QuoteLineItemOut] = []
    total: float
    delivery_time_days: int
    payment_terms: Optional[str] = None
    is_lowest: bool = False
    
    class Config:
        from_attributes = True


class WinnerSelect(BaseModel):
    quote_id: int
    justification: Optional[str] = None


# Purchase Order schemas
class PurchaseOrderOut(BaseModel):
    id: int
    order_number: str
    purchase_request_id: int
    supplier_id: int
    supplier_name: Optional[str] = None
    quote_id: int
    total: float
    payment_terms: Optional[str] = None
    expected_delivery: date
    current_status: str
    created_at: datetime
    is_overdue: Optional[bool] = None
    
    class Config:
        from_attributes = True


class OrderStatusUpdate(BaseModel):
    status: str


class PurchaseOrderStatusHistoryOut(BaseModel):
    id: int
    status: str
    timestamp: datetime
    
    class Config:
        from_attributes = True


class RatingSubmit(BaseModel):
    punctuality: int = Field(..., ge=0, le=100)
    quality: int = Field(..., ge=0, le=100)
    reliability: int = Field(..., ge=0, le=100)


# Dashboard schemas
class DashboardRFQItem(BaseModel):
    id: int
    title: str
    status: str
    type: str = "rfq_ready_for_review"


class DashboardOverdueOrderItem(BaseModel):
    id: int
    order_number: str
    supplier_name: str
    expected_delivery: date
    type: str = "overdue_order"


class DashboardStalePRItem(BaseModel):
    id: int
    title: str
    created_at: datetime
    days_in_new: int
    type: str = "stale_purchase_request"


class DashboardOut(BaseModel):
    rfqs_ready_for_review: List[DashboardRFQItem] = []
    overdue_orders: List[DashboardOverdueOrderItem] = []
    stale_purchase_requests: List[DashboardStalePRItem] = []
