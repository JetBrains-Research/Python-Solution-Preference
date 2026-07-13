from fastapi import APIRouter, Depends, HTTPException, status, Body
from sqlalchemy.orm import Session
from typing import List
from sqlalchemy import func

from app.database import get_db
from app.database.models import KanbanStage, PurchaseRequest, User
from app.api.v1.endpoints.auth import get_current_admin_user
from app.api.v1.schemas.stages import StageCreate, StageUpdate, StageSchema

router = APIRouter()

@router.get("/", response_model=List[StageSchema])
async def list_stages(current_user: User = Depends(get_current_admin_user), db: Session = Depends(get_db)):
    stages = db.query(KanbanStage).order_by(KanbanStage.order_index).all()
    return stages

@router.post("/", response_model=StageSchema)
async def create_stage(stage_data: StageCreate, current_user: User = Depends(get_current_admin_user), db: Session = Depends(get_db)):
    existing_stage = db.query(KanbanStage).filter(KanbanStage.name == stage_data.name).first()
    if existing_stage:
        raise HTTPException(status_code=400, detail="Stage name already exists")

    max_order = db.query(func.max(KanbanStage.order_index)).scalar() or 0
    stage_data.order_index = max_order + 1

    stage = KanbanStage(
        name=stage_data.name,
        color=stage_data.color,
        order_index=stage_data.order_index
    )
    db.add(stage)
    db.commit()
    db.refresh(stage)
    return stage

@router.get("/{stage_id}", response_model=StageSchema)
async def get_stage(stage_id: int, current_user: User = Depends(get_current_admin_user), db: Session = Depends(get_db)):
    stage = db.query(KanbanStage).filter(KanbanStage.id == stage_id).first()
    if not stage:
        raise HTTPException(status_code=404, detail="Stage not found")
    return stage

@router.put("/{stage_id}", response_model=StageSchema)
async def update_stage(stage_id: int, stage_data: StageUpdate, current_user: User = Depends(get_current_admin_user), db: Session = Depends(get_db)):
    stage = db.query(KanbanStage).filter(KanbanStage.id == stage_id).first()
    if not stage:
        raise HTTPException(status_code=404, detail="Stage not found")

    if stage.name in ["New", "In Review", "Approved", "Ordered"]:
        raise HTTPException(status_code=400, detail="Cannot rename default stages")

    if stage_data.name:
        existing_stage = db.query(KanbanStage).filter(KanbanStage.name == stage_data.name, KanbanStage.id != stage_id).first()
        if existing_stage:
            raise HTTPException(status_code=400, detail="Stage name already exists")

    update_data = stage_data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(stage, key, value)

    db.commit()
    db.refresh(stage)
    return stage

@router.delete("/{stage_id}", status_code=204)
async def delete_stage(stage_id: int, current_user: User = Depends(get_current_admin_user), db: Session = Depends(get_db)):
    stage = db.query(KanbanStage).filter(KanbanStage.id == stage_id).first()
    if not stage:
        raise HTTPException(status_code=404, detail="Stage not found")

    if stage.name in ["New", "In Review", "Approved", "Ordered"]:
        raise HTTPException(status_code=400, detail="Cannot delete default stages")

    pr_count = db.query(PurchaseRequest).filter(PurchaseRequest.stage_id == stage_id).count()
    if pr_count > 0:
        raise HTTPException(status_code=400, detail="Cannot delete stage containing requests")

    db.delete(stage)
    db.commit()
    return None

@router.post("/reorder")
async def reorder_stages(stage_ids: List[int] = Body(..., embed=True), current_user: User = Depends(get_current_admin_user), db: Session = Depends(get_db)):
    if len(stage_ids) != len(set(stage_ids)):
        raise HTTPException(status_code=400, detail="Duplicate stage IDs")

    stages = db.query(KanbanStage).filter(KanbanStage.id.in_(stage_ids)).all()
    if len(stages) != len(stage_ids):
        raise HTTPException(status_code=404, detail="Some stages not found")

    for index, stage_id in enumerate(stage_ids):
        stage = db.query(KanbanStage).filter(KanbanStage.id == stage_id).first()
        stage.order_index = index

    db.commit()
    return {"message": "Stages reordered successfully"}
