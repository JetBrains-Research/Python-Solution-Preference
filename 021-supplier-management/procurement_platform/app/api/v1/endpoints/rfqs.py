from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session, joinedload
from typing import List, Optional
from datetime import datetime, timedelta
from sqlalchemy import or_, and_, func, desc
import secrets

from app.database import get_db
from app.database.models import (
    PurchaseRequest, RFQ, RFQStatus, RFQSupplier, Supplier,
    SupplierCategory, Category, StageHistory, KanbanStage, Quote, User
)
from app.api.v1.endpoints.auth import get_current_active_user
from app.api.v1.schemas.rfqs import RFQCreate, RFQUpdate, RFQSchema, RFQStatusUpdate

router = APIRouter()

def create_quote_token():
    return secrets.token_hex(32)

async def handle_automatic_stage_movement(db: Session, rfq: RFQ, new_status: str = None):
    new_stage = db.query(KanbanStage).filter(KanbanStage.name == "In Review").first()
    approved_stage = db.query(KanbanStage).filter(KanbanStage.name == "Approved").first()
    ordered_stage = db.query(KanbanStage).filter(KanbanStage.name == "Ordered").first()
    new_stage_default = db.query(KanbanStage).filter(KanbanStage.name == "New").first()

    if not new_stage or not new_stage_default:
        return

    if new_status == RFQStatus.CANCELLED.value and rfq.purchase_request:
        rfq.purchase_request.stage_id = new_stage_default.id
        stage_history = StageHistory(
            purchase_request_id=rfq.purchase_request.id,
            previous_stage_id=rfq.purchase_request.stage_id,
            new_stage_id=new_stage_default.id,
            change_reason="RFQ cancelled - returned to New"
        )
        db.add(stage_history)

    elif new_status == RFQStatus.AWAITING_QUOTES.value and rfq.purchase_request and rfq.purchase_request.stage_id != new_stage.id:
        rfq.purchase_request.stage_id = new_stage.id
        stage_history = StageHistory(
            purchase_request_id=rfq.purchase_request.id,
            previous_stage_id=rfq.purchase_request.stage_id,
            new_stage_id=new_stage.id,
            change_reason="RFQ published - moved to In Review"
        )
        db.add(stage_history)

    elif new_status == RFQStatus.WINNER_SELECTED.value and rfq.purchase_request:
        rfq.purchase_request.stage_id = approved_stage.id
        stage_history1 = StageHistory(
            purchase_request_id=rfq.purchase_request.id,
            previous_stage_id=rfq.purchase_request.stage_id,
            new_stage_id=approved_stage.id,
            change_reason="Winner selected - moved to Approved"
        )
        db.add(stage_history1)

        from app.database.models import Order, OrderLineItem, OrderStatus
        from datetime import datetime, timedelta

        winner_quote = db.query(Quote).filter(Quote.id == rfq.winner_quote_id).first()
        if winner_quote and winner_quote.rfq_supplier:
            order_number = f"PO-{datetime.now().strftime('%Y')}-{rfq.id:04d}"
            expected_delivery = datetime.now() + timedelta(days=winner_quote.delivery_time_days)

            order = Order(
                order_number=order_number,
                supplier_id=winner_quote.rfq_supplier.supplier_id,
                rfq_id=rfq.id,
                expected_delivery=expected_delivery,
                payment_terms=winner_quote.payment_terms,
                total_amount=winner_quote.unit_price_total,
                status=OrderStatus.PENDING,
                created_by_id=rfq.created_by_id
            )
            db.add(order)
            db.commit()
            db.refresh(order)

            for quote_item in winner_quote.quote_items:
                order_line_item = OrderLineItem(
                    order_id=order.id,
                    description=quote_item.line_item.description,
                    quantity=quote_item.line_item.quantity,
                    unit=quote_item.line_item.unit,
                    unit_price=quote_item.unit_price
                )
                db.add(order_line_item)

            rfq.purchase_request.stage_id = ordered_stage.id
            stage_history2 = StageHistory(
                purchase_request_id=rfq.purchase_request.id,
                previous_stage_id=approved_stage.id,
                new_stage_id=ordered_stage.id,
                change_reason="Order auto-created - moved to Ordered"
            )
            db.add(stage_history2)
            db.commit()

