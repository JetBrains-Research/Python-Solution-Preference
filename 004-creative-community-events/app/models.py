from sqlalchemy import Column, Integer, String, DateTime, Float, Boolean, ForeignKey, Enum
from sqlalchemy.orm import relationship
from app.database import Base
import enum

class RoleEnum(enum.Enum):
    PHOTOGRAPHER = "Photographer"
    FILMMAKER = "Filmmaker"
    DESIGNER = "Designer"
    WRITER = "Writer"
    VISUAL_ARTIST = "Visual Artist"
    OTHER = "Other"

class EventCategoryEnum(enum.Enum):
    WORKSHOP = "workshop"
    NETWORKING = "networking"
    EXHIBITION = "exhibition"
    SCREENING = "screening"
    SOCIAL = "social"

class PaymentStatusEnum(enum.Enum):
    UNPAID = "unpaid"
    PROCESSING = "processing"
    PAID = "paid"

class InviteCodeType(enum.Enum):
    SINGLE = "single"
    MULTI = "multi"

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True, nullable=False)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    is_admin = Column(Boolean, default=False)
    
    # Profile
    full_name = Column(String, nullable=True)
    phone = Column(String, nullable=True)
    location = Column(String, nullable=True)
    creative_role = Column(String, nullable=True) # Using String to match the specific list in schemas
    bio = Column(String, nullable=True)
    
    attendances = relationship("Attendance", back_populates="user")

class InviteCode(Base):
    __tablename__ = "invite_codes"
    id = Column(Integer, primary_key=True, index=True)
    code = Column(String, unique=True, index=True, nullable=False)
    code_type = Column(String, nullable=False) # single or multi
    max_uses = Column(Integer, default=1)
    uses = Column(Integer, default=0)
    expiration_date = Column(DateTime, nullable=False)
    is_active = Column(Boolean, default=True)
    description = Column(String, nullable=True)

class Event(Base):
    __tablename__ = "events"
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, nullable=False)
    description = Column(String, nullable=False)
    date_time = Column(DateTime, nullable=False)
    location = Column(String, nullable=False)
    category = Column(String, nullable=False)
    capacity = Column(Integer, nullable=False)
    price = Column(Float, default=0.0)
    
    attendances = relationship("Attendance", back_populates="event", cascade="all, delete-orphan")

class Attendance(Base):
    __tablename__ = "attendances"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    event_id = Column(Integer, ForeignKey("events.id"))
    attended = Column(Boolean, default=False)
    amount_owed = Column(Float, default=0.0)
    payment_status = Column(String, default="unpaid")
    payment_date = Column(DateTime, nullable=True)
    admin_notes = Column(String, nullable=True)
    
    user = relationship("User", back_populates="attendances")
    event = relationship("Event", back_populates="attendances")
