from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from enum import Enum

class RFQStatus(str, Enum):
    AWAITING_QUOTES = "Awaiting Quotes"
    READY_FOR_REVIEW = "Ready for Review"
    WINNER_SELECTED = "Winner Selected"
    CANCELLED = "Cancelled"
    OVERDUE = "Overdue"

class RFQBase(BaseModel):
    title: str = Field(..., max_length=200)
    description: Optional[str] = None
    deadline: datetime = Field(..., future=True)
    supplier_ids: List[int] = Field(..., min_items=1)

class RFQCreate(RFQBase):
    purchase_request_id: int = Field(..., gt=0)

class RFQUpdate(BaseModel):
    title: Optional[str] = Field(None, max_length=200)
    description: Optional[str] = None
    deadline: Optional[datetime] = Field(None, future=True)

class RFQSchema(RFQBase):
    id: int
    status: RFQStatus
    purchase_request_id: int
    created_by_id: int
    winner_quote_id: Optional[int] = None
    justification: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

class RFQSupplierCreate(BaseModel):
    supplier_id: int = Field(..., gt=0)

class RFQStatusUpdate(BaseModel):
    status: RFQStatus
    winner_quote_id: Optional[int] = None
    justification: Optional[str] = None