@router.get("/", response_model=List[RFQSchema])
async def list_rfqs(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    rfqs = db.query(RFQ).options(
        joinedload(RFQ.purchase_request),
        joinedload(RFQ.created_by),
        joinedload(RFQ.winner_quote),
        joinedload(RFQ.suppliers).joinedload(RFQSupplier.supplier)
    ).all()
    return rfqs

@router.get("/{rfq_id}", response_model=RFQSchema)
async def get_rfq(
    rfq_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    rfq = db.query(RFQ).filter(RFQ.id == rfq_id).options(
        joinedload(RFQ.purchase_request),
        joinedload(RFQ.created_by),
        joinedload(RFQ.winner_quote),
        joinedload(RFQ.suppliers).joinedload(RFQSupplier.supplier),
        joinedload(RFQ.quotes).joinedload(Quote.quote_items)
    ).first()

    if not rfq:
        raise HTTPException(status_code=404, detail="RFQ not found")

    return rfq

@router.post("/", response_model=RFQSchema)
async def create_rfq(
    rfq_data: RFQCreate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    purchase_request = db.query(PurchaseRequest).filter(PurchaseRequest.id == rfq_data.purchase_request_id).first()
    if not purchase_request:
        raise HTTPException(status_code=404, detail="Purchase request not found")

    existing_active_rfq = db.query(RFQ).filter(
        RFQ.purchase_request_id == rfq_data.purchase_request_id,
        RFQ.status.notin_([RFQStatus.CANCELLED, RFQStatus.WINNER_SELECTED])
    ).first()

    if existing_active_rfq:
        raise HTTPException(status_code=400, detail="Active RFQ already exists for this purchase request")

    rfq = RFQ(
        title=rfq_data.title,
        description=rfq_data.description,
        deadline=rfq_data.deadline,
        status=RFQStatus.AWAITING_QUOTES,
        purchase_request_id=rfq_data.purchase_request_id,
        created_by_id=current_user.id
    )
    db.add(rfq)
    db.commit()
    db.refresh(rfq)

    for supplier_id in rfq_data.supplier_ids:
        supplier = db.query(Supplier).filter(Supplier.id == supplier_id).first()
        if not supplier:
            raise HTTPException(status_code=404, detail=f"Supplier {supplier_id} not found")

        quote_token = create_quote_token()
        rfq_supplier = RFQSupplier(
            rfq_id=rfq.id,
            supplier_id=supplier_id,
            quote_submission_token=quote_token,
            has_submitted=False
        )
        db.add(rfq_supplier)

    db.commit()
    db.refresh(rfq)

    await handle_automatic_stage_movement(db, rfq, RFQStatus.AWAITING_QUOTES.value)

    return rfq

@router.put("/{rfq_id}", response_model=RFQSchema)
async def update_rfq(
    rfq_id: int,
    rfq_data: RFQUpdate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    rfq = db.query(RFQ).filter(RFQ.id == rfq_id).options(
        joinedload(RFQ.purchase_request),
        joinedload(RFQ.suppliers)
    ).first()

    if not rfq:
        raise HTTPException(status_code=404, detail="RFQ not found")

    if rfq.status == RFQStatus.CANCELLED or rfq.status == RFQStatus.WINNER_SELECTED:
        raise HTTPException(status_code=400, detail="RFQ cannot be edited in this status")

    if rfq.status == RFQStatus.READY_FOR_REVIEW:
        raise HTTPException(status_code=400, detail="Cannot edit RFQ ready for review, only winner selection allowed")

    if rfq.status == RFQStatus.OVERDUE:
        raise HTTPException(status_code=400, detail="Cannot edit overdue RFQ, only winner selection allowed")

    quotes_count = db.query(RFQSupplier).filter(
        RFQSupplier.rfq_id == rfq_id,
        RFQSupplier.has_submitted == True
    ).count()

    if quotes_count > 0 and rfq_data.title:
        raise HTTPException(status_code=400, detail="Cannot edit title after quotes submitted")

    if quotes_count > 0 and rfq_data.description:
        raise HTTPException(status_code=400, detail="Cannot edit description after quotes submitted")

    if quotes_count == 0:
        update_data = rfq_data.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            setattr(rfq, key, value)

    elif quotes_count > 0:
        if rfq_data.deadline:
            rfq.deadline = rfq_data.deadline
        else:
            pass

    rfq.updated_at = func.now()
    db.commit()
    db.refresh(rfq)

    return rfq

@router.post("/{rfq_id}/cancel", response_model=RFQSchema)
async def cancel_rfq(
    rfq_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    rfq = db.query(RFQ).filter(RFQ.id == rfq_id).options(
        joinedload(RFQ.purchase_request)
    ).first()

    if not rfq:
        raise HTTPException(status_code=404, detail="RFQ not found")

    if rfq.status == RFQStatus.CANCELLED or rfq.status == RFQStatus.WINNER_SELECTED:
        raise HTTPException(status_code=400, detail="RFQ cannot be cancelled in this status")

    rfq.status = RFQStatus.CANCELLED
    db.commit()

    await handle_automatic_stage_movement(db, rfq, RFQStatus.CANCELLED.value)

    return rfq

@router.post("/{rfq_id}/select-winner")
async def select_winner(
    rfq_id: int,
    status_update: RFQStatusUpdate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    rfq = db.query(RFQ).filter(RFQ.id == rfq_id).options(
        joinedload(RFQ.purchase_request),
        joinedload(RFQ.quotes)
    ).first()

    if not rfq:
        raise HTTPException(status_code=404, detail="RFQ not found")

    if rfq.status not in [RFQStatus.READY_FOR_REVIEW, RFQStatus.OVERDUE]:
        raise HTTPException(status_code=400, detail="Winner selection only allowed for RFQs ready for review or overdue")

    if not status_update.winner_quote_id:
        raise HTTPException(status_code=400, detail="Winner quote ID is required")

    winner_quote = db.query(Quote).filter(Quote.id == status_update.winner_quote_id).first()
    if not winner_quote:
        raise HTTPException(status_code=404, detail="Winner quote not found")

    if winner_quote.rfq_id != rfq_id:
        raise HTTPException(status_code=400, detail="Winner quote does not belong to this RFQ")

    quotes = db.query(Quote).filter(Quote.rfq_id == rfq_id).all()
    quote_totals = []

    for quote in quotes:
        total = sum(qt.unit_price * qt.line_item.quantity for qt in quote.quote_items)
        quote_totals.append((quote.id, total))

    quote_totals.sort(key=lambda x: x[1])
    lowest_quote_id = quote_totals[0][0] if quote_totals else None

    if status_update.winner_quote_id != lowest_quote_id and not status_update.justification:
        raise HTTPException(status_code=400, detail="Justification required for non-lowest quote selection")

    rfq.winner_quote_id = status_update.winner_quote_id
    rfq.justification = status_update.justification
    rfq.status = RFQStatus.WINNER_SELECTED
    rfq.updated_at = func.now()

    db.commit()
    db.refresh(rfq)

    await handle_automatic_stage_movement(db, rfq, RFQStatus.WINNER_SELECTED.value)

    return rfq
