from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session, joinedload
from typing import List, Optional
from datetime import datetime
from sqlalchemy import and_

from app.database import get_db
from app.database.models import (
    Order, OrderLineItem, RFQ, Quote, RFQSupplier, Category, SupplierCategory, Supplier,
    User, OrderStatus, OrderStatusHistory
)
from app.api.v1.endpoints.auth import get_current_active_user
from app.api.v1.schemas.orders import OrderSchema, OrderStatusUpdate, OrderRating

router = APIRouter()

@router.get("/", response_model=List[OrderSchema])
async def list_orders(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    orders = db.query(Order).options(
        joinedload(Order.supplier),
        joinedload(Order.rfq),
        joinedload(Order.created_by),
        joinedload(Order.line_items)
    ).all()

    result = []
    for order in orders:
        is_overdue = False
        if order.expected_delivery and order.status != OrderStatus.DELIVERED:
            is_overdue = order.expected_delivery < datetime.now()

        order_dict = {
            **order.__dict__,
            "supplier_name": order.supplier.company_name,
            "is_overdue": is_overdue
        }
        result.append(order_dict)

    return result

@router.get("/{order_id}", response_model=OrderSchema)
async def get_order(
    order_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    order = db.query(Order).filter(Order.id == order_id).options(
        joinedload(Order.supplier),
        joinedload(Order.rfq),
        joinedload(Order.created_by),
        joinedload(Order.line_items),
        joinedload(Order.status_history)
    ).first()

    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    is_overdue = False
    if order.expected_delivery and order.status != OrderStatus.DELIVERED:
        is_overdue = order.expected_delivery < datetime.now()

    order_dict = {
        **order.__dict__,
        "supplier_name": order.supplier.company_name,
        "is_overdue": is_overdue
    }

    return order_dict

@router.post("/{order_id}/advance-status")
async def advance_order_status(
    order_id: int,
    status_update: OrderStatusUpdate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    status_flow = {
        OrderStatus.PENDING: [OrderStatus.CONFIRMED],
        OrderStatus.CONFIRMED: [OrderStatus.SHIPPED],
        OrderStatus.SHIPPED: [OrderStatus.DELIVERED],
        OrderStatus.DELIVERED: []
    }

    current_status = order.status
    allowed_next_statuses = status_flow.get(current_status, [])

    if status_update.status not in allowed_next_statuses:
        raise HTTPException(status_code=400, detail=f"Cannot move from {current_status} to {status_update.status}")

    previous_status = order.status
    order.status = status_update.status

    status_history = OrderStatusHistory(
        order_id=order_id,
        previous_status=previous_status,
        new_status=status_update.status,
        changed_by_id=current_user.id,
        change_reason=status_update.change_reason
    )
    db.add(status_history)

    db.commit()
    db.refresh(order)
    return order

@router.post("/{order_id}/rate-supplier")
async def rate_supplier(
    order_id: int,
    rating_data: OrderRating,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    order = db.query(Order).filter(Order.id == order_id).options(
        joinedload(Order.supplier)
    ).first()

    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    if order.status != OrderStatus.DELIVERED:
        raise HTTPException(status_code=400, detail="Can only rate supplier after order is delivered")

    supplier = order.supplier
    supplier.punctuality_score = rating_data.punctuality
    supplier.quality_score = rating_data.quality
    supplier.reliability_score = rating_data.reliability
    supplier.overall_score = round(rating_data.punctuality * 0.35 + rating_data.quality * 0.35 + rating_data.reliability * 0.30)
    supplier.updated_at = datetime.now()

    from app.database.models import SupplierRating
    rating = SupplierRating(
        supplier_id=supplier.id,
        rated_by_id=current_user.id,
        order_id=order.id,
        punctuality=rating_data.punctuality,
        quality=rating_data.quality,
        reliability=rating_data.reliability,
        notes=rating_data.notes
    )
    db.add(rating)

    db.commit()
    db.refresh(order)
    db.refresh(supplier)

    return {"message": "Supplier rated successfully", "supplier": supplier}

@router.post("/{order_id}/clone-to-request")
async def clone_order_to_purchase_request(
    order_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    order = db.query(Order).filter(Order.id == order_id).options(
        joinedload(Order.line_items),
        joinedload(Order.supplier)
    ).first()

    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    from app.database.models import PurchaseRequest, LineItem as PRLineItem, KanbanStage
    from app.database.models import StageHistory

    category_id = order.supplier.categories[0].category_id if order.supplier.categories else None
    if not category_id:
        category = db.query(Category).first()
        category_id = category.id if category else None

    if not category_id:
        raise HTTPException(status_code=400, detail="Cannot determine category for cloned request")

    default_stage = db.query(KanbanStage).filter(KanbanStage.name == "New").first()
    if not default_stage:
        raise HTTPException(status_code=500, detail="Default stage not found")

    request = PurchaseRequest(
        title=f"Re-order from {order.order_number}",
        description=f"Cloned from order {order.order_number}",
        priority="Medium",
        deadline=None,
        notes=f"Re-ordering items from {order.order_number}",
        category_id=category_id,
        stage_id=default_stage.id,
        created_by_id=current_user.id
    )
    db.add(request)
    db.commit()
    db.refresh(request)

    for line_item in order.line_items:
        pr_line_item = PRLineItem(
            description=line_item.description,
            quantity=line_item.quantity,
            unit=line_item.unit,
            purchase_request_id=request.id
        )
        db.add(pr_line_item)

    db.commit()

    stage_history = StageHistory(
        purchase_request_id=request.id,
        previous_stage_id=None,
        new_stage_id=default_stage.id,
        changed_by_id=current_user.id,
        change_reason="Cloned from order"
    )
    db.add(stage_history)
    db.commit()
    db.refresh(request)

    return {"message": "Purchase request created from order", "request_id": request.id}
