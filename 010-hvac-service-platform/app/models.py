import uuid
from datetime import datetime, date
from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, Date, Enum, Float, Text, Boolean
from sqlalchemy.orm import relationship
from app.database import Base
import enum

class UserRole(enum.Enum):
    Client = "Client"
    Technician = "Technician"

class ServiceType(enum.Enum):
    HVAC = "HVAC"
    Plumbing = "Plumbing"

class BookingType(enum.Enum):
    Residential = "Residential"
    Commercial = "Commercial"

class Category(enum.Enum):
    Installation = "Installation"
    Repair = "Repair"
    Maintenance = "Maintenance"
    Emergency = "Emergency"

class Urgency(enum.Enum):
    Standard = "Standard"
    Urgent = "Urgent"
    Emergency = "Emergency"

class TimeWindow(enum.Enum):
    AM = "AM"
    PM = "PM"
    Any = "Any"

class EquipmentType(enum.Enum):
    Furnace = "Furnace"
    AC = "AC"
    HeatPump = "Heat Pump"
    Boiler = "Boiler"
    WaterHeater = "Water Heater"
    Thermostat = "Thermostat"
    Humidifier = "Humidifier"
    AirPurifier = "Air Purifier"
    WaterSoftener = "Water Softener"
    PlumbingFixture = "Plumbing Fixture"
    Other = "Other"

class JobStatus(enum.Enum):
    Scheduled = "Scheduled"
    InProgress = "In Progress"
    Completed = "Completed"

class InvoiceStatus(enum.Enum):
    Draft = "Draft"
    Sent = "Sent"
    Paid = "Paid"
    Void = "Void"
    Overdue = "Overdue"

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    role = Column(Enum(UserRole), nullable=False)
    
    properties = relationship("Property", back_populates="owner")
    bookings = relationship("Booking", back_populates="client")

class Property(Base):
    __tablename__ = "properties"
    id = Column(Integer, primary_key=True, index=True)
    label = Column(String, nullable=False)
    street = Column(String, nullable=False)
    city = Column(String, nullable=False)
    state = Column(String, nullable=False)
    zip_code = Column(String, nullable=False)
    owner_id = Column(Integer, ForeignKey("users.id"))
    
    owner = relationship("User", back_populates="properties")
    equipment = relationship("Equipment", back_populates="property", cascade="all, delete-orphan")
    bookings = relationship("Booking", back_populates="property")

class Equipment(Base):
    __tablename__ = "equipment"
    id = Column(Integer, primary_key=True, index=True)
    service_type = Column(Enum(ServiceType), nullable=False)
    equipment_type = Column(Enum(EquipmentType), nullable=False)
    manufacturer = Column(String)
    model = Column(String)
    serial = Column(String)
    install_date = Column(Date)
    notes = Column(Text)
    property_id = Column(Integer, ForeignKey("properties.id"))
    
    property = relationship("Property", back_populates="equipment")

class Booking(Base):
    __tablename__ = "bookings"
    id = Column(Integer, primary_key=True, index=True)
    service_type = Column(Enum(ServiceType), nullable=False)
    booking_type = Column(Enum(BookingType), nullable=False)
    category = Column(Enum(Category), nullable=False)
    urgency = Column(Enum(Urgency), nullable=False)
    name = Column(String, nullable=False)
    email = Column(String, nullable=False)
    phone = Column(String, nullable=False)
    street = Column(String, nullable=False)
    city = Column(String, nullable=False)
    state = Column(String, nullable=False)
    zip_code = Column(String, nullable=False)
    company_name = Column(String)
    preferred_date = Column(Date)
    time_window = Column(Enum(TimeWindow))
    description = Column(Text)
    tracking_token = Column(String, unique=True, default=lambda: str(uuid.uuid4()))
    status = Column(String, default="New") # New, Converted
    client_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    property_id = Column(Integer, ForeignKey("properties.id"), nullable=True)
    
    client = relationship("User", back_populates="bookings")
    property = relationship("Property", back_populates="bookings")
    job = relationship("Job", back_populates="booking", uselist=False)

class Job(Base):
    __tablename__ = "jobs"
    id = Column(Integer, primary_key=True, index=True)
    booking_id = Column(Integer, ForeignKey("bookings.id"), unique=True)
    scheduled_date = Column(Date, nullable=False)
    scheduled_time = Column(String, nullable=False)
    status = Column(Enum(JobStatus), default=JobStatus.Scheduled)
    technician_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    
    booking = relationship("Booking", back_populates="job")
    technician = relationship("User")
    notes = relationship("JobNote", back_populates="job")
    photos = relationship("JobPhoto", back_populates="job")
    invoices = relationship("Invoice", back_populates="job")

class JobNote(Base):
    __tablename__ = "job_notes"
    id = Column(Integer, primary_key=True, index=True)
    job_id = Column(Integer, ForeignKey("jobs.id"))
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    job = relationship("Job", back_populates="notes")

class JobPhoto(Base):
    __tablename__ = "job_photos"
    id = Column(Integer, primary_key=True, index=True)
    job_id = Column(Integer, ForeignKey("jobs.id"))
    url = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    job = relationship("Job", back_populates="photos")

class Invoice(Base):
    __tablename__ = "invoices"
    id = Column(Integer, primary_key=True, index=True)
    job_id = Column(Integer, ForeignKey("jobs.id"))
    amount = Column(Float, nullable=False)
    due_date = Column(Date, nullable=False)
    status = Column(Enum(InvoiceStatus), default=InvoiceStatus.Draft)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    job = relationship("Job", back_populates="invoices")
