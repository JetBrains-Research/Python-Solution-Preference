from datetime import datetime, date, time
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from enum import Enum
import uuid

db = SQLAlchemy()

# Enums for various fields
class UserRole(Enum):
    COUPLE = 'couple'
    MANAGER = 'manager'

class VenueType(Enum):
    INDOOR = 'Indoor'
    OUTDOOR = 'Outdoor'
    BOTH = 'Both'

class VenueStatus(Enum):
    ACTIVE = 'Active'
    INACTIVE = 'Inactive'

class AvailabilityStatus(Enum):
    AVAILABLE = 'Available'
    BLOCKED = 'Blocked'
    BOOKED = 'Booked'

class TourType(Enum):
    IN_PERSON = 'In-Person'
    VIRTUAL = 'Virtual'

class BookingStatus(Enum):
    PENDING = 'Pending'
    APPROVED = 'Approved'
    DENIED = 'Denied'
    CONFIRMED = 'Confirmed'
    DECLINED = 'Declined'

class User(db.Model):
    __tablename__ = 'users'

    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)
    role = db.Column(db.Enum(UserRole), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Couple-specific fields
    partner_name_1 = db.Column(db.String(100))
    partner_name_2 = db.Column(db.String(100))
    postcode = db.Column(db.String(20))
    wedding_date = db.Column(db.Date)
    venue_type_preference = db.Column(db.Enum(VenueType))

    # Manager-specific fields
    name = db.Column(db.String(100))
    phone = db.Column(db.String(20))
    business_name = db.Column(db.String(100))

    # Relationships
    venues = db.relationship('Venue', backref='manager', lazy=True)
    tour_bookings = db.relationship('TourBooking', backref='user', lazy=True)
    wedding_bookings = db.relationship('WeddingBooking', backref='couple', lazy=True)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def to_dict(self):
        data = {
            'id': self.id,
            'email': self.email,
            'role': self.role.value,
            'created_at': self.created_at.isoformat(),
            'updated_at': self.updated_at.isoformat()
        }

        if self.role == UserRole.COUPLE:
            data.update({
                'partner-name-1': self.partner_name_1,
                'partner-name-2': self.partner_name_2,
                'postcode': self.postcode,
                'wedding-date': self.wedding_date.isoformat() if self.wedding_date else None,
                'venue-type-preference': self.venue_type_preference.value if self.venue_type_preference else None
            })
        else:
            data.update({
                'name': self.name,
                'phone': self.phone,
                'business-name': self.business_name
            })

        return data

class Venue(db.Model):
    __tablename__ = 'venues'

    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    manager_id = db.Column(db.String(36), db.ForeignKey('users.id'), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    address = db.Column(db.String(200), nullable=False)
    postcode = db.Column(db.String(20), nullable=False)
    description = db.Column(db.String(1000), nullable=False)
    contact_info = db.Column(db.String(200), nullable=False)
    min_capacity = db.Column(db.Integer, nullable=False)
    max_capacity = db.Column(db.Integer, nullable=False)
    base_fee = db.Column(db.Float, nullable=False)
    per_person_fee = db.Column(db.Float, nullable=False)
    venue_type = db.Column(db.Enum(VenueType), nullable=False)
    status = db.Column(db.Enum(VenueStatus), default=VenueStatus.ACTIVE, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    images = db.relationship('VenueImage', backref='venue', lazy=True, cascade='all, delete-orphan')
    availability = db.relationship('Availability', backref='venue', lazy=True, cascade='all, delete-orphan')
    tour_slots = db.relationship('TourSlot', backref='venue', lazy=True, cascade='all, delete-orphan')
    wedding_bookings = db.relationship('WeddingBooking', backref='venue', lazy=True)

    def calculate_price(self, guest_count):
        return self.base_fee + (self.per_person_fee * guest_count)

    def to_dict(self, guest_count=None):
        data = {
            'id': self.id,
            'manager-id': self.manager_id,
            'name': self.name,
            'address': self.address,
            'postcode': self.postcode,
            'description': self.description,
            'contact-info': self.contact_info,
            'min-capacity': self.min_capacity,
            'max-capacity': self.max_capacity,
            'base-fee': self.base_fee,
            'per-person-fee': self.per_person_fee,
            'venue-type': self.venue_type.value,
            'status': self.status.value,
            'created-at': self.created_at.isoformat(),
            'updated-at': self.updated_at.isoformat(),
            'images': [img.to_dict() for img in self.images]
        }

        if guest_count is not None:
            data['estimated-price'] = self.calculate_price(guest_count)

        return data

class VenueImage(db.Model):
    __tablename__ = 'venue_images'

    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    venue_id = db.Column(db.String(36), db.ForeignKey('venues.id'), nullable=False)
    image_url = db.Column(db.String(255), nullable=False)
    is_main = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'image-url': self.image_url,
            'is-main': self.is_main,
            'created-at': self.created_at.isoformat()
        }

class Availability(db.Model):
    __tablename__ = 'availability'

    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    venue_id = db.Column(db.String(36), db.ForeignKey('venues.id'), nullable=False)
    date = db.Column(db.Date, nullable=False)
    status = db.Column(db.Enum(AvailabilityStatus), default=AvailabilityStatus.AVAILABLE, nullable=False)
    note = db.Column(db.String(200))

    __table_args__ = (
        db.UniqueConstraint('venue_id', 'date', name='unique_venue_date'),
    )

    def to_dict(self):
        return {
            'date': self.date.isoformat(),
            'status': self.status.value,
            'note': self.note
        }

class TourSlot(db.Model):
    __tablename__ = 'tour_slots'

    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    venue_id = db.Column(db.String(36), db.ForeignKey('venues.id'), nullable=False)
    date = db.Column(db.Date, nullable=False)
    start_time = db.Column(db.Time, nullable=False)
    duration = db.Column(db.Integer, nullable=False)  # in minutes
    capacity = db.Column(db.Integer, nullable=False)
    status = db.Column(db.String(20), default='Available')  # Available, Full

    def to_dict(self):
        return {
            'id': self.id,
            'venue-id': self.venue_id,
            'date': self.date.isoformat(),
            'start-time': self.start_time.isoformat(),
            'duration': self.duration,
            'capacity': self.capacity,
            'status': self.status
        }

class TourBooking(db.Model):
    __tablename__ = 'tour_bookings'

    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = db.Column(db.String(36), db.ForeignKey('users.id'), nullable=False)
    tour_slot_id = db.Column(db.String(36), db.ForeignKey('tour_slots.id'), nullable=False)
    tour_type = db.Column(db.Enum(TourType), nullable=False)
    attendee_count = db.Column(db.Integer, nullable=False)
    notes = db.Column(db.String(300))
    status = db.Column(db.Enum(BookingStatus), default=BookingStatus.PENDING, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    manager_response_at = db.Column(db.DateTime)
    manager_note = db.Column(db.String(200))

    def to_dict(self):
        return {
            'id': self.id,
            'user-id': self.user_id,
            'tour-slot-id': self.tour_slot_id,
            'tour-type': self.tour_type.value,
            'attendee-count': self.attendee_count,
            'notes': self.notes,
            'status': self.status.value,
            'created-at': self.created_at.isoformat(),
            'updated-at': self.updated_at.isoformat(),
            'manager-response-at': self.manager_response_at.isoformat() if self.manager_response_at else None,
            'manager-note': self.manager_note
        }

class WeddingBooking(db.Model):
    __tablename__ = 'wedding_bookings'

    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    couple_id = db.Column(db.String(36), db.ForeignKey('users.id'), nullable=False)
    venue_id = db.Column(db.String(36), db.ForeignKey('venues.id'), nullable=False)
    date = db.Column(db.Date, nullable=False)
    guest_count = db.Column(db.Integer, nullable=False)
    notes = db.Column(db.String(300))
    status = db.Column(db.Enum(BookingStatus), default=BookingStatus.PENDING, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    manager_response_at = db.Column(db.DateTime)
    manager_note = db.Column(db.String(200))
    estimated_price = db.Column(db.Float)

    __table_args__ = (
        db.UniqueConstraint('couple_id', 'venue_id', 'date', name='unique_couple_venue_date'),
    )

    def to_dict(self):
        return {
            'id': self.id,
            'couple-id': self.couple_id,
            'venue-id': self.venue_id,
            'date': self.date.isoformat(),
            'guest-count': self.guest_count,
            'notes': self.notes,
            'status': self.status.value,
            'created-at': self.created_at.isoformat(),
            'updated-at': self.updated_at.isoformat(),
            'manager-response-at': self.manager_response_at.isoformat() if self.manager_response_at else None,
            'manager-note': self.manager_note,
            'estimated-price': self.estimated_price
        }
