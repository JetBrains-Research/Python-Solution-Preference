from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime

class StageBase(BaseModel):
    name: str = Field(..., max_length=100)
    color: Optional[str] = Field("#000000", max_length=50)

class StageCreate(StageBase):
    order_index: Optional[int] = None

class StageUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=100)
    color: Optional[str] = Field(None, max_length=50)

class StageSchema(StageBase):
    id: int
    order_index: int
    is_default: bool
    created_at: datetime

    class Config:
        from_attributes = True
