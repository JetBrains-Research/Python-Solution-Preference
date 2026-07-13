from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime

class QuoteItemBase(BaseModel):
    line_item_id: int = Field(..., gt=0)
    unit_price: float = Field(..., gt=0)

class QuoteBase(BaseModel):
    delivery_time_days: int = Field(..., ge=1)
    payment_terms: str = Field(..., max_length=200)
    notes: Optional[str] = None
    quote_items: List[QuoteItemBase] = Field(..., min_items=1)

class QuoteCreate(QuoteBase):
    quote_submission_token: str = Field(..., min_length=1)

class QuoteUpdate(BaseModel):
    delivery_time_days: Optional[int] = Field(None, ge=1)
    payment_terms: Optional[str] = Field(None, max_length=200)
    notes: Optional[str] = None
    quote_items: Optional[List[QuoteItemBase]] = None

class QuoteSchema(QuoteBase):
    id: int
    rfq_supplier_id: int
    rfq_id: int
    revision_number: int
    unit_price_total: float
    submission_reference: str
    supplier_name: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

class QuoteItemSchema(QuoteItemBase):
    id: int
    quote_id: int
    created_at: datetime

    class Config:
        from_attributes = True
