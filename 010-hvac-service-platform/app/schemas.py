from pydantic import BaseModel, EmailStr, Field, validator
from typing import Optional, List
from datetime import date, datetime
from app.models import UserRole, ServiceType, BookingType, Category, Urgency, TimeWindow, EquipmentType, JobStatus, InvoiceStatus

class UserBase(BaseModel):
    name: str
    email: EmailStr
    role: UserRole

class UserCreate(UserBase):
    password: str = Field(..., min_length=6)

class UserOut(UserBase):
    id: int
    class Config:
        from_attributes = True

class Token(BaseModel):
    access_token: str
    token_type: str

class PropertyBase(BaseModel):
    label: str
    street: str
    city: str
    state: str
    zip_code: str = Field(..., min_length=5, max_length=5)

class PropertyCreate(PropertyBase):
    pass

class PropertyOut(PropertyBase):
    id: int
    owner_id: int
    class Config:
        from_attributes = True

class EquipmentBase(BaseModel):
    service_type: ServiceType
    equipment_type: EquipmentType
    manufacturer: Optional[str] = None
    model: Optional[str] = None
    serial: Optional[str] = None
    install_date: Optional[date] = None
    notes: Optional[str] = None

class EquipmentCreate(EquipmentBase):
    property_id: int

class EquipmentOut(EquipmentBase):
    id: int
    property_id: int
    class Config:
        from_attributes = True

class BookingBase(BaseModel):
    service_type: ServiceType
    booking_type: BookingType
    category: Category
    urgency: Urgency
    name: str
    email: EmailStr
    phone: str = Field(..., min_length=10)
    street: str
    city: str
    state: str
    zip_code: str = Field(..., min_length=5, max_length=5)
    company_name: Optional[str] = None
    preferred_date: Optional[date] = None
    time_window: Optional[TimeWindow] = None
    description: Optional[str] = None

    @validator('preferred_date')
    def date_not_in_past(cls, v):
        if v and v < date.today():
            raise ValueError('Preferred date cannot be in the past')
        return v

class BookingCreate(BookingBase):
    property_id: Optional[int] = None

class BookingOut(BookingBase):
    id: int
    tracking_token: str
    status: str
    client_id: Optional[int]
    property_id: Optional[int]
    class Config:
        from_attributes = True

class JobConvert(BaseModel):
    scheduled_date: date
    scheduled_time: str

    @validator('scheduled_date')
    def date_not_in_past(cls, v):
        if v < date.today():
            raise ValueError('Scheduled date cannot be in the past')
        return v

class JobStatusUpdate(BaseModel):
    status: JobStatus

class JobNoteCreate(BaseModel):
    content: str

class JobNoteOut(BaseModel):
    id: int
    content: str
    created_at: datetime
    class Config:
        from_attributes = True

class JobPhotoCreate(BaseModel):
    url: str

class JobPhotoOut(BaseModel):
    id: int
    url: str
    created_at: datetime
    class Config:
        from_attributes = True

class JobOut(BaseModel):
    id: int
    booking_id: int
    scheduled_date: date
    scheduled_time: str
    status: JobStatus
    technician_id: int
    notes: List[JobNoteOut] = []
    photos: List[JobPhotoOut] = []
    class Config:
        from_attributes = True

class InvoiceCreate(BaseModel):
    amount: float = Field(..., gt=0)
    due_date: date

    @validator('due_date')
    def date_not_in_past(cls, v):
        if v < date.today():
            raise ValueError('Due date cannot be in the past')
        return v

class InvoiceStatusUpdate(BaseModel):
    status: InvoiceStatus

class InvoiceOut(BaseModel):
    id: int
    job_id: int
    amount: float
    due_date: date
    status: InvoiceStatus
    created_at: datetime
    class Config:
        from_attributes = True
