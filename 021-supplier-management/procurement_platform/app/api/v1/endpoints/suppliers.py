from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session, joinedload
from typing import List, Optional
from sqlalchemy import or_, and_, func

from app.database import get_db
from app.database.models import Supplier, Category, SupplierCategory, RFQ, RFQSupplier, Order, User
from app.api.v1.endpoints.auth import get_current_active_user, get_current_admin_user
from app.api.v1.schemas.suppliers import SupplierCreate, SupplierUpdate, SupplierSchema, SupplierSearch

router = APIRouter()

def calculate_overall_score(punctuality: float = 0, quality: float = 0, reliability: float = 0) -> float:
    return round(punctuality * 0.35 + quality * 0.35 + reliability * 0.30)

@router.get("/", response_model=List[SupplierSchema])
async def list_suppliers(
    search: Optional[str] = Query(None),
    category_id: Optional[int] = Query(None),
    is_active: Optional[bool] = Query(None),
    sort_by: str = Query("name"),
    sort_order: str = Query("asc"),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    query = db.query(Supplier).options(joinedload(Supplier.categories).joinedload(SupplierCategory.category))

    if search:
        query = query.filter(
            or_(
                Supplier.company_name.ilike(f"%{search}%"),
                Supplier.email.ilike(f"%{search}%")
            )
        )

    if category_id:
        query = query.join(Supplier.categories).filter(SupplierCategory.category_id == category_id)

    if is_active is not None:
        query = query.filter(Supplier.is_active == is_active)

    if sort_by == "name":
        if sort_order == "desc":
            query = query.order_by(Supplier.company_name.desc())
        else:
            query = query.order_by(Supplier.company_name.asc())
    elif sort_by == "score":
        if sort_order == "desc":
            query = query.order_by(Supplier.overall_score.desc(), Supplier.company_name.asc())
        else:
            query = query.order_by(Supplier.overall_score.asc(), Supplier.company_name.asc())

    suppliers = query.all()
    return suppliers

@router.get("/active", response_model=List[SupplierSchema])
async def list_active_suppliers(current_user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    suppliers = db.query(Supplier).filter(Supplier.is_active == True).all()
    return suppliers

@router.post("/", response_model=SupplierSchema)
async def create_supplier(supplier_data: SupplierCreate, current_user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    existing_tax_id = db.query(Supplier).filter(Supplier.tax_id == supplier_data.tax_id).first()
    if existing_tax_id:
        raise HTTPException(status_code=400, detail="Tax ID already exists")

    existing_email = db.query(Supplier).filter(Supplier.email == supplier_data.email).first()
    if existing_email:
        raise HTTPException(status_code=400, detail="Email already exists")

    if not supplier_data.category_ids:
        raise HTTPException(status_code=400, detail="At least one category is required")

    for cat_id in supplier_data.category_ids:
        category = db.query(Category).filter(Category.id == cat_id).first()
        if not category:
            raise HTTPException(status_code=400, detail=f"Category {cat_id} not found")

    supplier = Supplier(
        company_name=supplier_data.company_name,
        tax_id=supplier_data.tax_id,
        email=supplier_data.email,
        contact_person=supplier_data.contact_person,
        phone=supplier_data.phone,
        address=supplier_data.address,
        is_active=supplier_data.is_active
    )
    db.add(supplier)
    db.commit()
    db.refresh(supplier)

    for cat_id in supplier_data.category_ids:
        supplier_category = SupplierCategory(supplier_id=supplier.id, category_id=cat_id)
        db.add(supplier_category)

    db.commit()
    db.refresh(supplier)
    return supplier

@router.get("/{supplier_id}", response_model=SupplierSchema)
async def get_supplier(supplier_id: int, current_user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    supplier = db.query(Supplier).filter(Supplier.id == supplier_id).options(joinedload(Supplier.categories)).first()
    if not supplier:
        raise HTTPException(status_code=404, detail="Supplier not found")
    return supplier

@router.put("/{supplier_id}", response_model=SupplierSchema)
async def update_supplier(supplier_id: int, supplier_data: SupplierUpdate, current_user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    supplier = db.query(Supplier).filter(Supplier.id == supplier_id).first()
    if not supplier:
        raise HTTPException(status_code=404, detail="Supplier not found")

    if supplier_data.tax_id and supplier_data.tax_id != supplier.tax_id:
        existing_tax_id = db.query(Supplier).filter(Supplier.tax_id == supplier_data.tax_id, Supplier.id != supplier_id).first()
        if existing_tax_id:
            raise HTTPException(status_code=400, detail="Tax ID already exists")

    if supplier_data.email and supplier_data.email != supplier.email:
        existing_email = db.query(Supplier).filter(Supplier.email == supplier_data.email, Supplier.id != supplier_id).first()
        if existing_email:
            raise HTTPException(status_code=400, detail="Email already exists")

    update_data = supplier_data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        if key != "category_ids":
            setattr(supplier, key, value)

    if supplier_data.category_ids:
        db.query(SupplierCategory).filter(SupplierCategory.supplier_id == supplier_id).delete()
        for cat_id in supplier_data.category_ids:
            category = db.query(Category).filter(Category.id == cat_id).first()
            if category:
                supplier_category = SupplierCategory(supplier_id=supplier.id, category_id=cat_id)
                db.add(supplier_category)

    db.commit()
    db.refresh(supplier)
    return supplier

@router.delete("/{supplier_id}", status_code=204)
async def delete_supplier(supplier_id: int, current_user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    supplier = db.query(Supplier).filter(Supplier.id == supplier_id).first()
    if not supplier:
        raise HTTPException(status_code=404, detail="Supplier not found")

    rfq_count = db.query(RFQSupplier).filter(RFQSupplier.supplier_id == supplier_id).count()
    order_count = db.query(Order).filter(Order.supplier_id == supplier_id).count()

    if rfq_count > 0 or order_count > 0:
        raise HTTPException(status_code=400, detail="Cannot delete supplier with existing RFQs or orders")

    db.delete(supplier)
    db.commit()
    return None

@router.patch("/{supplier_id}/toggle-active", response_model=SupplierSchema)
async def toggle_supplier_active(supplier_id: int, current_user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    supplier = db.query(Supplier).filter(Supplier.id == supplier_id).first()
    if not supplier:
        raise HTTPException(status_code=404, detail="Supplier not found")

    if not supplier.is_active and supplier.id == current_user.id:
        raise HTTPException(status_code=400, detail="Cannot deactivate own supplier account")

    active_rfqs = db.query(RFQ).filter(
        RFQ.status.notin_(["Cancelled", "Winner Selected", "Overdue"]),
        RFQ.deadline > func.now()
    ).all()

    for rfq in active_rfqs:
        rfq_supplier = db.query(RFQSupplier).filter(
            RFQSupplier.rfq_id == rfq.id,
            RFQSupplier.supplier_id == supplier_id
        ).first()
        if rfq_supplier and rfq_supplier.has_submitted == False:
            raise HTTPException(status_code=400, detail="Cannot deactivate supplier invited to active RFQ awaiting quotes")

    supplier.is_active = not supplier.is_active
    supplier.updated_at = func.now()

    db.commit()
    db.refresh(supplier)
    return supplier
