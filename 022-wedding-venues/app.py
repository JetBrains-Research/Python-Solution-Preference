from flask import Flask, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash
from datetime import datetime, date, time, timedelta
from models import db, User, Venue, VenueImage, Availability, TourSlot, TourBooking, WeddingBooking, VenueType
from models import UserRole, VenueType, VenueStatus, AvailabilityStatus, TourType, BookingStatus
from utils import (
    get_lat_long, haversine_distance, is_date_available, is_slot_available,
    check_venue_date_conflict, validate_venue_for_search, get_venue_distance,
    can_create_tour_slot, get_availability_calendar, load_postcode_data
)
import os
import uuid

# Initialize Flask app
app = Flask(__name__)

# Configure database
basedir = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'wedding_venue.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY') or 'welcome123'

# Initialize database
db.init_app(app)

# Create tables
with app.app_context():
    db.create_all()

# Helper function to return JSON responses
def success_response(data, status_code=200):
    return jsonify({
        'success': True,
        'data': data
    }), status_code

def error_response(message, status_code=400):
    return jsonify({
        'success': False,
        'error': message
    }), status_code

# Authentication middleware
def authenticate_user(email, password):
    user = User.query.filter_by(email=email).first()
    if user and user.check_password(password):
        return user
    return None

# ==================== ACCOUNT ENDPOINTS ====================

@app.route('/api/auth/signup', methods=['POST'])
def signup():
    try:
        data = request.get_json()

        if not data or 'email' not in data or 'password' not in data or 'role' not in data:
            return error_response('Missing required fields', 400)

        email = data['email']
        password = data['password']
        role = data['role']

        # Check if user already exists
        if User.query.filter_by(email=email).first():
            return error_response('Email already exists', 400)

        # Validate role
        if role not in ['couple', 'manager']:
            return error_response('Invalid role', 400)

        user = User(email=email, role=UserRole(role))
        user.set_password(password)

        if role == 'couple':
            if 'partner-names' not in data:
                return error_response('Missing partner names for couple', 400)

            partner_names = data['partner-names']
            user.partner_name_1 = partner_names[0] if len(partner_names) > 0 else None
            user.partner_name_2 = partner_names[1] if len(partner_names) > 1 else None
            user.postcode = data.get('postcode', '')
            user.venue_type_preference = VenueType(data.get('venue-type-preference', 'Either'))
            if 'wedding-date' in data:
                user.wedding_date = date.fromisoformat(data['wedding-date'])

        elif role == 'manager':
            user.name = data.get('name', '')
            user.phone = data.get('phone', '')
            user.business_name = data.get('business-name', '')

        db.session.add(user)
        db.session.commit()

        return success_response(user.to_dict(), 201)

    except Exception as e:
        db.session.rollback()
        return error_response(str(e), 500)

@app.route('/api/auth/login', methods=['POST'])
def login():
    try:
        data = request.get_json()

        if not data or 'email' not in data or 'password' not in data:
            return error_response('Missing email or password', 400)

        user = authenticate_user(data['email'], data['password'])
        if not user:
            return error_response('Invalid email or password', 401)

        return success_response(user.to_dict())

    except Exception as e:
        return error_response(str(e), 500)

# ==================== VENUE ENDPOINTS (Manager only) ====================

