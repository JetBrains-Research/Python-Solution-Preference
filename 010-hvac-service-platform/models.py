from datetime import datetime
from enum import Enum
from typing import Optional, List
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Enum as SQLEnum, Boolean, Text, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
import uuid

Base = declarative_base()


class UserRole(str, Enum):
    CLIENT = "Client"
    TECHNICIAN = "Technician"


class ServiceType(str, Enum):
    HVAC = "HVAC"
    PLUMBING = "Plumbing"


class BookingType(str, Enum):
    RESIDENTIAL = "Residential"
    COMMERCIAL = "Commercial"


class Category(str, Enum):
    INSTALLATION = "Installation"
    REPAIR = "Repair"
    MAINTENANCE = "Maintenance"
    EMERGENCY = "Emergency"


class Urgency(str, Enum):
    STANDARD = "Standard"
    URGENT = "Urgent"
    EMERGENCY = "Emergency"


class TimeWindow(str, Enum):
    AM = "AM"
    PM = "PM"
    ANY = "Any"


class BookingState(str, Enum):
    NEW = "New"
    CONVERTED = "Converted"


class JobStatus(str, Enum):
    SCHEDULED = "Scheduled"
    IN_PROGRESS = "In Progress"
    COMPLETED = "Completed"


class InvoiceStatus(str, Enum):
    DRAFT = "Draft"
    SENT = "Sent"
    PAID = "Paid"
    VOID = "Void"
    OVERDUE = "Overdue"


class EquipmentType(str, Enum):
    FURNACE = "Furnace"
    AC = "AC"
    HEAT_PUMP = "Heat Pump"
    BOILER = "Boiler"
    WATER_HEATER = "Water Heater"
    THERMOSTAT = "Thermostat"
    HUMIDIFIER = "Humidifier"
    AIR_PURIFIER = "Air Purifier"
    WATER_SOFTENER = "Water Softener"
    PLUMBING_FIXTURE = "Plumbing Fixture"
    OTHER = "Other"


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    email = Column(String, unique=True, index=True, nullable=False)
    password_hash = Column(String, nullable=False)
    role = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    properties = relationship("Property", back_populates="owner", cascade="all, delete-orphan")
    bookings = relationship("Booking", back_populates="client", foreign_keys="Booking.client_id")
    assigned_jobs = relationship("Job", back_populates="assigned_technician", foreign_keys="Job.technician_id")
    created_invoices = relationship("Invoice", back_populates="creator", foreign_keys="Invoice.creator_id")


class Property(Base):
    __tablename__ = "properties"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    label = Column(String, nullable=False)
    street = Column(String, nullable=False)
    city = Column(String, nullable=False)
    state = Column(String, nullable=False)
    zip_code = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    owner = relationship("User", back_populates="properties")
    equipment = relationship("Equipment", back_populates="property", cascade="all, delete-orphan")


class Equipment(Base):
    __tablename__ = "equipment"

    id = Column(Integer, primary_key=True, index=True)
    property_id = Column(Integer, ForeignKey("properties.id", ondelete="CASCADE"), nullable=False)
    service_type = Column(String, nullable=False)
    equipment_type = Column(String, nullable=False)
    manufacturer = Column(String, nullable=True)
    model = Column(String, nullable=True)
    serial = Column(String, nullable=True)
    install_date = Column(DateTime, nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    property = relationship("Property", back_populates="equipment")


class Booking(Base):
    __tablename__ = "bookings"

    id = Column(Integer, primary_key=True, index=True)
    tracking_token = Column(String, unique=True, index=True, nullable=False)
    service_type = Column(String, nullable=False)
    booking_type = Column(String, nullable=False)
    category = Column(String, nullable=False)
    urgency = Column(String, nullable=False)
    name = Column(String, nullable=False)
    email = Column(String, nullable=False)
    phone = Column(String, nullable=False)
    street = Column(String, nullable=False)
    city = Column(String, nullable=False)
    state = Column(String, nullable=False)
    zip_code = Column(String, nullable=False)
    company_name = Column(String, nullable=True)
    preferred_date = Column(DateTime, nullable=True)
    time_window = Column(String, nullable=True)
    description = Column(Text, nullable=True)
    booking_state = Column(String, default="New")
    client_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    job_id = Column(Integer, ForeignKey("jobs.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    client = relationship("User", back_populates="bookings", foreign_keys=[client_id])


class Job(Base):
    __tablename__ = "jobs"

    id = Column(Integer, primary_key=True, index=True)
    booking_id = Column(Integer, ForeignKey("bookings.id"), nullable=False, unique=True)
    technician_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    scheduled_date = Column(DateTime, nullable=False)
    time_window = Column(String, nullable=False)
    status = Column(String, default="Scheduled")
    created_at = Column(DateTime, default=datetime.utcnow)

    assigned_technician = relationship("User", back_populates="assigned_jobs", foreign_keys=[technician_id])
    notes = relationship("JobNote", back_populates="job", cascade="all, delete-orphan")
    photos = relationship("JobPhoto", back_populates="job", cascade="all, delete-orphan")
    invoices = relationship("Invoice", back_populates="job")


class JobNote(Base):
    __tablename__ = "job_notes"

    id = Column(Integer, primary_key=True, index=True)
    job_id = Column(Integer, ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False)
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    job = relationship("Job", back_populates="notes")


class JobPhoto(Base):
    __tablename__ = "job_photos"

    id = Column(Integer, primary_key=True, index=True)
    job_id = Column(Integer, ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False)
    filename = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    job = relationship("Job", back_populates="photos")


class Invoice(Base):
    __tablename__ = "invoices"

    id = Column(Integer, primary_key=True, index=True)
    job_id = Column(Integer, ForeignKey("jobs.id"), nullable=False)
    creator_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    amount = Column(Integer, nullable=False)
    due_date = Column(DateTime, nullable=False)
    status = Column(String, default="Draft")
    created_at = Column(DateTime, default=datetime.utcnow)

    job = relationship("Job", back_populates="invoices")
    creator = relationship("User", back_populates="created_invoices", foreign_keys=[creator_id])
