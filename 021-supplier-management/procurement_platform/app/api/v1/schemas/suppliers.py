from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime

class SupplierBase(BaseModel):
    company_name: str = Field(..., max_length=100)
    tax_id: str = Field(..., max_length=50)
    email: str = Field(..., max_length=100)
    contact_person: Optional[str] = Field(None, max_length=100)
    phone: Optional[str] = Field(None, max_length=50)
    address: Optional[str] = None
    is_active: Optional[bool] = True
    category_ids: List[int] = Field(..., min_items=1)

class SupplierCreate(SupplierBase):
    pass

class SupplierUpdate(BaseModel):
    company_name: Optional[str] = Field(None, max_length=100)
    email: Optional[str] = Field(None, max_length=100)
    contact_person: Optional[str] = Field(None, max_length=100)
    phone: Optional[str] = Field(None, max_length=50)
    address: Optional[str] = None
    is_active: Optional[bool] = None
    category_ids: Optional[List[int]] = None

class SupplierSchema(SupplierBase):
    id: int
    punctuality_score: Optional[float] = 0
    quality_score: Optional[float] = 0
    reliability_score: Optional[float] = 0
    overall_score: Optional[float] = 0
    created_at: datetime
    updated_at: datetime
    categories: Optional[List[dict]] = None

    class Config:
        from_attributes = True

class SupplierSearch(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    category_id: Optional[int] = None
    is_active: Optional[bool] = None
    sort_by: Optional[str] = "name"
    sort_order: Optional[str] = "asc"