@app.route('/api/venues', methods=['POST'])
def create_venue():
    try:
        data = request.get_json()

        # Authenticate manager
        if 'manager-email' not in data or 'manager-password' not in data:
            return error_response('Manager authentication required', 401)

        manager = authenticate_user(data['manager-email'], data['manager-password'])
        if not manager or manager.role != UserRole.MANAGER:
            return error_response('Only managers can create venues', 401)

        # Validate required fields
        required_fields = ['name', 'address', 'postcode', 'description', 'contact-info',
                          'min-capacity', 'max-capacity', 'base-fee', 'per-person-fee', 'venue-type']
        for field in required_fields:
            if field not in data:
                return error_response(f'Missing required field: {field}', 400)

        # Validate description length
        if len(data['description']) < 200:
            return error_response('Description must be at least 200 characters', 400)

        # Validate capacity
        if data['min-capacity'] >= data['max-capacity']:
            return error_response('Min capacity must be less than max capacity', 400)

        venue = Venue(
            manager_id=manager.id,
            name=data['name'],
            address=data['address'],
            postcode=data['postcode'],
            description=data['description'],
            contact_info=data['contact-info'],
            min_capacity=data['min-capacity'],
            max_capacity=data['max-capacity'],
            base_fee=data['base-fee'],
            per_person_fee=data['per-person-fee'],
            venue_type=VenueType(data['venue-type']),
            status=VenueStatus(data.get('status', 'Active'))
        )

        db.session.add(venue)
        db.session.commit()

        # Add images
        images = data.get('images', [])
        for img_data in images:
            image = VenueImage(
                venue_id=venue.id,
                image_url=img_data['image-url'],
                is_main=img_data.get('is-main', False)
            )
            db.session.add(image)

        db.session.commit()

        return success_response(venue.to_dict(), 201)

    except Exception as e:
        db.session.rollback()
        return error_response(str(e), 500)

@app.route('/api/venues/<venue_id>', methods=['GET'])
def get_venue(venue_id):
    try:
        venue = Venue.query.get(venue_id)
        if not venue:
            return error_response('Venue not found', 404)

        guest_count = request.args.get('guest-count', type=int)
        return success_response(venue.to_dict(guest_count=guest_count))

    except Exception as e:
        return error_response(str(e), 500)

@app.route('/api/venues/<venue_id>/availability', methods=['GET'])
def get_venue_availability(venue_id):
    try:
        venue = Venue.query.get(venue_id)
        if not venue:
            return error_response('Venue not found', 404)

        end_date_param = request.args.get('end-date')
        if end_date_param:
            try:
                end_date = date.fromisoformat(end_date_param)
            except ValueError:
                end_date = None
        else:
            end_date = None

        calendar = get_availability_calendar(venue_id, end_date)
        return success_response(calendar)

    except Exception as e:
        return error_response(str(e), 500)

@app.route('/api/managers/venues', methods=['GET'])
def get_manager_venues():
    try:
        manager_email = request.args.get('manager-email')
        manager_password = request.args.get('manager-password')

        if not manager_email or not manager_password:
            return error_response('Manager authentication required', 401)

        manager = authenticate_user(manager_email, manager_password)
        if not manager or manager.role != UserRole.MANAGER:
            return error_response('Only managers can access their venues', 401)

        venues = Venue.query.filter_by(manager_id=manager.id).all()
        venues_data = [venue.to_dict() for venue in venues]

        return success_response(venues_data)

    except Exception as e:
        return error_response(str(e), 500)

@app.route('/api/venues/<venue_id>', methods=['PUT'])
def update_venue(venue_id):
    try:
        data = request.get_json()

        # Authenticate manager
        if 'manager-email' not in data or 'manager-password' not in data:
            return error_response('Manager authentication required', 401)

        manager = authenticate_user(data['manager-email'], data['manager-password'])
        if not manager or manager.role != UserRole.MANAGER:
            return error_response('Only managers can update venues', 401)

        venue = Venue.query.get(venue_id)
        if not venue:
            return error_response('Venue not found', 404)

        if venue.manager_id != manager.id:
            return error_response('Can only update your own venues', 401)

        # Update fields
        if 'name' in data:
            venue.name = data['name']
        if 'address' in data:
            venue.address = data['address']
        if 'postcode' in data:
            venue.postcode = data['postcode']
        if 'description' in data:
            if len(data['description']) < 200:
                return error_response('Description must be at least 200 characters', 400)
            venue.description = data['description']
        if 'contact-info' in data:
            venue.contact_info = data['contact-info']
        if 'min-capacity' in data:
            venue.min_capacity = data['min-capacity']
        if 'max-capacity' in data:
            venue.max_capacity = data['max-capacity']
        if 'base-fee' in data:
            venue.base_fee = data['base-fee']
        if 'per-person-fee' in data:
            venue.per_person_fee = data['per-person-fee']
        if 'venue-type' in data:
            venue.venue_type = VenueType(data['venue-type'])
        if 'status' in data:
            venue.status = VenueStatus(data['status'])

        db.session.commit()
        return success_response(venue.to_dict())

    except Exception as e:
        db.session.rollback()
        return error_response(str(e), 500)

