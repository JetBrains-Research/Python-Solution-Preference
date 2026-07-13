from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import Optional

from models import User, get_db, UserRole
from schemas import UserCreateCouple, UserCreateManager, UserResponse, UserDetailResponse
from utils import hash_password, verify_password

router = APIRouter(prefix="/accounts", tags=["accounts"])

@router.post("/signup", response_model=UserDetailResponse, status_code=status.HTTP_201_CREATED)
def signup(user_data: UserCreateCouple | UserCreateManager, db: Session = Depends(get_db)):
    """
    Sign up with email, password, and role.
    Couples provide partner names, postcode, wedding date, venue type preference.
    Managers provide name, phone, business name.
    """
    # Check if email already exists
    existing_user = db.query(User).filter(User.email == user_data.email).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )
    
    hashed_password = hash_password(user_data.password)
    
    if user_data.role == UserRole.COUPLE:
        couple_data = user_data
        new_user = User(
            email=couple_data.email,
            password_hash=hashed_password,
            role=UserRole.COUPLE.value,
            partner_name=couple_data.partner_name,
            postcode=couple_data.postcode,
            wedding_date=couple_data.wedding_date,
            venue_type_preference=couple_data.venue_type_preference
        )
    else:
        manager_data = user_data
        new_user = User(
            email=manager_data.email,
            password_hash=hashed_password,
            role=UserRole.MANAGER.value,
            name=manager_data.name,
            phone=manager_data.phone,
            business_name=manager_data.business_name
        )
    
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    
    return new_user

@router.post("/login", response_model=UserDetailResponse)
def login(email: str = Query(...), password: str = Query(...), db: Session = Depends(get_db)):
    """
    Login with email and password.
    """
    user = db.query(User).filter(User.email == email).first()
    
    if not user or not verify_password(password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password"
        )
    
    return user

@router.get("/me", response_model=UserDetailResponse)
def get_current_user(user_id: int, db: Session = Depends(get_db)):
    """
    Get current user details.
    """
    user = db.query(User).filter(User.id == user_id).first()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    return user
