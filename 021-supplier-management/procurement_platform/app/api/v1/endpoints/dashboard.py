from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from typing import List
from datetime import datetime, timedelta

from app.database import get_db
from app.database.models import RFQ, RFQStatus, RFQSupplier, Order, OrderStatus, PurchaseRequest, KanbanStage, User
from app.api.v1.endpoints.auth import get_current_active_user
from app.api.v1.schemas.dashboard import DashboardItem, DashboardItemType

router = APIRouter()

@router.get("/", response_model=List[DashboardItem])
async def get_dashboard(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    dashboard_items = []

    rfqs_ready_for_review = db.query(RFQ).filter(RFQ.status == RFQStatus.READY_FOR_REVIEW).all()
    for rfq in rfqs_ready_for_review:
        dashboard_items.append(DashboardItem(
            item_type=DashboardItemType.RFQ_READY_FOR_REVIEW,
            record_id=rfq.id,
            title=f"RFQ: {rfq.title} ready for review",
            record_data={"rfq_id": rfq.id, "title": rfq.title, "deadline": str(rfq.deadline)}
        ))

    overdue_orders = db.query(Order).filter(
        Order.expected_delivery < datetime.now(),
        Order.status != OrderStatus.DELIVERED
    ).all()

    for order in overdue_orders:
        dashboard_items.append(DashboardItem(
            item_type=DashboardItemType.OVERDUE_ORDER,
            record_id=order.id,
            title=f"Order {order.order_number} is overdue",
            record_data={"order_id": order.id, "order_number": order.order_number, "supplier_id": order.supplier_id}
        ))

    new_stage = db.query(KanbanStage).filter(KanbanStage.name == "New").first()
    if new_stage:
        stale_threshold = datetime.now() - timedelta(days=7)
        stale_requests = db.query(PurchaseRequest).filter(
            PurchaseRequest.stage_id == new_stage.id,
            PurchaseRequest.created_at < stale_threshold
        ).all()

        for pr in stale_requests:
            age = (datetime.now() - pr.created_at).days
            dashboard_items.append(DashboardItem(
                item_type=DashboardItemType.STALE_REQUEST,
                record_id=pr.id,
                title=f"Purchase request {pr.title} stale in New stage",
                record_data={"request_id": pr.id, "title": pr.title, "age": age}
            ))

    return dashboard_items