# ==================== AVAILABILITY ENDPOINTS (Manager only) ====================

@app.route('/api/venues/<venue_id>/availability', methods=['POST'])
def set_availability(venue_id):
    try:
        data = request.get_json()

        # Authenticate manager
        if 'manager-email' not in data or 'manager-password' not in data:
            return error_response('Manager authentication required', 401)

        manager = authenticate_user(data['manager-email'], data['manager-password'])
        if not manager or manager.role != UserRole.MANAGER:
            return error_response('Only managers can set availability', 401)

        venue = Venue.query.get(venue_id)
        if not venue:
            return error_response('Venue not found', 404)

        if venue.manager_id != manager.id:
            return error_response('Can only manage your own venues', 401)

        date_str = data.get('date')
        status = data.get('status')
        note = data.get('note')

        if not date_str or not status:
            return error_response('Date and status are required', 400)

        try:
            target_date = date.fromisoformat(date_str)
        except ValueError:
            return error_response('Invalid date format', 400)

        # Check if date is already booked (booked dates are immutable)
        existing_availability = Availability.query.filter_by(
            venue_id=venue_id,
            date=target_date
        ).first()

        if existing_availability and existing_availability.status == AvailabilityStatus.BOOKED:
            return error_response('Booked dates cannot be modified', 400)

        # Validate status
        try:
            status_enum = AvailabilityStatus(status)
        except ValueError:
            return error_response('Invalid status', 400)

        if existing_availability:
            existing_availability.status = status_enum
            existing_availability.note = note
        else:
            availability = Availability(
                venue_id=venue_id,
                date=target_date,
                status=status_enum,
                note=note
            )
            db.session.add(availability)

        db.session.commit()
        return success_response({'message': 'Availability updated successfully'})

    except Exception as e:
        db.session.rollback()
        return error_response(str(e), 500)

# ==================== TOUR SLOT ENDPOINTS ====================

@app.route('/api/venues/<venue_id>/tour-slots', methods=['POST'])
def create_tour_slot(venue_id):
    try:
        data = request.get_json()

        # Authenticate manager
        if 'manager-email' not in data or 'manager-password' not in data:
            return error_response('Manager authentication required', 401)

        manager = authenticate_user(data['manager-email'], data['manager-password'])
        if not manager or manager.role != UserRole.MANAGER:
            return error_response('Only managers can create tour slots', 401)

        venue = Venue.query.get(venue_id)
        if not venue:
            return error_response('Venue not found', 404)

        if venue.manager_id != manager.id:
            return error_response('Can only manage your own venues', 401)

        # Validate required fields
        required_fields = ['date', 'start-time', 'duration', 'capacity']
        for field in required_fields:
            if field not in data:
                return error_response(f'Missing required field: {field}', 400)

        try:
            slot_date = date.fromisoformat(data['date'])
            start_time = time.fromisoformat(data['start-time'])
        except ValueError:
            return error_response('Invalid date or time format', 400)

        duration = data['duration']
        capacity = data['capacity']

        # Check if slot can be created
        if not can_create_tour_slot(venue_id, slot_date, start_time, duration):
            return error_response('Cannot create slot - conflict with existing slots or date unavailable', 400)

        slot = TourSlot(
            venue_id=venue_id,
            date=slot_date,
            start_time=start_time,
            duration=duration,
            capacity=capacity,
            status='Available'
        )

        db.session.add(slot)
        db.session.commit()

        return success_response(slot.to_dict(), 201)

    except Exception as e:
        db.session.rollback()
        return error_response(str(e), 500)

