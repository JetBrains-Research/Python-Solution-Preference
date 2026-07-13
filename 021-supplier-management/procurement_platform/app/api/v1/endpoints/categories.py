from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List

from app.database import get_db
from app.database.models import Category, PurchaseRequest, Supplier, SupplierCategory, User
from app.api.v1.endpoints.auth import get_current_admin_user
from app.api.v1.schemas.categories import CategoryCreate, CategoryUpdate, CategorySchema

router = APIRouter()

@router.get("/", response_model=List[CategorySchema])
async def list_categories(current_user: User = Depends(get_current_admin_user), db: Session = Depends(get_db)):
    categories = db.query(Category).all()
    return categories

@router.post("/", response_model=CategorySchema)
async def create_category(category_data: CategoryCreate, current_user: User = Depends(get_current_admin_user), db: Session = Depends(get_db)):
    existing_category = db.query(Category).filter(Category.name == category_data.name).first()
    if existing_category:
        raise HTTPException(status_code=400, detail="Category already exists")

    category = Category(
        name=category_data.name,
        description=category_data.description
    )
    db.add(category)
    db.commit()
    db.refresh(category)
    return category

@router.get("/{category_id}", response_model=CategorySchema)
async def get_category(category_id: int, current_user: User = Depends(get_current_admin_user), db: Session = Depends(get_db)):
    category = db.query(Category).filter(Category.id == category_id).first()
    if not category:
        raise HTTPException(status_code=404, detail="Category not found")
    return category

@router.put("/{category_id}", response_model=CategorySchema)
async def update_category(category_id: int, category_data: CategoryUpdate, current_user: User = Depends(get_current_admin_user), db: Session = Depends(get_db)):
    category = db.query(Category).filter(Category.id == category_id).first()
    if not category:
        raise HTTPException(status_code=404, detail="Category not found")

    if category_data.name:
        existing_category = db.query(Category).filter(Category.name == category_data.name, Category.id != category_id).first()
        if existing_category:
            raise HTTPException(status_code=400, detail="Category name already exists")

    update_data = category_data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(category, key, value)

    db.commit()
    db.refresh(category)
    return category

@router.delete("/{category_id}", status_code=204)
async def delete_category(category_id: int, current_user: User = Depends(get_current_admin_user), db: Session = Depends(get_db)):
    category = db.query(Category).filter(Category.id == category_id).first()
    if not category:
        raise HTTPException(status_code=404, detail="Category not found")

    pr_count = db.query(PurchaseRequest).filter(PurchaseRequest.category_id == category_id).count()
    supplier_count = db.query(SupplierCategory).filter(SupplierCategory.category_id == category_id).count()

    if pr_count > 0 or supplier_count > 0:
        raise HTTPException(status_code=400, detail="Cannot delete category used by purchase requests or suppliers")

    db.delete(category)
    db.commit()
    return None
