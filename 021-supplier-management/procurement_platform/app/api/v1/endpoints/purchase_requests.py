from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session, joinedload
from typing import List, Optional
from datetime import datetime, timedelta
from sqlalchemy import or_, and_, func

from app.database import get_db
from app.database.models import (
    PurchaseRequest, User, Category, KanbanStage, LineItem,
    StageHistory, RFQ, Supplier, SupplierCategory, RFQSupplier, Order
)
from app.api.v1.endpoints.auth import get_current_active_user
from app.api.v1.schemas.purchase_requests import PurchaseRequestCreate, PurchaseRequestUpdate, PurchaseRequestSchema
from app.api.v1.schemas.stages import StageSchema

router = APIRouter()

@router.get("/", response_model=List[PurchaseRequestSchema])
async def list_purchase_requests(
    title: Optional[str] = Query(None),
    category_id: Optional[int] = Query(None),
    priority: Optional[str] = Query(None),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    query = db.query(PurchaseRequest).options(
        joinedload(PurchaseRequest.category),
        joinedload(PurchaseRequest.stage),
        joinedload(PurchaseRequest.created_by),
        joinedload(PurchaseRequest.line_items)
    )

    if title:
        query = query.filter(
            or_(
                PurchaseRequest.title.ilike(f"%{title}%"),
                LineItem.description.ilike(f"%{title}%")
            )
        )

    if category_id:
        query = query.filter(PurchaseRequest.category_id == category_id)

    if priority:
        query = query.filter(PurchaseRequest.priority == priority)

    requests = query.all()

    result = []
    default_stage = db.query(KanbanStage).filter(KanbanStage.name == "New").first()

    for pr in requests:
        age = (datetime.now() - pr.created_at).days if pr.created_at else 0
        item_count = len(pr.line_items)

        pr_dict = {
            **pr.__dict__,
            "age": age,
            "item_count": item_count,
            "current_stage": pr.stage.name if pr.stage else "New"
        }

        if pr.stage is None and default_stage:
            pr.stage = default_stage
            db.commit()

        result.append(pr)

    return result

@router.post("/", response_model=PurchaseRequestSchema)
async def create_purchase_request(
    request_data: PurchaseRequestCreate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    category = db.query(Category).filter(Category.id == request_data.category_id).first()
    if not category:
        raise HTTPException(status_code=400, detail="Category not found")

    default_stage = db.query(KanbanStage).filter(KanbanStage.name == "New").first()
    if not default_stage:
        raise HTTPException(status_code=500, detail="Default stage 'New' not found")

    request = PurchaseRequest(
        title=request_data.title,
        description=request_data.description,
        priority=request_data.priority,
        deadline=request_data.deadline,
        notes=request_data.notes,
        category_id=request_data.category_id,
        stage_id=default_stage.id,
        created_by_id=current_user.id
    )
    db.add(request)
    db.commit()
    db.refresh(request)

    for item in request_data.line_items:
        line_item = LineItem(
            description=item.description,
            quantity=item.quantity,
            unit=item.unit,
            purchase_request_id=request.id
        )
        db.add(line_item)

    db.commit()
    db.refresh(request)

    stage_history = StageHistory(
        purchase_request_id=request.id,
        previous_stage_id=None,
        new_stage_id=default_stage.id,
        changed_by_id=current_user.id,
        change_reason="Initial creation"
    )
    db.add(stage_history)
    db.commit()

    return request

@router.get("/{request_id}", response_model=PurchaseRequestSchema)
async def get_purchase_request(
    request_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    request = db.query(PurchaseRequest).filter(PurchaseRequest.id == request_id).options(
        joinedload(PurchaseRequest.category),
        joinedload(PurchaseRequest.stage),
        joinedload(PurchaseRequest.created_by),
        joinedload(PurchaseRequest.line_items)
    ).first()

    if not request:
        raise HTTPException(status_code=404, detail="Purchase request not found")

    return request

@router.put("/{request_id}", response_model=PurchaseRequestSchema)
async def update_purchase_request(
    request_id: int,
    request_data: PurchaseRequestUpdate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    request = db.query(PurchaseRequest).filter(PurchaseRequest.id == request_id).first()
    if not request:
        raise HTTPException(status_code=404, detail="Purchase request not found")

    if request_data.category_id:
        category = db.query(Category).filter(Category.id == request_data.category_id).first()
        if not category:
            raise HTTPException(status_code=400, detail="Category not found")

    update_data = request_data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(request, key, value)

    request.updated_at = func.now()
    db.commit()
    db.refresh(request)
    return request

@router.delete("/{request_id}", status_code=204)
async def delete_purchase_request(
    request_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    request = db.query(PurchaseRequest).filter(PurchaseRequest.id == request_id).first()
    if not request:
        raise HTTPException(status_code=404, detail="Purchase request not found")

    existing_rfq = db.query(RFQ).filter(RFQ.purchase_request_id == request_id).first()
    if existing_rfq:
        raise HTTPException(status_code=400, detail="Cannot delete request with existing RFQ")

    db.delete(request)
    db.commit()
    return None

@router.post("/{request_id}/clone", response_model=PurchaseRequestSchema)
async def clone_purchase_request(
    request_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    original = db.query(PurchaseRequest).filter(PurchaseRequest.id == request_id).options(
        joinedload(PurchaseRequest.category),
        joinedload(PurchaseRequest.stage),
        joinedload(PurchaseRequest.line_items)
    ).first()

    if not original:
        raise HTTPException(status_code=404, detail="Purchase request not found")

    default_stage = db.query(KanbanStage).filter(KanbanStage.name == "New").first()
    if not default_stage:
        raise HTTPException(status_code=500, detail="Default stage 'New' not found")

    cloned = PurchaseRequest(
        title=f"Clone: {original.title}",
        description=original.description,
        priority=original.priority,
        deadline=original.deadline,
        notes=original.notes,
        category_id=original.category_id,
        stage_id=default_stage.id,
        created_by_id=current_user.id
    )
    db.add(cloned)
    db.commit()
    db.refresh(cloned)

    for item in original.line_items:
        cloned_item = LineItem(
            description=item.description,
            quantity=item.quantity,
            unit=item.unit,
            purchase_request_id=cloned.id
        )
        db.add(cloned_item)

    db.commit()
    db.refresh(cloned)

    stage_history = StageHistory(
        purchase_request_id=cloned.id,
        previous_stage_id=None,
        new_stage_id=default_stage.id,
        changed_by_id=current_user.id,
        change_reason="Cloned from request {request_id}"
    )
    db.add(stage_history)
    db.commit()

    return cloned

@router.post("/{request_id}/move-to-stage/{stage_id}", response_model=PurchaseRequestSchema)
async def move_to_stage(
    request_id: int,
    stage_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    request = db.query(PurchaseRequest).filter(PurchaseRequest.id == request_id).first()
    if not request:
        raise HTTPException(status_code=404, detail="Purchase request not found")

    new_stage = db.query(KanbanStage).filter(KanbanStage.id == stage_id).first()
    if not new_stage:
        raise HTTPException(status_code=404, detail="Stage not found")

    previous_stage_id = request.stage_id
    request.stage_id = stage_id

    stage_history = StageHistory(
        purchase_request_id=request_id,
        previous_stage_id=previous_stage_id,
        new_stage_id=stage_id,
        changed_by_id=current_user.id,
        change_reason="Manual stage change"
    )
    db.add(stage_history)
    db.commit()
    db.refresh(request)

    return request