@app.route('/api/tour-slots/<slot_id>/book', methods=['POST'])
def book_tour_slot(slot_id):
    try:
        data = request.get_json()

        # Authenticate couple
        if 'email' not in data or 'password' not in data:
            return error_response('Authentication required', 401)

        user = authenticate_user(data['email'], data['password'])
        if not user or user.role != UserRole.COUPLE:
            return error_response('Only couples can book tour slots', 401)

        # Validate required fields
        required_fields = ['tour-type', 'attendee-count']
        for field in required_fields:
            if field not in data:
                return error_response(f'Missing required field: {field}', 400)

        slot = TourSlot.query.get(slot_id)
        if not slot:
            return error_response('Tour slot not found', 404)

        # Check if slot is available
        if not is_slot_available(slot_id):
            return error_response('Tour slot is not available for booking', 400)

        tour_type = TourType(data['tour-type'])
        attendee_count = data['attendee-count']
        notes = data.get('notes', '')

        booking = TourBooking(
            user_id=user.id,
            tour_slot_id=slot_id,
            tour_type=tour_type,
            attendee_count=attendee_count,
            notes=notes,
            status=BookingStatus.PENDING
        )

        db.session.add(booking)
        db.session.commit()

        return success_response(booking.to_dict(), 201)

    except Exception as e:
        db.session.rollback()
        return error_response(str(e), 500)

@app.route('/api/managers/tour-bookings/<booking_id>/approve', methods=['POST'])
def approve_tour_booking(booking_id):
    try:
        data = request.get_json()

        # Authenticate manager
        if 'manager-email' not in data or 'manager-password' not in data:
            return error_response('Manager authentication required', 401)

        manager = authenticate_user(data['manager-email'], data['manager-password'])
        if not manager or manager.role != UserRole.MANAGER:
            return error_response('Only managers can approve tour bookings', 401)

        booking = TourBooking.query.get(booking_id)
        if not booking:
            return error_response('Tour booking not found', 404)

        slot = TourSlot.query.get(booking.tour_slot_id)
        if not slot:
            return error_response('Tour slot not found', 404)

        venue = Venue.query.get(slot.venue_id)
        if not venue:
            return error_response('Venue not found', 404)

        if venue.manager_id != manager.id:
            return error_response('Can only manage your own venues', 401)

        if booking.status != BookingStatus.PENDING:
            return error_response('Only pending bookings can be approved', 400)

        if slot.status == 'Full':
            return error_response('Slot is full, cannot approve', 400)

        # Check if slot is still available for booking
        if not is_slot_available(slot.id):
            return error_response('Slot is no longer available for booking', 400)

        # Decrement slot capacity
        slot.capacity -= 1
        if slot.capacity <= 0:
            slot.capacity = 0
            slot.status = 'Full'

        booking.status = BookingStatus.APPROVED
        booking.manager_response_at = datetime.utcnow()
        booking.manager_note = data.get('note', '')

        db.session.commit()
        return success_response(booking.to_dict())

    except Exception as e:
        db.session.rollback()
        return error_response(str(e), 500)

