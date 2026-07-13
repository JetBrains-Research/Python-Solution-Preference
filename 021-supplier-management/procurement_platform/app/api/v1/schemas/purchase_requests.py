from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from enum import Enum

class Priority(str, Enum):
    LOW = "Low"
    MEDIUM = "Medium"
    HIGH = "High"
    URGENT = "Urgent"

class LineItemBase(BaseModel):
    description: str = Field(..., max_length=200)
    quantity: float = Field(..., gt=0)
    unit: Optional[str] = Field(None, max_length=50)

class PurchaseRequestBase(BaseModel):
    title: str = Field(..., max_length=200)
    description: Optional[str] = None
    priority: Priority = Priority.MEDIUM
    deadline: Optional[datetime] = None
    notes: Optional[str] = None
    category_id: int = Field(..., gt=0)
    line_items: List[LineItemBase] = Field(..., min_items=1)

class PurchaseRequestCreate(PurchaseRequestBase):
    pass

class PurchaseRequestUpdate(BaseModel):
    title: Optional[str] = Field(None, max_length=200)
    description: Optional[str] = None
    priority: Optional[Priority] = None
    deadline: Optional[datetime] = None
    notes: Optional[str] = None
    category_id: Optional[int] = Field(None, gt=0)

class PurchaseRequestSchema(PurchaseRequestBase):
    id: int
    stage_id: int
    created_by_id: int
    created_at: datetime
    updated_at: datetime
    age: Optional[int] = None
    item_count: int
    current_stage: str

    class Config:
        from_attributes = True
