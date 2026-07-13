from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime
from enum import Enum

class OrderStatus(str, Enum):
    PENDING = "Pending"
    CONFIRMED = "Confirmed"
    SHIPPED = "Shipped"
    DELIVERED = "Delivered"

class OrderBase(BaseModel):
    order_number: Optional[str] = Field(None, max_length=50)
    expected_delivery: datetime
    payment_terms: str = Field(..., max_length=200)
    total_amount: float = Field(..., gt=0)

class OrderSchema(OrderBase):
    id: int
    supplier_id: int
    rfq_id: int
    status: OrderStatus
    created_by_id: int
    created_at: datetime
    updated_at: datetime
    supplier_name: Optional[str] = None
    is_overdue: bool = False

    class Config:
        from_attributes = True

class OrderStatusUpdate(BaseModel):
    status: OrderStatus
    change_reason: Optional[str] = None

class OrderRating(BaseModel):
    punctuality: int = Field(..., ge=0, le=100)
    quality: int = Field(..., ge=0, le=100)
    reliability: int = Field(..., ge=0, le=100)
    notes: Optional[str] = None