@app.route('/api/managers/tour-bookings/<booking_id>/deny', methods=['POST'])
def deny_tour_booking(booking_id):
    try:
        data = request.get_json()

        # Authenticate manager
        if 'manager-email' not in data or 'manager-password' not in data:
            return error_response('Manager authentication required', 401)

        manager = authenticate_user(data['manager-email'], data['manager-password'])
        if not manager or manager.role != UserRole.MANAGER:
            return error_response('Only managers can deny tour bookings', 401)

        booking = TourBooking.query.get(booking_id)
        if not booking:
            return error_response('Tour booking not found', 404)

        slot = TourSlot.query.get(booking.tour_slot_id)
        if not slot:
            return error_response('Tour slot not found', 404)

        venue = Venue.query.get(slot.venue_id)
        if not venue:
            return error_response('Venue not found', 404)

        if venue.manager_id != manager.id:
            return error_response('Can only manage your own venues', 401)

        if booking.status != BookingStatus.PENDING:
            return error_response('Only pending bookings can be denied', 400)

        booking.status = BookingStatus.DENIED
        booking.manager_response_at = datetime.utcnow()
        booking.manager_note = data.get('note', '')

        db.session.commit()
        return success_response(booking.to_dict())

    except Exception as e:
        db.session.rollback()
        return error_response(str(e), 500)

# ==================== WEDDING BOOKING ENDPOINTS ====================

@app.route('/api/wedding-bookings', methods=['POST'])
def request_wedding_booking():
    try:
        data = request.get_json()

        # Authenticate couple
        if 'email' not in data or 'password' not in data:
            return error_response('Authentication required', 401)

        user = authenticate_user(data['email'], data['password'])
        if not user or user.role != UserRole.COUPLE:
            return error_response('Only couples can request wedding bookings', 401)

        # Validate required fields
        required_fields = ['venue-id', 'date', 'guest-count']
        for field in required_fields:
            if field not in data:
                return error_response(f'Missing required field: {field}', 400)

        venue_id = data['venue-id']
        try:
            booking_date = date.fromisoformat(data['date'])
        except ValueError:
            return error_response('Invalid date format', 400)

        guest_count = data['guest-count']
        notes = data.get('notes', '')

        venue = Venue.query.get(venue_id)
        if not venue:
            return error_response('Venue not found', 404)

        # Check if date is available
        if not is_date_available(venue_id, booking_date):
            return error_response('Date is not available for booking', 400)

        # Check capacity
        if guest_count < venue.min_capacity or guest_count > venue.max_capacity:
            return error_response('Guest count is outside venue capacity', 400)

        # Check for existing bookings for the same venue/date by this couple
        existing_booking = WeddingBooking.query.filter_by(
            couple_id=user.id,
            venue_id=venue_id,
            date=booking_date
        ).first()

        if existing_booking and existing_booking.status in [BookingStatus.PENDING, BookingStatus.CONFIRMED]:
            return error_response('Cannot have multiple pending or confirmed bookings for the same venue/date', 400)

        # Calculate estimated price
        estimated_price = venue.calculate_price(guest_count)

        booking = WeddingBooking(
            couple_id=user.id,
            venue_id=venue_id,
            date=booking_date,
            guest_count=guest_count,
            notes=notes,
            status=BookingStatus.PENDING,
            estimated_price=estimated_price
        )

        db.session.add(booking)
        db.session.commit()

        return success_response(booking.to_dict(), 201)

    except Exception as e:
        db.session.rollback()
        return error_response(str(e), 500)

