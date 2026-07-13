import os
import secrets
import datetime
from contextlib import asynccontextmanager
from typing import List, Optional

from fastapi import FastAPI, Depends, HTTPException, status, Query
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session, joinedload
from jose import jwt, JWTError
from passlib.context import CryptContext

from app.database import engine, Base, get_db
from app import models, schemas

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
SECRET_KEY = os.environ.get("SECRET_KEY", "supersecretdevelopmentkey")
ALGORITHM = "HS256"

security = HTTPBearer(auto_error=False)

def hash_password(password: str) -> str:
    return pwd_context.hash(password)

def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)

def create_access_token(data: dict, expires_delta: Optional[datetime.timedelta] = None) -> str:
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.datetime.utcnow() + expires_delta
    else:
        expire = datetime.datetime.utcnow() + datetime.timedelta(hours=24)
    to_encode["exp"] = expire
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security), db: Session = Depends(get_db)):
    if not credentials:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    token = credentials.credentials
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    user = db.query(models.User).filter(models.User.username == username).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account inactive")
    return user

def require_admin(user: models.User = Depends(get_current_user)):
    if not user.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    return user

def get_default_stage(db: Session):
    return db.query(models.Stage).filter(models.Stage.is_default == True).first()

def record_stage_history(db: Session, request_id: int, from_stage_id: Optional[int], to_stage_id: int):
    history = models.StageHistory(
        request_id=request_id,
        from_stage_id=from_stage_id,
        to_stage_id=to_stage_id,
        timestamp=datetime.datetime.utcnow()
    )
    db.add(history)
    db.commit()

def generate_order_number(db: Session) -> str:
    year = datetime.datetime.utcnow().year
    count = db.query(models.PurchaseOrder).filter(models.PurchaseOrder.order_number.like(f"PO-{year}-%")).count()
    return f"PO-{year}-{count + 1:04d}"

def overall_score(supplier: models.Supplier) -> Optional[int]:
    if supplier.punctuality is not None and supplier.quality is not None and supplier.reliability is not None:
        return int(round(supplier.punctuality * 0.35 + supplier.quality * 0.35 + supplier.reliability * 0.30))
    return None

def seed_data(db: Session):
    if not db.query(models.User).filter(models.User.username == "admin").first():
        admin = models.User(
            username="admin",
            password_hash=hash_password("admin123"),
            is_admin=True,
            is_active=True
        )
        db.add(admin)
    categories = ["Raw Materials", "Office Supplies", "Equipment", "Services", "Other"]
    for idx, cat_name in enumerate(categories):
        if not db.query(models.Category).filter(models.Category.name == cat_name).first():
            db.add(models.Category(name=cat_name))
    stages_data = [
        ("New", "#4CAF50", 0, True),
        ("In Review", "#FF9800", 1, False),
        ("Approved", "#2196F3", 2, False),
        ("Ordered", "#9C27B0", 3, False),
    ]
    for name, color, order, is_default in stages_data:
        if not db.query(models.Stage).filter(models.Stage.name == name).first():
            db.add(models.Stage(name=name, color=color, order=order, is_default=is_default, is_seed=True))
    db.commit()

@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    db = next(get_db())
    seed_data(db)
    db.close()
    yield

app = FastAPI(title="Supplier Relationship Management Platform", lifespan=lifespan)

# Auth endpoints
@app.post("/api/auth/login", response_model=schemas.Token)
def login(payload: schemas.UserLogin, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.username == payload.username).first()
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account inactive")
    token = create_access_token({"sub": user.username})
    return {"access_token": token, "token_type": "bearer"}


