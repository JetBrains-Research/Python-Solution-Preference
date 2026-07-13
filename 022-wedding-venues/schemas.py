from pydantic import BaseModel, EmailStr, Field, validator
from typing import Optional, List
from datetime import datetime, date
from models import UserRole, VenueType, VenueStatus, TourType, TourStatus, BookingStatus, AvailabilityStatus

class UserBase(BaseModel):
    email: EmailStr
    password: str
    role: UserRole

class CoupleSignUp(UserBase):
    partner_name1: str
    partner_name2: str
    postcode: str
    wedding_date: datetime
    venue_type_pref: VenueType

class ManagerSignUp(UserBase):
    manager_name: str
    phone: str
    business_name: str

class UserResponse(BaseModel):
    id: int
    email: EmailStr
    role: UserRole
    
    class Config:
        orm_mode = True

class VenueCreate(BaseModel):
    name: str
    address: str
    postcode: str
    description: str = Field(..., min_length=200)
    contact_info: str
    min_guests: int
    max_guests: int
    base_fee: float
    per_person_fee: float
    venue_type: VenueType
    status: VenueStatus = VenueStatus.ACTIVE
    main_image_url: Optional[str] = None

class VenueResponse(BaseModel):
    id: int
    name: str
    address: str
    postcode: str
    description: str
    contact_info: str
    min_guests: int
    max_guests: int
    base_fee: float
    per_person_fee: float
    venue_type: VenueType
    status: VenueStatus
    main_image_url: Optional[str]
    estimated_price: Optional[float] = None

    class Config:
        orm_mode = True

class SearchParams(BaseModel):
    postcode: str
    date: datetime
    guest_count: int
    min_price: Optional[float] = None
    max_price: Optional[float] = None
    venue_type: Optional[VenueType] = None
    sort_by: str = "distance" # "distance" or "price"

class AvailabilityUpdate(BaseModel):
    date: datetime
    status: AvailabilityStatus
    note: Optional[str] = None

class AvailabilityResponse(BaseModel):
    date: datetime
    status: AvailabilityStatus
    note: Optional[str] = None

class TourSlotCreate(BaseModel):
    date: datetime
    time: str # HH:MM
    duration_minutes: int
    capacity: int

class TourSlotResponse(BaseModel):
    id: int
    start_time: datetime
    duration_minutes: int
    capacity: int

    class Config:
        orm_mode = True

class TourBookingRequest(BaseModel):
    slot_id: int
    tour_type: TourType
    attendee_count: int
    notes: Optional[str] = None

class TourBookingResponse(BaseModel):
    id: int
    slot_id: int
    status: TourStatus
    tour_type: TourType
    attendee_count: int
    notes: Optional[str]

    class Config:
        orm_mode = True

class WeddingBookingRequest(BaseModel):
    venue_id: int
    date: datetime
    guest_count: int
    note: Optional[str] = None

class WeddingBookingResponse(BaseModel):
    id: int
    venue_id: int
    date: datetime
    guest_count: int
    status: BookingStatus
    note: Optional[str]
    decline_reason: Optional[str]

    class Config:
        orm_mode = True
