from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, EmailStr, Field, field_validator
from models import (
    UserRole, ServiceType, BookingType, Category, Urgency, 
    TimeWindow, BookingState, JobStatus, InvoiceStatus, EquipmentType
)


# Auth schemas
class UserCreate(BaseModel):
    name: str
    email: EmailStr
    password: str = Field(..., min_length=6)
    role: UserRole

    @field_validator('email')
    @classmethod
    def validate_email(cls, v):
        if '@' not in v or '.' not in v:
            raise ValueError('Invalid email format')
        return v


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class UserResponse(BaseModel):
    id: int
    name: str
    email: str
    role: UserRole
    class Config:
        from_attributes = True


# Property schemas
class PropertyCreate(BaseModel):
    label: str
    street: str
    city: str
    state: str
    zip_code: str = Field(..., min_length=5, max_length=5)

    @field_validator('zip_code')
    @classmethod
    def validate_zip(cls, v):
        if not v.isdigit():
            raise ValueError('ZIP must be 5 digits')
        return v


class PropertyResponse(BaseModel):
    id: int
    label: str
    street: str
    city: str
    state: str
    zip_code: str
    created_at: datetime
    class Config:
        from_attributes = True


# Equipment schemas
class EquipmentCreate(BaseModel):
    service_type: ServiceType
    equipment_type: EquipmentType
    manufacturer: Optional[str] = None
    model: Optional[str] = None
    serial: Optional[str] = None
    install_date: Optional[datetime] = None
    notes: Optional[str] = None


class EquipmentResponse(BaseModel):
    id: int
    service_type: ServiceType
    equipment_type: EquipmentType
    manufacturer: Optional[str]
    model: Optional[str]
    serial: Optional[str]
    install_date: Optional[datetime]
    notes: Optional[str]
    created_at: datetime
    class Config:
        from_attributes = True


# Booking schemas
class BookingCreate(BaseModel):
    service_type: ServiceType
    booking_type: BookingType
    category: Category
    urgency: Urgency
    name: Optional[str] = None
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    street: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zip_code: Optional[str] = None
    company_name: Optional[str] = None
    preferred_date: Optional[datetime] = None
    time_window: Optional[TimeWindow] = None
    description: Optional[str] = None
    property_id: Optional[int] = None

    @field_validator('phone')
    @classmethod
    def validate_phone(cls, v):
        if v and len(v) < 10:
            raise ValueError('Phone must be at least 10 digits')
        return v

    @field_validator('zip_code')
    @classmethod
    def validate_zip(cls, v):
        if v and (not v.isdigit() or len(v) != 5):
            raise ValueError('ZIP must be exactly 5 digits')
        return v


class BookingResponse(BaseModel):
    id: int
    tracking_token: str
    service_type: str
    booking_type: str
    category: str
    urgency: str
    name: str
    email: str
    phone: str
    street: str
    city: str
    state: str
    zip_code: str
    company_name: Optional[str]
    preferred_date: Optional[datetime]
    time_window: Optional[str]
    description: Optional[str]
    state: str
    created_at: datetime
    class Config:
        from_attributes = True


class BookingSummary(BaseModel):
    id: int
    tracking_token: str
    service_type: str
    booking_type: str
    category: str
    urgency: str
    state: str


# Job schemas
class JobCreate(BaseModel):
    scheduled_date: datetime
    time_window: TimeWindow


class JobNoteCreate(BaseModel):
    content: str


class JobPhotoCreate(BaseModel):
    filename: str


class JobNoteResponse(BaseModel):
    id: int
    content: str
    created_at: datetime
    class Config:
        from_attributes = True


class JobPhotoResponse(BaseModel):
    id: int
    filename: str
    created_at: datetime
    class Config:
        from_attributes = True


class JobResponse(BaseModel):
    id: int
    booking_id: int
    technician_name: str
    scheduled_date: datetime
    time_window: str
    status: str
    street: str
    city: str
    state: str
    zip_code: str
    notes: List[JobNoteResponse]
    photos: List[JobPhotoResponse]
    created_at: datetime
    class Config:
        from_attributes = True


# Invoice schemas
class InvoiceCreate(BaseModel):
    amount: int = Field(..., gt=0)
    due_date: datetime


class InvoiceResponse(BaseModel):
    id: int
    job_id: int
    amount: int
    due_date: datetime
    status: str
    created_at: datetime
    class Config:
        from_attributes = True