# Dashboard
@app.get("/api/dashboard", response_model=schemas.DashboardOut)
def dashboard(db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    result = schemas.DashboardOut()
    all_rfqs = db.query(models.RFQ).filter(models.RFQ.status.in_(["Awaiting Quotes", "Ready for Review", "Overdue"])).all()
    for rfq in all_rfqs:
        total_invited = len(rfq.suppliers)
        responded = sum(1 for q in rfq.quotes if any(q.supplier_id == s.supplier_id for s in rfq.suppliers))
        if total_invited > 0 and responded == total_invited and rfq.status == "Awaiting Quotes":
            rfq.status = "Ready for Review"
            db.add(rfq)
            db.commit()
        if rfq.status == "Ready for Review":
            result.rfqs_ready_for_review.append(schemas.DashboardRFQItem(
                id=rfq.id, title=rfq.title, status=rfq.status
            ))
    orders = db.query(models.PurchaseOrder).filter(models.PurchaseOrder.current_status != "Delivered").all()
    for order in orders:
        if order.expected_delivery < datetime.date.today():
            supplier = db.query(models.Supplier).filter(models.Supplier.id == order.supplier_id).first()
            result.overdue_orders.append(schemas.DashboardOverdueOrderItem(
                id=order.id, order_number=order.order_number,
                supplier_name=supplier.company_name if supplier else "",
                expected_delivery=order.expected_delivery
            ))
    new_stage = db.query(models.Stage).filter(models.Stage.name == "New").first()
    if new_stage:
        prs = db.query(models.PurchaseRequest).filter(
            models.PurchaseRequest.current_stage_id == new_stage.id,
            models.PurchaseRequest.is_deleted == False
        ).all()
        for pr in prs:
            days = (datetime.datetime.utcnow() - pr.created_at).days
            if days > 7:
                result.stale_purchase_requests.append(schemas.DashboardStalePRItem(
                    id=pr.id, title=pr.title, created_at=pr.created_at, days_in_new=days
                ))
    db.commit()
    return result


# Users (Admin only)
@app.post("/api/users", response_model=schemas.UserOut, status_code=status.HTTP_201_CREATED)
def create_user(payload: schemas.UserCreate, db: Session = Depends(get_db), admin: models.User = Depends(require_admin)):
    if db.query(models.User).filter(models.User.username == payload.username).first():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Username already exists")
    user = models.User(
        username=payload.username,
        password_hash=hash_password(payload.password),
        is_admin=payload.is_admin,
        is_active=True
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@app.get("/api/users", response_model=List[schemas.UserOut])
def list_users(db: Session = Depends(get_db), admin: models.User = Depends(require_admin)):
    return db.query(models.User).all()


@app.get("/api/users/{user_id}", response_model=schemas.UserOut)
def get_user(user_id: int, db: Session = Depends(get_db), admin: models.User = Depends(require_admin)):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return user


@app.put("/api/users/{user_id}", response_model=schemas.UserOut)
def update_user(user_id: int, payload: schemas.UserUpdate, db: Session = Depends(get_db), admin: models.User = Depends(require_admin)):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    if payload.is_admin is not None:
        user.is_admin = payload.is_admin
    if payload.is_active is not None:
        if user_id == admin.id and not payload.is_active:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot deactivate own account")
        user.is_active = payload.is_active
    db.commit()
    db.refresh(user)
    return user


# Categories (Admin only)
@app.post("/api/categories", response_model=schemas.CategoryOut, status_code=status.HTTP_201_CREATED)
def create_category(payload: schemas.CategoryCreate, db: Session = Depends(get_db), admin: models.User = Depends(require_admin)):
    cat = models.Category(name=payload.name)
    db.add(cat)
    db.commit()
    db.refresh(cat)
    return cat


@app.get("/api/categories", response_model=List[schemas.CategoryOut])
def list_categories(db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    return db.query(models.Category).all()


@app.put("/api/categories/{category_id}", response_model=schemas.CategoryOut)
def update_category(category_id: int, payload: schemas.CategoryUpdate, db: Session = Depends(get_db), admin: models.User = Depends(require_admin)):
    cat = db.query(models.Category).filter(models.Category.id == category_id).first()
    if not cat:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Category not found")
    if payload.name is not None:
        cat.name = payload.name
    db.commit()
    db.refresh(cat)
    return cat


@app.delete("/api/categories/{category_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_category(category_id: int, db: Session = Depends(get_db), admin: models.User = Depends(require_admin)):
    cat = db.query(models.Category).filter(models.Category.id == category_id).first()
    if not cat:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Category not found")
    has_refs = db.query(models.PurchaseRequest).filter(models.PurchaseRequest.category_id == category_id).first() or \
               db.query(models.SupplierCategory).filter(models.SupplierCategory.category_id == category_id).first()
    if has_refs:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Category in use")
    db.delete(cat)
    db.commit()


# Stages (Admin only)
@app.post("/api/stages", response_model=schemas.StageOut, status_code=status.HTTP_201_CREATED)
def create_stage(payload: schemas.StageCreate, db: Session = Depends(get_db), admin: models.User = Depends(require_admin)):
    max_order = db.query(models.Stage).order_by(models.Stage.order.desc()).first()
    next_order = (max_order.order + 1) if max_order else 0
    stage = models.Stage(name=payload.name, color=payload.color, order=next_order)
    db.add(stage)
    db.commit()
    db.refresh(stage)
    return stage


@app.get("/api/stages", response_model=List[schemas.StageOut])
def list_stages(db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    return db.query(models.Stage).order_by(models.Stage.order).all()


@app.put("/api/stages/{stage_id}", response_model=schemas.StageOut)
def update_stage(stage_id: int, payload: schemas.StageUpdate, db: Session = Depends(get_db), admin: models.User = Depends(require_admin)):
    stage = db.query(models.Stage).filter(models.Stage.id == stage_id).first()
    if not stage:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Stage not found")
    if stage.is_seed:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot modify seed stages")
    if payload.name is not None:
        stage.name = payload.name
    if payload.color is not None:
        stage.color = payload.color
    if payload.order is not None:
        stage.order = payload.order
    db.commit()
    db.refresh(stage)
    return stage


@app.delete("/api/stages/{stage_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_stage(stage_id: int, db: Session = Depends(get_db), admin: models.User = Depends(require_admin)):
    stage = db.query(models.Stage).filter(models.Stage.id == stage_id).first()
    if not stage:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Stage not found")
    if stage.is_seed:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot delete seed stages")
    has_reqs = db.query(models.PurchaseRequest).filter(models.PurchaseRequest.current_stage_id == stage_id).first()
    if has_reqs:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Stage contains requests")
    db.delete(stage)
    db.commit()


# Suppliers
@app.post("/api/suppliers", response_model=schemas.SupplierOut, status_code=status.HTTP_201_CREATED)
def create_supplier(payload: schemas.SupplierCreate, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    if db.query(models.Supplier).filter(models.Supplier.tax_id == payload.tax_id).first():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Tax ID already exists")
    if db.query(models.Supplier).filter(models.Supplier.email == payload.email).first():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email already exists")
    if not payload.category_ids:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="At least one category required")
    supplier = models.Supplier(
        company_name=payload.company_name,
        tax_id=payload.tax_id,
        email=payload.email,
        is_active=True
    )
    db.add(supplier)
    db.commit()
    db.refresh(supplier)
    for cid in payload.category_ids:
        db.add(models.SupplierCategory(supplier_id=supplier.id, category_id=cid))
    db.commit()
    db.refresh(supplier)
    return enrich_supplier(supplier)


def enrich_supplier(supplier: models.Supplier) -> schemas.SupplierOut:
    return schemas.SupplierOut(
        id=supplier.id,
        company_name=supplier.company_name,
        tax_id=supplier.tax_id,
        email=supplier.email,
        is_active=supplier.is_active,
        punctuality=supplier.punctuality,
        quality=supplier.quality,
        reliability=supplier.reliability,
        overall_score=overall_score(supplier),
        categories=[schemas.CategoryOut(id=sc.category.id, name=sc.category.name) for sc in supplier.categories]
    )

@app.get("/api/suppliers", response_model=List[schemas.SupplierOut])
def list_suppliers(
    query: Optional[str] = None,
    status: Optional[str] = None,
    category_id: Optional[int] = None,
    sort_by: Optional[str] = None,
    sort_order: Optional[str] = "asc",
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user)
):
    q = db.query(models.Supplier).options(joinedload(models.Supplier.categories).joinedload(models.SupplierCategory.category))
    if query:
        q = q.filter(
            (models.Supplier.company_name.ilike(f"%{query}%")) |
            (models.Supplier.email.ilike(f"%{query}%"))
        )
    if status == "active":
        q = q.filter(models.Supplier.is_active == True)
    elif status == "inactive":
        q = q.filter(models.Supplier.is_active == False)
    if category_id is not None:
        q = q.join(models.SupplierCategory).filter(models.SupplierCategory.category_id == category_id)
    items = q.all()
    result = [enrich_supplier(s) for s in items]
    if sort_by == "name":
        result.sort(key=lambda x: x.company_name.lower(), reverse=(sort_order == "desc"))
    elif sort_by == "score":
        result.sort(key=lambda x: (x.overall_score is None, x.overall_score or 0), reverse=(sort_order == "desc"))
    return result


@app.get("/api/suppliers/{supplier_id}", response_model=schemas.SupplierOut)
def get_supplier(supplier_id: int, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    supplier = db.query(models.Supplier).filter(models.Supplier.id == supplier_id).first()
    if not supplier:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Supplier not found")
    return enrich_supplier(supplier)


@app.put("/api/suppliers/{supplier_id}", response_model=schemas.SupplierOut)
def update_supplier(supplier_id: int, payload: schemas.SupplierUpdate, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    supplier = db.query(models.Supplier).filter(models.Supplier.id == supplier_id).first()
    if not supplier:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Supplier not found")
    if payload.company_name is not None:
        supplier.company_name = payload.company_name
    if payload.tax_id is not None:
        if db.query(models.Supplier).filter(models.Supplier.tax_id == payload.tax_id, models.Supplier.id != supplier_id).first():
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Tax ID already exists")
        supplier.tax_id = payload.tax_id
    if payload.email is not None:
        if db.query(models.Supplier).filter(models.Supplier.email == payload.email, models.Supplier.id != supplier_id).first():
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email already exists")
        supplier.email = payload.email
    if payload.is_active is not None:
        active_rfq = db.query(models.RFQSupplier).join(models.RFQ).filter(
            models.RFQSupplier.supplier_id == supplier_id,
            models.RFQ.status.in_(["Awaiting Quotes", "Ready for Review", "Overdue"])
        ).first()
        if active_rfq and not payload.is_active:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot deactivate supplier invited to active RFQ")
        supplier.is_active = payload.is_active
    if payload.category_ids is not None:
        db.query(models.SupplierCategory).filter(models.SupplierCategory.supplier_id == supplier_id).delete()
        for cid in payload.category_ids:
            db.add(models.SupplierCategory(supplier_id=supplier_id, category_id=cid))
    db.commit()
    db.refresh(supplier)
    return enrich_supplier(supplier)


@app.delete("/api/suppliers/{supplier_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_supplier(supplier_id: int, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    supplier = db.query(models.Supplier).filter(models.Supplier.id == supplier_id).first()
    if not supplier:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Supplier not found")
    has_rfq = db.query(models.RFQSupplier).filter(models.RFQSupplier.supplier_id == supplier_id).first()
    has_order = db.query(models.PurchaseOrder).filter(models.PurchaseOrder.supplier_id == supplier_id).first()
    if has_rfq or has_order:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Supplier has existing RFQs or orders")
    db.query(models.SupplierCategory).filter(models.SupplierCategory.supplier_id == supplier_id).delete()
    db.delete(supplier)
    db.commit()


# Purchase Requests
@app.post("/api/purchase-requests", response_model=schemas.PurchaseRequestOut, status_code=status.HTTP_201_CREATED)
def create_purchase_request(payload: schemas.PurchaseRequestCreate, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    if not payload.line_items:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="At least one line item required")
    default_stage = get_default_stage(db)
    if not default_stage:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Default stage not configured")
    pr = models.PurchaseRequest(
        title=payload.title,
        priority=payload.priority,
        category_id=payload.category_id,
        deadline=payload.deadline,
        notes=payload.notes,
        current_stage_id=default_stage.id,
        created_at=datetime.datetime.utcnow()
    )
    db.add(pr)
    db.commit()
    db.refresh(pr)
    for item in payload.line_items:
        db.add(models.PurchaseRequestLineItem(
            request_id=pr.id,
            description=item.description,
            quantity=item.quantity
        ))
    record_stage_history(db, pr.id, None, default_stage.id)
    db.commit()
    db.refresh(pr)
    return enrich_purchase_request(pr, db)


def enrich_purchase_request(pr: models.PurchaseRequest, db: Session) -> schemas.PurchaseRequestOut:
    data = schemas.PurchaseRequestOut.from_orm(pr)
    cat = db.query(models.Category).filter(models.Category.id == pr.category_id).first()
    data.category_name = cat.name if cat else None
    stage = db.query(models.Stage).filter(models.Stage.id == pr.current_stage_id).first()
    data.current_stage_name = stage.name if stage else None
    data.age_days = (datetime.datetime.utcnow() - pr.created_at).days
    data.item_count = len(pr.line_items)
    return data


@app.get("/api/purchase-requests", response_model=List[schemas.PurchaseRequestOut])
def list_purchase_requests(
    query: Optional[str] = None,
    category_id: Optional[int] = None,
    priority: Optional[str] = None,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user)
):
    q = db.query(models.PurchaseRequest).filter(models.PurchaseRequest.is_deleted == False).options(joinedload(models.PurchaseRequest.line_items))
    if query:
        ids_from_items = db.query(models.PurchaseRequestLineItem.request_id).filter(
            models.PurchaseRequestLineItem.description.ilike(f"%{query}%")
        ).subquery()
        q = q.filter(
            (models.PurchaseRequest.title.ilike(f"%{query}%")) |
            (models.PurchaseRequest.id.in_(ids_from_items))
        )
    if category_id is not None:
        q = q.filter(models.PurchaseRequest.category_id == category_id)
    if priority is not None:
        q = q.filter(models.PurchaseRequest.priority == priority)
    items = q.all()
    return [enrich_purchase_request(i, db) for i in items]


@app.get("/api/purchase-requests/{pr_id}", response_model=schemas.PurchaseRequestOut)
def get_purchase_request(pr_id: int, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    pr = db.query(models.PurchaseRequest).filter(models.PurchaseRequest.id == pr_id, models.PurchaseRequest.is_deleted == False).first()
    if not pr:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Purchase request not found")
    return enrich_purchase_request(pr, db)


@app.put("/api/purchase-requests/{pr_id}", response_model=schemas.PurchaseRequestOut)
def update_purchase_request(pr_id: int, payload: schemas.PurchaseRequestUpdate, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    pr = db.query(models.PurchaseRequest).filter(models.PurchaseRequest.id == pr_id, models.PurchaseRequest.is_deleted == False).first()
    if not pr:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Purchase request not found")
    if payload.title is not None:
        pr.title = payload.title
    if payload.priority is not None:
        pr.priority = payload.priority
    if payload.category_id is not None:
        pr.category_id = payload.category_id
    if payload.deadline is not None:
        pr.deadline = payload.deadline
    if payload.notes is not None:
        pr.notes = payload.notes
    if payload.line_items is not None:
        db.query(models.PurchaseRequestLineItem).filter(models.PurchaseRequestLineItem.request_id == pr_id).delete()
        for item in payload.line_items:
            db.add(models.PurchaseRequestLineItem(
                request_id=pr.id,
                description=item.description,
                quantity=item.quantity
            ))
    db.commit()
    db.refresh(pr)
    return enrich_purchase_request(pr, db)


@app.post("/api/purchase-requests/{pr_id}/move", response_model=schemas.PurchaseRequestOut)
def move_purchase_request(pr_id: int, payload: schemas.PurchaseRequestMove, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    pr = db.query(models.PurchaseRequest).filter(models.PurchaseRequest.id == pr_id, models.PurchaseRequest.is_deleted == False).first()
    if not pr:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Purchase request not found")
    new_stage = db.query(models.Stage).filter(models.Stage.id == payload.stage_id).first()
    if not new_stage:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Stage not found")
    old_stage_id = pr.current_stage_id
    pr.current_stage_id = payload.stage_id
    record_stage_history(db, pr.id, old_stage_id, payload.stage_id)
    db.commit()
    db.refresh(pr)
    return enrich_purchase_request(pr, db)


@app.get("/api/purchase-requests/{pr_id}/history", response_model=List[schemas.StageHistoryOut])
def get_purchase_request_history(pr_id: int, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    pr = db.query(models.PurchaseRequest).filter(models.PurchaseRequest.id == pr_id).first()
    if not pr:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Purchase request not found")
    return db.query(models.StageHistory).filter(models.StageHistory.request_id == pr_id).order_by(models.StageHistory.timestamp).all()


@app.post("/api/purchase-requests/{pr_id}/clone", response_model=schemas.PurchaseRequestOut)
def clone_purchase_request(pr_id: int, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    pr = db.query(models.PurchaseRequest).filter(models.PurchaseRequest.id == pr_id, models.PurchaseRequest.is_deleted == False).first()
    if not pr:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Purchase request not found")
    default_stage = get_default_stage(db)
    new_pr = models.PurchaseRequest(
        title=pr.title,
        priority=pr.priority,
        category_id=pr.category_id,
        deadline=pr.deadline,
        notes=pr.notes,
        current_stage_id=default_stage.id,
        cloned_from_id=pr.id,
        created_at=datetime.datetime.utcnow()
    )
    db.add(new_pr)
    db.commit()
    db.refresh(new_pr)
    for item in pr.line_items:
        db.add(models.PurchaseRequestLineItem(
            request_id=new_pr.id,
            description=item.description,
            quantity=item.quantity
        ))
    record_stage_history(db, new_pr.id, None, default_stage.id)
    db.commit()
    db.refresh(new_pr)
    return enrich_purchase_request(new_pr, db)


@app.delete("/api/purchase-requests/{pr_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_purchase_request(pr_id: int, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    pr = db.query(models.PurchaseRequest).filter(models.PurchaseRequest.id == pr_id, models.PurchaseRequest.is_deleted == False).first()
    if not pr:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Purchase request not found")
    rfq = db.query(models.RFQ).filter(models.RFQ.purchase_request_id == pr_id).first()
    if rfq:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot delete request with existing RFQ")
    db.query(models.PurchaseRequestLineItem).filter(models.PurchaseRequestLineItem.request_id == pr_id).delete()
    db.query(models.StageHistory).filter(models.StageHistory.request_id == pr_id).delete()
    db.delete(pr)
    db.commit()


# RFQ Management
@app.post("/api/rfqs", response_model=schemas.RFQOut, status_code=status.HTTP_201_CREATED)
def create_rfq(payload: schemas.RFQCreate, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    pr = db.query(models.PurchaseRequest).filter(models.PurchaseRequest.id == payload.purchase_request_id, models.PurchaseRequest.is_deleted == False).first()
    if not pr:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Purchase request not found")
    existing = db.query(models.RFQ).filter(models.RFQ.purchase_request_id == payload.purchase_request_id).first()
    if existing and existing.status not in ["Cancelled"]:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Active RFQ already exists for this request")
    if not payload.supplier_ids:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="At least one supplier required")
    rfq = models.RFQ(
        purchase_request_id=payload.purchase_request_id,
        title=payload.title,
        description=payload.description,
        deadline=payload.deadline,
        status="Awaiting Quotes"
    )
    db.add(rfq)
    db.commit()
    db.refresh(rfq)
    for sid in payload.supplier_ids:
        token = secrets.token_urlsafe(32)
        db.add(models.RFQSupplier(rfq_id=rfq.id, supplier_id=sid, quote_token=token))
    db.commit()
    db.refresh(rfq)
    # Move PR to In Review
    in_review = db.query(models.Stage).filter(models.Stage.name == "In Review").first()
    if in_review and pr.current_stage_id != in_review.id:
        old = pr.current_stage_id
        pr.current_stage_id = in_review.id
        record_stage_history(db, pr.id, old, in_review.id)
        db.commit()
    return enrich_rfq(rfq, db)


def enrich_rfq(rfq: models.RFQ, db: Session) -> schemas.RFQOut:
    suppliers_out = []
    for rs in rfq.suppliers:
        sub = db.query(models.Quote).filter(models.Quote.rfq_id == rfq.id, models.Quote.supplier_id == rs.supplier_id).first()
        suppliers_out.append(schemas.RFQSupplierOut(
            id=rs.id,
            supplier_id=rs.supplier_id,
            company_name=rs.supplier.company_name if rs.supplier else "",
            has_submitted=sub is not None,
            quote_token=rs.quote_token
        ))
    return schemas.RFQOut(
        id=rfq.id,
        purchase_request_id=rfq.purchase_request_id,
        title=rfq.title,
        description=rfq.description,
        deadline=rfq.deadline,
        status=rfq.status,
        winner_quote_id=rfq.winner_quote_id,
        created_at=rfq.created_at,
        suppliers=suppliers_out
    )

@app.get("/api/rfqs", response_model=List[schemas.RFQOut])
def list_rfqs(db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    rfqs = db.query(models.RFQ).order_by(models.RFQ.created_at.desc()).all()
    return [enrich_rfq(r, db) for r in rfqs]


@app.get("/api/rfqs/{rfq_id}", response_model=schemas.RFQOut)
def get_rfq(rfq_id: int, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    rfq = db.query(models.RFQ).filter(models.RFQ.id == rfq_id).first()
    if not rfq:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="RFQ not found")
    # Check overdue
    if rfq.status == "Awaiting Quotes" and rfq.deadline and rfq.deadline < datetime.datetime.utcnow():
        rfq.status = "Overdue"
        db.commit()
    return enrich_rfq(rfq, db)


@app.put("/api/rfqs/{rfq_id}", response_model=schemas.RFQOut)
def update_rfq(rfq_id: int, payload: schemas.RFQUpdate, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    rfq = db.query(models.RFQ).filter(models.RFQ.id == rfq_id).first()
    if not rfq:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="RFQ not found")
    if rfq.status not in ["Awaiting Quotes", "Overdue"]:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot edit RFQ in current status")
    has_quotes = db.query(models.Quote).filter(models.Quote.rfq_id == rfq_id).first()
    if has_quotes:
        if payload.deadline is not None and payload.title is None and payload.description is None:
            rfq.deadline = payload.deadline
            if rfq.status == "Overdue" and rfq.deadline > datetime.datetime.utcnow():
                rfq.status = "Awaiting Quotes"
            db.commit()
            db.refresh(rfq)
            return enrich_rfq(rfq, db)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Can only extend deadline after first quote")
    if payload.title is not None:
        rfq.title = payload.title
    if payload.description is not None:
        rfq.description = payload.description
    if payload.deadline is not None:
        rfq.deadline = payload.deadline
    db.commit()
    db.refresh(rfq)
    return enrich_rfq(rfq, db)


@app.post("/api/rfqs/{rfq_id}/cancel", response_model=schemas.RFQOut)
def cancel_rfq(rfq_id: int, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    rfq = db.query(models.RFQ).filter(models.RFQ.id == rfq_id).first()
    if not rfq:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="RFQ not found")
    if rfq.status in ["Winner Selected", "Cancelled"]:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot cancel RFQ in current status")
    rfq.status = "Cancelled"
    db.commit()
    # Return PR to New
    pr = db.query(models.PurchaseRequest).filter(models.PurchaseRequest.id == rfq.purchase_request_id).first()
    if pr:
        new_stage = db.query(models.Stage).filter(models.Stage.name == "New").first()
        if new_stage and pr.current_stage_id != new_stage.id:
            old = pr.current_stage_id
            pr.current_stage_id = new_stage.id
            record_stage_history(db, pr.id, old, new_stage.id)
            db.commit()
    db.refresh(rfq)
    return enrich_rfq(rfq, db)


@app.get("/api/rfqs/{rfq_id}/quotes", response_model=List[schemas.QuoteComparisonOut])
def get_rfq_quotes(rfq_id: int, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    rfq = db.query(models.RFQ).filter(models.RFQ.id == rfq_id).first()
    if not rfq:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="RFQ not found")
    quotes = db.query(models.Quote).filter(models.Quote.rfq_id == rfq_id).all()
    if not quotes:
        return []
    totals = []
    for q in quotes:
        t = sum(li.unit_price * (li.request_line_item.quantity if li.request_line_item else 1) for li in q.line_items)
        totals.append(t)
    min_total = min(totals) if totals else 0
    result = []
    for q in quotes:
        total = sum(li.unit_price * (li.request_line_item.quantity if li.request_line_item else 1) for li in q.line_items)
        delivery = max((li.delivery_time_days for li in q.line_items), default=0)
        li_out = []
        for li in q.line_items:
            req = li.request_line_item
            li_out.append(schemas.QuoteLineItemOut(
                id=li.id,
                request_line_item_id=li.request_line_item_id,
                description=req.description if req else None,
                quantity=req.quantity if req else None,
                unit_price=li.unit_price,
                delivery_time_days=li.delivery_time_days,
                line_total=li.unit_price * (req.quantity if req else 1)
            ))
        result.append(schemas.QuoteComparisonOut(
            id=q.id,
            supplier_id=q.supplier_id,
            supplier_name=q.supplier.company_name,
            supplier_score=overall_score(q.supplier),
            line_items=li_out,
            total=total,
            delivery_time_days=delivery,
            payment_terms=q.payment_terms,
            is_lowest=(total == min_total)
        ))
    return result


@app.post("/api/rfqs/{rfq_id}/winner", response_model=schemas.RFQOut)
def select_winner(rfq_id: int, payload: schemas.WinnerSelect, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    rfq = db.query(models.RFQ).filter(models.RFQ.id == rfq_id).first()
    if not rfq:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="RFQ not found")
    if rfq.status not in ["Ready for Review", "Overdue"]:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot select winner in current status")
    quote = db.query(models.Quote).filter(models.Quote.id == payload.quote_id, models.Quote.rfq_id == rfq_id).first()
    if not quote:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Quote not found")
    totals = []
    for q in rfq.quotes:
        t = sum(li.unit_price * (li.request_line_item.quantity if li.request_line_item else 1) for li in q.line_items)
        totals.append(t)
    min_total = min(totals) if totals else 0
    quote_total = sum(li.unit_price * (li.request_line_item.quantity if li.request_line_item else 1) for li in quote.line_items)
    if quote_total != min_total and (not payload.justification or not payload.justification.strip()):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Justification required for non-lowest quote")
    rfq.status = "Winner Selected"
    rfq.winner_quote_id = payload.quote_id
    db.commit()
    # Move PR to Approved then Ordered
    pr = db.query(models.PurchaseRequest).filter(models.PurchaseRequest.id == rfq.purchase_request_id).first()
    approved_stage = db.query(models.Stage).filter(models.Stage.name == "Approved").first()
    ordered_stage = db.query(models.Stage).filter(models.Stage.name == "Ordered").first()
    if pr and approved_stage:
        old = pr.current_stage_id
        pr.current_stage_id = approved_stage.id
        record_stage_history(db, pr.id, old, approved_stage.id)
        db.commit()
    # Auto-create order
    delivery_days = max((li.delivery_time_days for li in quote.line_items), default=0)
    expected = datetime.date.today() + datetime.timedelta(days=delivery_days)
    total = sum(li.unit_price * (li.request_line_item.quantity if li.request_line_item else 1) for li in quote.line_items)
    order = models.PurchaseOrder(
        order_number=generate_order_number(db),
        purchase_request_id=rfq.purchase_request_id,
        supplier_id=quote.supplier_id,
        quote_id=quote.id,
        total=total,
        payment_terms=quote.payment_terms,
        expected_delivery=expected,
        current_status="Pending"
    )
    db.add(order)
    db.commit()
    db.add(models.OrderStatusHistory(order_id=order.id, status="Pending"))
    if pr and ordered_stage:
        old = pr.current_stage_id
        pr.current_stage_id = ordered_stage.id
        record_stage_history(db, pr.id, old, ordered_stage.id)
        db.commit()
    db.commit()
    db.refresh(rfq)
    return enrich_rfq(rfq, db)


# Supplier-facing Quote Submission (no auth)
@app.get("/api/quote/{token}")
def get_quote_by_token(token: str, db: Session = Depends(get_db)):
    rs = db.query(models.RFQSupplier).filter(models.RFQSupplier.quote_token == token).first()
    if not rs:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Token not found")
    rfq = rs.rfq
    if rfq.status in ["Cancelled", "Winner Selected"]:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="RFQ is closed")
    if rfq.deadline and rfq.deadline < datetime.datetime.utcnow():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Deadline passed")
    line_items = db.query(models.PurchaseRequestLineItem).filter(models.PurchaseRequestLineItem.request_id == rfq.purchase_request_id).all()
    li_out = [schemas.PurchaseRequestLineItemOut.from_orm(li) for li in line_items]
    return {
        "rfq_title": rfq.title,
        "rfq_description": rfq.description,
        "rfq_deadline": rfq.deadline,
        "supplier_name": rs.supplier.company_name,
        "line_items": li_out
    }


@app.post("/api/quote/{token}")
def submit_quote(token: str, payload: schemas.QuoteSubmit, db: Session = Depends(get_db)):
    rs = db.query(models.RFQSupplier).filter(models.RFQSupplier.quote_token == token).first()
    if not rs:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Token not found")
    rfq = rs.rfq
    if rfq.status in ["Cancelled", "Winner Selected"]:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="RFQ is closed")
    if rfq.deadline and rfq.deadline < datetime.datetime.utcnow():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Deadline passed")
    existing = db.query(models.Quote).filter(models.Quote.rfq_id == rfq.id, models.Quote.supplier_id == rs.supplier_id).first()
    if existing:
        # Revision
        existing.revision_number += 1
        existing.payment_terms = payload.payment_terms
        existing.notes = payload.notes
        existing.submitted_at = datetime.datetime.utcnow()
        db.query(models.QuoteLineItem).filter(models.QuoteLineItem.quote_id == existing.id).delete()
        for item in payload.line_items:
            db.add(models.QuoteLineItem(
                quote_id=existing.id,
                request_line_item_id=item.request_line_item_id,
                unit_price=item.unit_price,
                delivery_time_days=item.delivery_time_days
            ))
        db.commit()
        db.refresh(existing)
        revision = existing.revision_number
    else:
        quote = models.Quote(
            rfq_id=rfq.id,
            supplier_id=rs.supplier_id,
            revision_number=1,
            payment_terms=payload.payment_terms,
            notes=payload.notes
        )
        db.add(quote)
        db.commit()
        db.refresh(quote)
        for item in payload.line_items:
            db.add(models.QuoteLineItem(
                quote_id=quote.id,
                request_line_item_id=item.request_line_item_id,
                unit_price=item.unit_price,
                delivery_time_days=item.delivery_time_days
            ))
        db.commit()
        db.refresh(quote)
        existing = quote
        revision = 1
    # Check if all responded
    total_invited = len(rfq.suppliers)
    responded = db.query(models.Quote).filter(models.Quote.rfq_id == rfq.id).group_by(models.Quote.supplier_id).count()
    if responded == total_invited and rfq.status == "Awaiting Quotes":
        rfq.status = "Ready for Review"
        db.commit()
    return {"message": "Quote submitted", "revision_number": revision, "reference_number": f"Q-{existing.id}"}


# Purchase Orders
@app.get("/api/orders", response_model=List[schemas.PurchaseOrderOut])
def list_orders(db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    orders = db.query(models.PurchaseOrder).order_by(models.PurchaseOrder.created_at.desc()).all()
    result = []
    for o in orders:
        data = schemas.PurchaseOrderOut.from_orm(o)
        supplier = db.query(models.Supplier).filter(models.Supplier.id == o.supplier_id).first()
        data.supplier_name = supplier.company_name if supplier else None
        data.is_overdue = o.current_status != "Delivered" and o.expected_delivery < datetime.date.today()
        result.append(data)
    return result


@app.get("/api/orders/{order_id}", response_model=schemas.PurchaseOrderOut)
def get_order(order_id: int, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    order = db.query(models.PurchaseOrder).filter(models.PurchaseOrder.id == order_id).first()
    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
    data = schemas.PurchaseOrderOut.from_orm(order)
    supplier = db.query(models.Supplier).filter(models.Supplier.id == order.supplier_id).first()
    data.supplier_name = supplier.company_name if supplier else None
    data.is_overdue = order.current_status != "Delivered" and order.expected_delivery < datetime.date.today()
    return data


@app.put("/api/orders/{order_id}/status", response_model=schemas.PurchaseOrderOut)
def update_order_status(order_id: int, payload: schemas.OrderStatusUpdate, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    order = db.query(models.PurchaseOrder).filter(models.PurchaseOrder.id == order_id).first()
    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
    progression = ["Pending", "Confirmed", "Shipped", "Delivered"]
    if payload.status not in progression:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid status")
    if progression.index(payload.status) <= progression.index(order.current_status):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Status can only move forward")
    order.current_status = payload.status
    db.add(models.OrderStatusHistory(order_id=order.id, status=payload.status))
    db.commit()
    db.refresh(order)
    data = schemas.PurchaseOrderOut.from_orm(order)
    supplier = db.query(models.Supplier).filter(models.Supplier.id == order.supplier_id).first()
    data.supplier_name = supplier.company_name if supplier else None
    data.is_overdue = order.current_status != "Delivered" and order.expected_delivery < datetime.date.today()
    return data


@app.get("/api/orders/{order_id}/history", response_model=List[schemas.PurchaseOrderStatusHistoryOut])
def get_order_history(order_id: int, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    order = db.query(models.PurchaseOrder).filter(models.PurchaseOrder.id == order_id).first()
    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
    return db.query(models.OrderStatusHistory).filter(models.OrderStatusHistory.order_id == order_id).order_by(models.OrderStatusHistory.timestamp).all()


@app.post("/api/orders/{order_id}/rate", response_model=schemas.SupplierOut)
def rate_supplier(order_id: int, payload: schemas.RatingSubmit, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    order = db.query(models.PurchaseOrder).filter(models.PurchaseOrder.id == order_id).first()
    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
    if order.current_status != "Delivered":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Can only rate after delivery")
    supplier = db.query(models.Supplier).filter(models.Supplier.id == order.supplier_id).first()
    if not supplier:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Supplier not found")
    supplier.punctuality = payload.punctuality
    supplier.quality = payload.quality
    supplier.reliability = payload.reliability
    db.commit()
    db.refresh(supplier)
    return enrich_supplier(supplier)


@app.post("/api/orders/{order_id}/reorder", response_model=schemas.PurchaseRequestOut)
def reorder(order_id: int, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    order = db.query(models.PurchaseOrder).filter(models.PurchaseOrder.id == order_id).first()
    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
    po = db.query(models.PurchaseOrder).filter(models.PurchaseOrder.id == order_id).first()
    pr = db.query(models.PurchaseRequest).filter(models.PurchaseRequest.id == po.purchase_request_id).first()
    default_stage = get_default_stage(db)
    new_pr = models.PurchaseRequest(
        title=pr.title if pr else f"Reorder from {po.order_number}",
        priority=pr.priority if pr else "Medium",
        category_id=pr.category_id if pr else 1,
        notes=f"Reordered from order {po.order_number}",
        current_stage_id=default_stage.id,
        created_at=datetime.datetime.utcnow()
    )
    db.add(new_pr)
    db.commit()
    db.refresh(new_pr)
    quote = db.query(models.Quote).filter(models.Quote.id == po.quote_id).first()
    if quote:
        for li in quote.line_items:
            req_li = li.request_line_item
            if req_li:
                db.add(models.PurchaseRequestLineItem(
                    request_id=new_pr.id,
                    description=req_li.description,
                    quantity=req_li.quantity
                ))
    db.commit()
    record_stage_history(db, new_pr.id, None, default_stage.id)
    db.commit()
    db.refresh(new_pr)
    return enrich_purchase_request(new_pr, db)
