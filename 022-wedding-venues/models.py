from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Enum, Boolean, Text
from sqlalchemy.orm import relationship
from database import Base
import enum

class UserRole(enum.Enum):
    COUPLE = "couple"
    MANAGER = "manager"

class VenueType(enum.Enum):
    INDOOR = "Indoor"
    OUTDOOR = "Outdoor"
    BOTH = "Both"

class VenueStatus(enum.Enum):
    ACTIVE = "Active"
    INACTIVE = "Inactive"

class TourType(enum.Enum):
    IN_PERSON = "In-Person"
    VIRTUAL = "Virtual"

class TourStatus(enum.Enum):
    PENDING = "Pending"
    APPROVED = "Approved"
    DENIED = "Denied"

class BookingStatus(enum.Enum):
    PENDING = "Pending"
    CONFIRMED = "Confirmed"
    DECLINED = "Declined"

class AvailabilityStatus(enum.Enum):
    AVAILABLE = "Available"
    BLOCKED = "Blocked"
    BOOKED = "Booked"

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    password = Column(String, nullable=False)
    role = Column(Enum(UserRole), nullable=False)
    
    # Couple specific
    partner_name1 = Column(String, nullable=True)
    partner_name2 = Column(String, nullable=True)
    postcode = Column(String, nullable=True)
    wedding_date = Column(DateTime, nullable=True)
    venue_type_pref = Column(Enum(VenueType), nullable=True)
    
    # Manager specific
    manager_name = Column(String, nullable=True)
    phone = Column(String, nullable=True)
    business_name = Column(String, nullable=True)

class Venue(Base):
    __tablename__ = "venues"
    id = Column(Integer, primary_key=True, index=True)
    manager_id = Column(Integer, ForeignKey("users.id"))
    name = Column(String, nullable=False)
    address = Column(String, nullable=False)
    postcode = Column(String, nullable=False)
    description = Column(Text, nullable=False) # min 200 chars check in schema
    contact_info = Column(String, nullable=False)
    min_guests = Column(Integer, nullable=False)
    max_guests = Column(Integer, nullable=False)
    base_fee = Column(Float, nullable=False)
    per_person_fee = Column(Float, nullable=False)
    venue_type = Column(Enum(VenueType), nullable=False)
    status = Column(Enum(VenueStatus), default=VenueStatus.ACTIVE)
    main_image_url = Column(String, nullable=True)

class Availability(Base):
    __tablename__ = "availabilities"
    id = Column(Integer, primary_key=True, index=True)
    venue_id = Column(Integer, ForeignKey("venues.id"))
    date = Column(DateTime, nullable=False)
    status = Column(Enum(AvailabilityStatus), default=AvailabilityStatus.AVAILABLE)
    note = Column(String, nullable=True)

class TourSlot(Base):
    __tablename__ = "tour_slots"
    id = Column(Integer, primary_key=True, index=True)
    venue_id = Column(Integer, ForeignKey("venues.id"))
    start_time = Column(DateTime, nullable=False)
    duration_minutes = Column(Integer, nullable=False)
    capacity = Column(Integer, nullable=False) # current available capacity

class TourBooking(Base):
    __tablename__ = "tour_bookings"
    id = Column(Integer, primary_key=True, index=True)
    slot_id = Column(Integer, ForeignKey("tour_slots.id"))
    couple_id = Column(Integer, ForeignKey("users.id"))
    tour_type = Column(Enum(TourType), nullable=False)
    attendee_count = Column(Integer, nullable=False)
    notes = Column(String, nullable=True)
    status = Column(Enum(TourStatus), default=TourStatus.PENDING)

class WeddingBooking(Base):
    __tablename__ = "wedding_bookings"
    id = Column(Integer, primary_key=True, index=True)
    venue_id = Column(Integer, ForeignKey("venues.id"))
    couple_id = Column(Integer, ForeignKey("users.id"))
    date = Column(DateTime, nullable=False)
    guest_count = Column(Integer, nullable=False)
    note = Column(String, nullable=True)
    status = Column(Enum(BookingStatus), default=BookingStatus.PENDING)
    decline_reason = Column(String, nullable=True)
