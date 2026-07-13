from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session, joinedload
from typing import Optional
from datetime import datetime, timedelta
from sqlalchemy import and_, or_

from app.database import get_db
from app.database.models import (
    RFQ, Quote, QuoteItem, RFQSupplier, LineItem, RFQStatus, Supplier, Quote
)
from app.api.v1.schemas.quotes import QuoteCreate, QuoteUpdate, QuoteSchema
from app.api.v1.endpoints.auth import get_current_active_user, User

router = APIRouter()

@router.get("/rfq/{quote_token}", response_model=dict)
async def get_rfq_by_token(
    quote_token: str,
    db: Session = Depends(get_db)
):
    rfq_supplier = db.query(RFQSupplier).filter(RFQSupplier.quote_submission_token == quote_token).first()
    if not rfq_supplier:
        raise HTTPException(status_code=404, detail="Invalid quote token")

    rfq = db.query(RFQ).filter(RFQ.id == rfq_supplier.rfq_id).options(
        joinedload(RFQ.purchase_request).joinedload("line_items")
    ).first()

    if not rfq:
        raise HTTPException(status_code=404, detail="RFQ not found")

    supplier = db.query(Supplier).filter(Supplier.id == rfq_supplier.supplier_id).first()

    result = {
        "rfq_title": rfq.title,
        "rfq_description": rfq.description,
        "rfq_deadline": rfq.deadline,
        "company_name": supplier.company_name,
        "line_items": [{"description": li.description, "quantity": li.quantity, "unit": li.unit} for li in rfq.purchase_request.line_items],
        "has_submitted": rfq_supplier.has_submitted
    }

    if rfq.status in [RFQStatus.CANCELLED, RFQStatus.WINNER_SELECTED]:
        result["blocked"] = True
        result["reason"] = "RFQ is cancelled or has a winner selected"

    if rfq.deadline < datetime.now():
        result["blocked"] = True
        result["reason"] = "RFQ deadline has passed"

    return result

