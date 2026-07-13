from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List

from app.database import get_db
from app.database.models import User, UserRole
from app.api.v1.endpoints.auth import get_current_admin_user, get_current_active_user, get_password_hash
from app.api.v1.schemas.users import UserCreate, UserUpdate, UserSchema

router = APIRouter()

@router.get("/", response_model=List[UserSchema])
async def list_users(current_user: User = Depends(get_current_admin_user), db: Session = Depends(get_db)):
    users = db.query(User).all()
    return users

@router.post("/", response_model=UserSchema)
async def create_user(user_data: UserCreate, current_user: User = Depends(get_current_admin_user), db: Session = Depends(get_db)):
    existing_user = db.query(User).filter(User.username == user_data.username).first()
    if existing_user:
        raise HTTPException(status_code=400, detail="Username already exists")

    existing_email = db.query(User).filter(User.email == user_data.email).first()
    if existing_email:
        raise HTTPException(status_code=400, detail="Email already exists")

    role = UserRole(user_data.role) if user_data.role else UserRole.BUYER

    user = User(
        username=user_data.username,
        password_hash=get_password_hash(user_data.password),
        email=user_data.email,
        full_name=user_data.full_name,
        is_active=True,
        role=role
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user

@router.get("/{user_id}", response_model=UserSchema)
async def get_user(user_id: int, current_user: User = Depends(get_current_admin_user), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user

@router.put("/{user_id}", response_model=UserSchema)
async def update_user(user_id: int, user_data: UserUpdate, current_user: User = Depends(get_current_admin_user), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if user.id == current_user.id and user_data.is_active is not None and not user_data.is_active:
        raise HTTPException(status_code=400, detail="Users cannot deactivate their own account")

    if user_data.email:
        existing_email = db.query(User).filter(User.email == user_data.email, User.id != user_id).first()
        if existing_email:
            raise HTTPException(status_code=400, detail="Email already exists")

    update_data = user_data.model_dump(exclude_unset=True)
    if "password" in update_data:
        update_data["password_hash"] = get_password_hash(update_data.pop("password"))

    for key, value in update_data.items():
        setattr(user, key, value)

    db.commit()
    db.refresh(user)
    return user

@router.patch("/{user_id}/activate", response_model=UserSchema)
async def toggle_user_active(user_id: int, current_user: User = Depends(get_current_admin_user), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if user.id == current_user.id:
        raise HTTPException(status_code=400, detail="Users cannot deactivate their own account")

    user.is_active = not user.is_active
    db.commit()
    db.refresh(user)
    return user