@app.route('/api/managers/wedding-bookings/<booking_id>/confirm', methods=['POST'])
def confirm_wedding_booking(booking_id):
    try:
        data = request.get_json()

        # Authenticate manager
        if 'manager-email' not in data or 'manager-password' not in data:
            return error_response('Manager authentication required', 401)

        manager = authenticate_user(data['manager-email'], data['manager-password'])
        if not manager or manager.role != UserRole.MANAGER:
            return error_response('Only managers can confirm wedding bookings', 401)

        booking = WeddingBooking.query.get(booking_id)
        if not booking:
            return error_response('Wedding booking not found', 404)

        venue = Venue.query.get(booking.venue_id)
        if not venue:
            return error_response('Venue not found', 404)

        if venue.manager_id != manager.id:
            return error_response('Can only manage your own venues', 401)

        if booking.status != BookingStatus.PENDING:
            return error_response('Only pending bookings can be confirmed', 400)

        # Set date as Booked in availability
        availability = Availability.query.filter_by(
            venue_id=booking.venue_id,
            date=booking.date
        ).first()

        if availability:
            availability.status = AvailabilityStatus.BOOKED
        else:
            availability = Availability(
                venue_id=booking.venue_id,
                date=booking.date,
                status=AvailabilityStatus.BOOKED
            )
            db.session.add(availability)

        booking.status = BookingStatus.CONFIRMED
        booking.manager_response_at = datetime.utcnow()
        booking.manager_note = data.get('note', '')

        db.session.commit()
        return success_response(booking.to_dict())

    except Exception as e:
        db.session.rollback()
        return error_response(str(e), 500)

@app.route('/api/managers/wedding-bookings/<booking_id>/decline', methods=['POST'])
def decline_wedding_booking(booking_id):
    try:
        data = request.get_json()

        # Authenticate manager
        if 'manager-email' not in data or 'manager-password' not in data:
            return error_response('Manager authentication required', 401)

        manager = authenticate_user(data['manager-email'], data['manager-password'])
        if not manager or manager.role != UserRole.MANAGER:
            return error_response('Only managers can decline wedding bookings', 401)

        booking = WeddingBooking.query.get(booking_id)
        if not booking:
            return error_response('Wedding booking not found', 404)

        venue = Venue.query.get(booking.venue_id)
        if not venue:
            return error_response('Venue not found', 404)

        if venue.manager_id != manager.id:
            return error_response('Can only manage your own venues', 401)

        if booking.status != BookingStatus.PENDING:
            return error_response('Only pending bookings can be declined', 400)

        booking.status = BookingStatus.DECLINED
        booking.manager_response_at = datetime.utcnow()
        booking.manager_note = data.get('note', '')

        db.session.commit()
        return success_response(booking.to_dict())

    except Exception as e:
        db.session.rollback()
        return error_response(str(e), 500)

@app.route('/api/managers/wedding-bookings', methods=['GET'])
def get_venue_wedding_bookings():
    try:
        manager_email = request.args.get('manager-email')
        manager_password = request.args.get('manager-password')
        venue_id = request.args.get('venue-id')

        if not manager_email or not manager_password:
            return error_response('Manager authentication required', 401)

        manager = authenticate_user(manager_email, manager_password)
        if not manager or manager.role != UserRole.MANAGER:
            return error_response('Only managers can access wedding bookings', 401)

        if venue_id:
            venue = Venue.query.get(venue_id)
            if not venue:
                return error_response('Venue not found', 404)
            if venue.manager_id != manager.id:
                return error_response('Can only access your own venues bookings', 401)

            bookings = WeddingBooking.query.filter_by(venue_id=venue_id).all()
        else:
            # Get all bookings for all venues managed by this manager
            venue_ids = [v.id for v in Venue.query.filter_by(manager_id=manager.id).all()]
            bookings = WeddingBooking.query.filter(WeddingBooking.venue_id.in_(venue_ids)).all()

        bookings_data = []
        for booking in bookings:
            booking_data = booking.to_dict()
            # Add couple info
            couple = User.query.get(booking.couple_id)
            if couple:
                booking_data['couple-info'] = {
                    'email': couple.email,
                    'partner-names': [couple.partner_name_1, couple.partner_name_2],
                    'postcode': couple.postcode,
                    'wedding-date': couple.wedding_date.isoformat() if couple.wedding_date else None,
                    'venue-type-preference': couple.venue_type_preference.value if couple.venue_type_preference else None
                }
            bookings_data.append(booking_data)

        return success_response(bookings_data)

    except Exception as e:
        return error_response(str(e), 500)