@router.post("/submit", response_model=QuoteSchema)
async def submit_quote(
    quote_data: QuoteCreate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    rfq_supplier = db.query(RFQSupplier).filter(RFQSupplier.quote_submission_token == quote_data.quote_submission_token).first()
    if not rfq_supplier:
        raise HTTPException(status_code=404, detail="Invalid quote token")

    rfq = db.query(RFQ).filter(RFQ.id == rfq_supplier.rfq_id).first()
    if not rfq:
        raise HTTPException(status_code=404, detail="RFQ not found")

    if rfq.status in [RFQStatus.CANCELLED, RFQStatus.WINNER_SELECTED, RFQStatus.READY_FOR_REVIEW]:
        raise HTTPException(status_code=400, detail="Cannot submit quote for RFQ in this state")

    if rfq.deadline < datetime.now():
        raise HTTPException(status_code=400, detail="RFQ deadline has passed")

    total_amount = 0
    for quote_item in quote_data.quote_items:
        line_item = db.query(LineItem).filter(LineItem.id == quote_item.line_item_id).first()
        if not line_item:
            raise HTTPException(status_code=404, detail=f"Line item {quote_item.line_item_id} not found")

        if line_item.purchase_request_id != rfq.purchase_request_id:
            raise HTTPException(status_code=400, detail="Line item does not belong to this RFQ's purchase request")

        total_amount += quote_item.unit_price * line_item.quantity

    existing_quote = db.query(Quote).filter(Quote.rfq_supplier_id == rfq_supplier.id).first()
    revision_number = 1

    if existing_quote:
        revision_number = existing_quote.revision_number + 1
    else:
        rfq_supplier.has_submitted = True

    submission_reference = f"Q-{rfq.id}-{rfq_supplier.supplier_id}-{revision_number}"

    quote = Quote(
        rfq_supplier_id=rfq_supplier.id,
        rfq_id=rfq.id,
        revision_number=revision_number,
        unit_price_total=total_amount,
        delivery_time_days=quote_data.delivery_time_days,
        payment_terms=quote_data.payment_terms,
        notes=quote_data.notes,
        submission_reference=submission_reference
    )
    db.add(quote)
    db.commit()
    db.refresh(quote)

    for quote_item in quote_data.quote_items:
        quote_item_db = QuoteItem(
            quote_id=quote.id,
            line_item_id=quote_item.line_item_id,
            unit_price=quote_item.unit_price
        )
        db.add(quote_item_db)

    db.commit()
    db.refresh(rfq_supplier)

    all_submitted = all(rs.has_submitted for rs in rfq.suppliers)
    if all_submitted and len(rfq.suppliers) > 0:
        rfq.status = RFQStatus.READY_FOR_REVIEW
        db.commit()

    return quote

@router.put("/{quote_id}", response_model=QuoteSchema)
async def revise_quote(
    quote_id: int,
    quote_data: QuoteUpdate,
    db: Session = Depends(get_db)
):
    quote = db.query(Quote).filter(Quote.id == quote_id).options(
        joinedload(Quote.rfq_supplier),
        joinedload(Quote.rfq)
    ).first()

    if not quote:
        raise HTTPException(status_code=404, detail="Quote not found")

    if not quote.rfq_supplier or not quote.rfq_supplier.quote_submission_token:
        raise HTTPException(status_code=400, detail="Invalid quote token reference")

    if quote.rfq.deadline < datetime.now():
        raise HTTPException(status_code=400, detail="Cannot revise quote after deadline")

    if quote.rfq.status in [RFQStatus.CANCELLED, RFQStatus.WINNER_SELECTED, RFQStatus.READY_FOR_REVIEW]:
        raise HTTPException(status_code=400, detail="Cannot revise quote for RFQ in this state")

    if quote_data.quote_items:
        total_amount = 0
        for quote_item in quote_data.quote_items:
            line_item = db.query(LineItem).filter(LineItem.id == quote_item.line_item_id).first()
            if line_item:
                total_amount += quote_item.unit_price * line_item.quantity
        quote.unit_price_total = total_amount

    if quote_data.delivery_time_days:
        quote.delivery_time_days = quote_data.delivery_time_days

    if quote_data.payment_terms:
        quote.payment_terms = quote_data.payment_terms

    if quote_data.notes:
        quote.notes = quote_data.notes

    if quote_data.quote_items:
        db.query(QuoteItem).filter(QuoteItem.quote_id == quote.id).delete()
        for quote_item in quote_data.quote_items:
            quote_item_db = QuoteItem(
                quote_id=quote.id,
                line_item_id=quote_item.line_item_id,
                unit_price=quote_item.unit_price
            )
            db.add(quote_item_db)

    quote.revision_number += 1
    quote.updated_at = datetime.now()

    db.commit()
    db.refresh(quote)
    return quote

@router.get("/by-rfq/{rfq_id}", response_model=List[QuoteSchema])
async def get_quotes_by_rfq(
    rfq_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    rfq = db.query(RFQ).filter(RFQ.id == rfq_id).first()
    if not rfq:
        raise HTTPException(status_code=404, detail="RFQ not found")

    quotes = db.query(Quote).filter(Quote.rfq_id == rfq_id).options(
        joinedload(Quote.rfq_supplier).joinedload(RFQSupplier.supplier),
        joinedload(Quote.quote_items)
    ).all()

    return quotes

@router.get("/comparison/{rfq_id}", response_model=List[dict])
async def get_quote_comparison(
    rfq_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    rfq = db.query(RFQ).filter(RFQ.id == rfq_id).first()
    if not rfq:
        raise HTTPException(status_code=404, detail="RFQ not found")

    quotes = db.query(Quote).filter(Quote.rfq_id == rfq_id).options(
        joinedload(Quote.rfq_supplier).joinedload(RFQSupplier.supplier),
        joinedload(Quote.quote_items).joinedload(QuoteItem.line_item)
    ).all()

    comparison_data = []
    quote_totals = []

    for quote in quotes:
        supplier = quote.rfq_supplier.supplier
        total = 0
        line_items = []

        for quote_item in quote.quote_items:
            item_total = quote_item.unit_price * quote_item.line_item.quantity
            total += item_total
            line_items.append({
                "description": quote_item.line_item.description,
                "quantity": quote_item.line_item.quantity,
                "unit_price": quote_item.unit_price,
                "total": item_total
            })

        quote_totals.append(total)

        comparison_data.append({
            "quote_id": quote.id,
            "supplier_name": supplier.company_name,
            "supplier_score": supplier.overall_score,
            "revision_number": quote.revision_number,
            "delivery_time_days": quote.delivery_time_days,
            "payment_terms": quote.payment_terms,
            "total": total,
            "line_items": line_items,
            "is_lowest": False
        })

    if quote_totals:
        min_total = min(quote_totals)
        for item in comparison_data:
            if item["total"] == min_total:
                item["is_lowest"] = True

    comparison_data.sort(key=lambda x: x["total"])

    return comparison_data
