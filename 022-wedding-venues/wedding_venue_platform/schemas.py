from datetime import datetime, date
from typing import Optional, List, Union
from pydantic import BaseModel, Field, validator
from enum import Enum

# Enums
class UserRole(str, Enum):
    COUPLE = "couple"
    MANAGER = "manager"

class VenueType(str, Enum):
    INDOOR = "Indoor"
    OUTDOOR = "Outdoor"
    BOTH = "Both"

class VenueStatus(str, Enum):
    ACTIVE = "Active"
    INACTIVE = "Inactive"

class DateStatus(str, Enum):
    AVAILABLE = "Available"
    BLOCKED = "Blocked"
    BOOKED = "Booked"

class TourType(str, Enum):
    IN_PERSON = "In-Person"
    VIRTUAL = "Virtual"

class TourStatus(str, Enum):
    PENDING = "Pending"
    APPROVED = "Approved"
    DENIED = "Denied"

class BookingStatus(str, Enum):
    PENDING = "Pending"
    CONFIRMED = "Confirmed"
    DECLINED = "Declined"

# User schemas
class UserBase(BaseModel):
    email: str
    password: str = Field(..., min_length=8)
    role: UserRole

class UserCreateCouple(UserBase):
    role: UserRole = UserRole.COUPLE
    partner_name: str
    postcode: str
    wedding_date: date
    venue_type_preference: str  # Indoor/Outdoor/Either

class UserCreateManager(UserBase):
    role: UserRole = UserRole.MANAGER
    name: str
    phone: str
    business_name: str

class UserResponse(BaseModel):
    id: int
    email: str
    role: UserRole
    created_at: datetime
    
    class Config:
        from_attributes = True

class UserDetailResponse(BaseModel):
    id: int
    email: str
    role: UserRole
    created_at: datetime
    
    # Couple fields
    partner_name: Optional[str] = None
    postcode: Optional[str] = None
    wedding_date: Optional[date] = None
    venue_type_preference: Optional[str] = None
    
    # Manager fields
    name: Optional[str] = None
    phone: Optional[str] = None
    business_name: Optional[str] = None
    
    class Config:
        from_attributes = True

# Venue schemas
class VenueBase(BaseModel):
    name: str
    address: str
    postcode: str
    description: str = Field(..., min_length=200)
    contact_info: str
    min_capacity: int
    max_capacity: int
    base_fee: float
    per_person_fee: float
    venue_type: VenueType
    status: VenueStatus = VenueStatus.ACTIVE
    main_image: Optional[str] = None
    images: Optional[List[str]] = None

class VenueCreate(VenueBase):
    pass

class VenueUpdate(BaseModel):
    name: Optional[str] = None
    address: Optional[str] = None
    postcode: Optional[str] = None
    description: Optional[str] = None
    contact_info: Optional[str] = None
    min_capacity: Optional[int] = None
    max_capacity: Optional[int] = None
    base_fee: Optional[float] = None
    per_person_fee: Optional[float] = None
    venue_type: Optional[VenueType] = None
    status: Optional[VenueStatus] = None
    main_image: Optional[str] = None
    images: Optional[List[str]] = None

class VenueResponse(BaseModel):
    id: int
    manager_id: int
    name: str
    address: str
    postcode: str
    description: str
    contact_info: str
    min_capacity: int
    max_capacity: int
    base_fee: float
    per_person_fee: float
    venue_type: str
    status: str
    main_image: Optional[str] = None
    images: Optional[Union[List[str], str]] = None
    created_at: datetime
    
    class Config:
        from_attributes = True

class VenueDetailResponse(BaseModel):
    id: int
    manager_id: int
    name: str
    address: str
    postcode: str
    description: str
    contact_info: str
    min_capacity: int
    max_capacity: int
    base_fee: float
    per_person_fee: float
    venue_type: str
    status: str
    main_image: Optional[str] = None
    images: Optional[Union[List[str], str]] = None
    created_at: datetime
    estimated_price: Optional[float] = None
    availability_calendar: dict = {}

# Search schemas
class SearchRequest(BaseModel):
    postcode: str
    date: date
    guest_count: int
    min_price: Optional[float] = None
    max_price: Optional[float] = None
    venue_type: Optional[str] = None  # Indoor/Outdoor/Both/Either

class SearchResponse(BaseModel):
    id: int
    name: str
    address: str
    postcode: str
    venue_type: str
    min_capacity: int
    max_capacity: int
    base_fee: float
    per_person_fee: float
    distance_miles: float
    estimated_price: float
    
    class Config:
        from_attributes = True

# Blocked date schemas
class BlockedDateCreate(BaseModel):
    blocked_date: date
    note: Optional[str] = None

class BlockedDateUpdate(BaseModel):
    note: Optional[str] = None

class BlockedDateResponse(BaseModel):
    id: int
    venue_id: int
    blocked_date: date
    note: Optional[str] = None
    
    class Config:
        from_attributes = True

# Tour slot schemas
class TourSlotCreate(BaseModel):
    slot_date: date
    slot_time: str  # HH:MM format
    duration_minutes: int
    capacity: int

class TourSlotResponse(BaseModel):
    id: int
    venue_id: int
    slot_date: date
    slot_time: str
    duration_minutes: int
    capacity: int
    remaining_capacity: int
    is_full: bool = False
    
    class Config:
        from_attributes = True

# Tour booking schemas
class TourBookingCreate(BaseModel):
    slot_id: int
    tour_type: TourType
    attendee_count: int
    notes: Optional[str] = None

class TourBookingResponse(BaseModel):
    id: int
    slot_id: int
    couple_id: int
    tour_type: str
    attendee_count: int
    notes: Optional[str] = None
    status: str
    created_at: datetime
    
    class Config:
        from_attributes = True

class TourBookingUpdate(BaseModel):
    status: str

# Wedding booking schemas
class WeddingBookingCreate(BaseModel):
    venue_id: int
    booking_date: date
    guest_count: int
    note: Optional[str] = None

class WeddingBookingResponse(BaseModel):
    id: int
    venue_id: int
    couple_id: int
    booking_date: date
    guest_count: int
    note: Optional[str] = None
    status: str
    estimated_price: float
    decline_reason: Optional[str] = None
    created_at: datetime
    
    class Config:
        from_attributes = True

class WeddingBookingUpdate(BaseModel):
    status: str
    decline_reason: Optional[str] = None

# Availability calendar schema
class AvailabilityDay(BaseModel):
    date: date
    status: DateStatus
    note: Optional[str] = None

class AvailabilityCalendar(BaseModel):
    days: List[AvailabilityDay]
