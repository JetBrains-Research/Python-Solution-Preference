from datetime import datetime, date
from typing import Optional, List
from enum import Enum
from sqlalchemy import create_engine, Column, Integer, String, Float, Text, DateTime, Date, ForeignKey, Boolean
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
import os

Base = declarative_base()

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

# Models
class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    password_hash = Column(String, nullable=False)
    role = Column(String, nullable=False)
    
    # Couple-specific fields
    partner_name = Column(String, nullable=True)
    postcode = Column(String, nullable=True)
    wedding_date = Column(Date, nullable=True)
    venue_type_preference = Column(String, nullable=True)  # Indoor/Outdoor/Either
    
    # Manager-specific fields
    name = Column(String, nullable=True)
    phone = Column(String, nullable=True)
    business_name = Column(String, nullable=True)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    venues = relationship("Venue", back_populates="manager", foreign_keys="Venue.manager_id")
    tour_bookings = relationship("TourBooking", back_populates="couple", foreign_keys="TourBooking.couple_id")
    wedding_bookings = relationship("WeddingBooking", back_populates="couple", foreign_keys="WeddingBooking.couple_id")


class Venue(Base):
    __tablename__ = "venues"
    
    id = Column(Integer, primary_key=True, index=True)
    manager_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    
    name = Column(String, nullable=False)
    address = Column(String, nullable=False)
    postcode = Column(String, nullable=False)
    description = Column(Text, nullable=False)
    contact_info = Column(String, nullable=False)
    
    min_capacity = Column(Integer, nullable=False)
    max_capacity = Column(Integer, nullable=False)
    
    base_fee = Column(Float, nullable=False)
    per_person_fee = Column(Float, nullable=False)
    
    venue_type = Column(String, nullable=False)  # Indoor/Outdoor/Both
    status = Column(String, nullable=False, default="Active")
    
    main_image = Column(String, nullable=True)
    images = Column(Text, nullable=True)  # JSON-like string of image URLs
    
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    manager = relationship("User", back_populates="venues", foreign_keys=[manager_id])
    blocked_dates = relationship("BlockedDate", back_populates="venue")
    tour_slots = relationship("TourSlot", back_populates="venue")
    wedding_bookings = relationship("WeddingBooking", back_populates="venue")


class BlockedDate(Base):
    __tablename__ = "blocked_dates"
    
    id = Column(Integer, primary_key=True, index=True)
    venue_id = Column(Integer, ForeignKey("venues.id"), nullable=False)
    blocked_date = Column(Date, nullable=False)
    note = Column(String, nullable=True)
    
    venue = relationship("Venue", back_populates="blocked_dates")
    
    __table_args__ = (
        {'sqlite_autoincrement': True},
    )


class TourSlot(Base):
    __tablename__ = "tour_slots"
    
    id = Column(Integer, primary_key=True, index=True)
    venue_id = Column(Integer, ForeignKey("venues.id"), nullable=False)
    
    slot_date = Column(Date, nullable=False)
    slot_time = Column(String, nullable=False)  # HH:MM format
    duration_minutes = Column(Integer, nullable=False)
    capacity = Column(Integer, nullable=False)  # Number of groups
    remaining_capacity = Column(Integer, nullable=False)
    
    venue = relationship("Venue", back_populates="tour_slots")
    bookings = relationship("TourBooking", back_populates="slot")
    
    __table_args__ = (
        {'sqlite_autoincrement': True},
    )


class TourBooking(Base):
    __tablename__ = "tour_bookings"
    
    id = Column(Integer, primary_key=True, index=True)
    slot_id = Column(Integer, ForeignKey("tour_slots.id"), nullable=False)
    couple_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    
    tour_type = Column(String, nullable=False)  # In-Person/Virtual
    attendee_count = Column(Integer, nullable=False)
    notes = Column(String, nullable=True)
    
    status = Column(String, nullable=False, default="Pending")
    created_at = Column(DateTime, default=datetime.utcnow)
    
    slot = relationship("TourSlot", back_populates="bookings")
    couple = relationship("User", back_populates="tour_bookings", foreign_keys=[couple_id])


class WeddingBooking(Base):
    __tablename__ = "wedding_bookings"
    
    id = Column(Integer, primary_key=True, index=True)
    venue_id = Column(Integer, ForeignKey("venues.id"), nullable=False)
    couple_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    
    booking_date = Column(Date, nullable=False)
    guest_count = Column(Integer, nullable=False)
    note = Column(String, nullable=True)
    
    status = Column(String, nullable=False, default="Pending")
    estimated_price = Column(Float, nullable=False)
    decline_reason = Column(String, nullable=True)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    venue = relationship("Venue", back_populates="wedding_bookings")
    couple = relationship("User", back_populates="wedding_bookings", foreign_keys=[couple_id])
    
    __table_args__ = (
        {'sqlite_autoincrement': True},
    )


# Database setup
DATABASE_URL = "sqlite:///./wedding_venue.db"
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# Create tables
Base.metadata.create_all(bind=engine)
