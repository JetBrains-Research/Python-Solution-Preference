from pydantic import BaseModel, EmailStr, Field, validator
from typing import Optional, List
from datetime import datetime
from enum import Enum

class RoleEnum(str, Enum):
    PHOTOGRAPHER = "Photographer"
    FILMMAKER = "Filmmaker"
    DESIGNER = "Designer"
    WRITER = "Writer"
    VISUAL_ARTIST = "Visual Artist"
    OTHER = "Other"

class EventCategoryEnum(str, Enum):
    WORKSHOP = "workshop"
    NETWORKING = "networking"
    EXHIBITION = "exhibition"
    SCREENING = "screening"
    SOCIAL = "social"

class PaymentStatusEnum(str, Enum):
    UNPAID = "unpaid"
    PROCESSING = "processing"
    PAID = "paid"

class InviteCodeTypeEnum(str, Enum):
    SINGLE = "single"
    MULTI = "multi"

# User
class UserBase(BaseModel):
    username: str
    email: EmailStr

class UserCreate(UserBase):
    password: str
    invite_code: str

class UserProfileUpdate(BaseModel):
    full_name: str
    location: str
    creative_role: RoleEnum
    phone: Optional[str] = None
    bio: Optional[str] = Field(None, max_length=500)

class UserOut(UserBase):
    id: int
    is_admin: bool
    full_name: Optional[str]
    location: Optional[str]
    creative_role: Optional[str]
    
    class Config:
        orm_mode = True

# Invite Code
class InviteCodeCreate(BaseModel):
    code: str
    code_type: InviteCodeTypeEnum
    max_uses: int
    expiration_date: datetime
    description: Optional[str] = None

class InviteCodeOut(BaseModel):
    id: int
    code: str
    code_type: str
    max_uses: int
    uses: int
    expiration_date: datetime
    is_active: bool
    description: Optional[str]
    
    class Config:
        orm_mode = True

# Event
class EventCreate(BaseModel):
    title: str
    description: str
    date_time: datetime
    location: str
    category: EventCategoryEnum
    capacity: int
    price: float = 0.0

class EventListOut(BaseModel):
    id: int
    title: str
    description: str
    date_time: datetime
    location: str
    category: str
    capacity_remaining: str
    price: str

    @classmethod
    def from_orm_event(cls, event, attendance_count):
        remaining = event.capacity - attendance_count
        return cls(
            id=event.id,
            title=event.title,
            description=event.description[:100],
            date_time=event.date_time,
            location=event.location,
            category=event.category,
            capacity_remaining=f"{remaining} spots remaining" if remaining > 0 else "Full",
            price="Free" if event.price == 0 else f"${event.price:.2f}"
        )

class EventDetailOut(BaseModel):
    id: int
    title: str
    description: str
    date_time: datetime
    location: str
    category: str
    capacity: int
    price: float
    has_passed: bool = False
    
    class Config:
        orm_mode = True

class AttendeeOut(BaseModel):
    full_name: str
    creative_role: str
    
    class Config:
        orm_mode = True

# Attendance
class AttendanceOut(BaseModel):
    event_name: str
    date_time: datetime
    amount_owed: float
    payment_status: PaymentStatusEnum
    
    class Config:
        orm_mode = True

class AttendanceAdminOut(BaseModel):
    id: int
    user_id: int
    username: str
    full_name: str
    event_id: int
    event_title: str
    attended: bool
    amount_owed: float
    payment_status: PaymentStatusEnum
    payment_date: Optional[datetime]
    admin_notes: Optional[str]
    
    class Config:
        orm_mode = True

class Token(BaseModel):
    access_token: str
    token_type: str
