from pydantic import BaseModel
from typing import Optional
from datetime import datetime
from enum import Enum

class DashboardItemType(str, Enum):
    RFQ_READY_FOR_REVIEW = "rfq_ready_for_review"
    OVERDUE_ORDER = "overdue_order"
    STALE_REQUEST = "stale_request"

class DashboardItem(BaseModel):
    item_type: DashboardItemType
    record_id: int
    title: str
    record_data: Optional[dict] = None

    class Config:
        from_attributes = True