@app.route('/api/managers/tour-bookings', methods=['GET'])
def get_venue_tour_bookings():
    try:
        manager_email = request.args.get('manager-email')
        manager_password = request.args.get('manager-password')
        venue_id = request.args.get('venue-id')

        if not manager_email or not manager_password:
            return error_response('Manager authentication required', 401)

        manager = authenticate_user(manager_email, manager_password)
        if not manager or manager.role != UserRole.MANAGER:
            return error_response('Only managers can access tour bookings', 401)

        if venue_id:
            venue = Venue.query.get(venue_id)
            if not venue:
                return error_response('Venue not found', 404)
            if venue.manager_id != manager.id:
                return error_response('Can only access your own venues bookings', 401)

            # Get all tour slots for this venue
            slots = TourSlot.query.filter_by(venue_id=venue_id).all()
            slot_ids = [slot.id for slot in slots]

            bookings = TourBooking.query.filter(TourBooking.tour_slot_id.in_(slot_ids)).all()
        else:
            # Get all venues managed by this manager
            venue_ids = [v.id for v in Venue.query.filter_by(manager_id=manager.id).all()]
            slots = TourSlot.query.filter(TourSlot.venue_id.in_(venue_ids)).all()
            slot_ids = [slot.id for slot in slots]

            bookings = TourBooking.query.filter(TourBooking.tour_slot_id.in_(slot_ids)).all()

        bookings_data = []
        for booking in bookings:
            booking_data = booking.to_dict()
            # Add user info
            user = User.query.get(booking.user_id)
            if user:
                booking_data['user-info'] = {
                    'email': user.email,
                    'name': user.name if user.role == UserRole.MANAGER else f'{user.partner_name_1} & {user.partner_name_2}'
                }
            bookings_data.append(booking_data)

        return success_response(bookings_data)

    except Exception as e:
        return error_response(str(e), 500)

# ==================== SEARCH ENDPOINTS ====================

@app.route('/api/search/venues', methods=['GET'])
def search_venues():
    try:
        # Get search parameters
        postcode = request.args.get('postcode')
        search_date = request.args.get('date')
        guest_count = request.args.get('guest-count', type=int)
        min_price = request.args.get('min-price', type=float)
        max_price = request.args.get('max-price', type=float)
        venue_type = request.args.get('venue-type')
        sort_by = request.args.get('sort-by', 'distance')  # distance or price

        if not postcode:
            return error_response('Postcode is required', 400)

        if search_date:
            try:
                search_date_obj = date.fromisoformat(search_date)
            except ValueError:
                return error_response('Invalid date format', 400)
        else:
            search_date_obj = None

        # Get all active venues
        venues = Venue.query.filter_by(status=VenueStatus.ACTIVE).all()

        # Filter venues
        valid_venues = []
        for venue in venues:
            if validate_venue_for_search(
                venue, postcode, guest_count, search_date_obj,
                min_price, max_price, venue_type
            ):
                valid_venues.append(venue)

        # Sort results
        if sort_by == 'distance':
            valid_venues.sort(key=lambda v: get_venue_distance(v, postcode))
        elif sort_by == 'price' and guest_count:
            valid_venues.sort(key=lambda v: v.calculate_price(guest_count))

        # Prepare response
        results = []
        for venue in valid_venues:
            venue_data = venue.to_dict()
            if guest_count:
                venue_data['estimated-price'] = venue.calculate_price(guest_count)
                venue_data['distance'] = get_venue_distance(venue, postcode)
            results.append(venue_data)

        return success_response(results)

    except Exception as e:
        return error_response(str(e), 500)

# ==================== USER PROFILE ENDPOINTS ====================

@app.route('/api/users/<user_id>', methods=['GET'])
def get_user(user_id):
    try:
        user = User.query.get(user_id)
        if not user:
            return error_response('User not found', 404)

        return success_response(user.to_dict())

    except Exception as e:
        return error_response(str(e), 500)

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
