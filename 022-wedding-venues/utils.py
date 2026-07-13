import pandas as pd
import os
from datetime import datetime, date, timedelta
from math import radians, sin, cos, sqrt, asin
from models import db, Venue, Availability, AvailabilityStatus, TourSlot, WeddingBooking, BookingStatus, VenueType
from flask import current_app

# Load postcode data
POSTCODE_DATA = None

def load_postcode_data():
    global POSTCODE_DATA
    if POSTCODE_DATA is None:
        csv_path = os.path.join(os.path.dirname(__file__), 'assets', 'postcode-outcodes.csv')
        if not os.path.exists(csv_path):
            csv_path = 'assets/postcode-outcodes.csv'
        POSTCODE_DATA = pd.read_csv(csv_path)
    return POSTCODE_DATA

def get_lat_long(postcode):
    """Get latitude and longitude for a postcode outcode"""
    if not postcode:
        return None, None

    postcode = postcode.strip().upper()
    data = load_postcode_data()

    # Try exact match
    match = data[data['postcode'] == postcode]
    if not match.empty:
        return float(match.iloc[0]['latitude']), float(match.iloc[0]['longitude'])

    # Try partial match (first part of postcode)
    # Extract the outcode (first part before space or just the string)
    outcode = postcode.split()[0] if ' ' in postcode else postcode
    match = data[data['postcode'] == outcode]
    if not match.empty:
        return float(match.iloc[0]['latitude']), float(match.iloc[0]['longitude'])

    return None, None

def haversine_distance(lat1, lon1, lat2, lon2):
    """Calculate the great circle distance between two points on the earth"""
    if lat1 is None or lon1 is None or lat2 is None or lon2 is None:
        return float('inf')

    # Convert decimal degrees to radians
    lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])

    # Haversine formula
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
    c = 2 * asin(sqrt(a))
    r = 3959  # Radius of Earth in miles
    return c * r

def is_date_available(venue_id, target_date):
    """Check if a date is available for a venue"""
    availability = Availability.query.filter_by(
        venue_id=venue_id,
        date=target_date
    ).first()

    if availability:
        return availability.status == AvailabilityStatus.AVAILABLE
    else:
        # If no availability record exists, it's available by default
        return True

def is_slot_available(tour_slot_id):
    """Check if a tour slot is available for booking"""
    slot = TourSlot.query.get(tour_slot_id)
    if not slot or slot.status == 'Full':
        return False

    # Check if booking is at least 24 hours in advance
    slot_datetime = datetime.combine(slot.date, slot.start_time)
    booking_window = slot_datetime - datetime.utcnow()
    if booking_window < timedelta(hours=24):
        return False

    return True

def check_venue_date_conflict(venue_id, target_date):
    """Check if there are any conflicts for a venue on a specific date"""
    # Check if date is blocked or booked
    availability = Availability.query.filter_by(
        venue_id=venue_id,
        date=target_date
    ).first()

    if availability and availability.status != AvailabilityStatus.AVAILABLE:
        return False

    return True

def validate_venue_for_search(venue, search_postcode, guest_count, search_date,
                           min_price=None, max_price=None, venue_type_filter=None):
    """Validate if a venue matches search criteria"""
    # Check if venue is active
    if venue.status.value != 'Active':
        return False

    # Check capacity
    if guest_count and (guest_count < venue.min_capacity or guest_count > venue.max_capacity):
        return False

    # Check price range if specified
    if guest_count and (min_price is not None or max_price is not None):
        price = venue.calculate_price(guest_count)
        if min_price is not None and price < min_price:
            return False
        if max_price is not None and price > max_price:
            return False

    # Check venue type matching
    if venue_type_filter:
        if (venue_type_filter == 'Indoor' and
            venue.venue_type not in [VenueType.INDOOR, VenueType.BOTH]):
            return False
        if (venue_type_filter == 'Outdoor' and
            venue.venue_type not in [VenueType.OUTDOOR, VenueType.BOTH]):
            return False

    # Check date availability
    if search_date and not is_date_available(venue.id, search_date):
        return False

    # Check distance (30-mile radius)
    search_lat, search_lon = get_lat_long(search_postcode)
    venue_lat, venue_lon = get_lat_long(venue.postcode)

    distance = haversine_distance(search_lat, search_lon, venue_lat, venue_lon)
    if distance > 30:
        return False

    return True

def get_venue_distance(venue, search_postcode):
    """Get distance between venue and search postcode"""
    search_lat, search_lon = get_lat_long(search_postcode)
    venue_lat, venue_lon = get_lat_long(venue.postcode)

    return haversine_distance(search_lat, search_lon, venue_lat, venue_lon)

def can_create_tour_slot(venue_id, date, start_time, duration):
    """Check if a tour slot can be created without conflicts"""
    from models import Availability, TourSlot, AvailabilityStatus

    # Check if date is blocked or booked
    availability = Availability.query.filter_by(
        venue_id=venue_id,
        date=date
    ).first()

    if availability and availability.status in [AvailabilityStatus.BLOCKED, AvailabilityStatus.BOOKED]:
        return False

    # Check for overlapping slots on the same date
    end_time = (datetime.combine(date, start_time) + timedelta(minutes=duration)).time()

    existing_slots = TourSlot.query.filter_by(
        venue_id=venue_id,
        date=date
    ).all()

    for slot in existing_slots:
        slot_start = slot.start_time
        slot_end = (datetime.combine(date, slot_start) + timedelta(minutes=slot.duration)).time()

        # Check for overlap
        if (start_time < slot_end and
            (datetime.combine(date, start_time) + timedelta(minutes=duration)).time() > slot_start):
            return False

    return True

def get_availability_calendar(venue_id, end_date=None):
    """Get 12-month availability calendar for a venue"""
    if end_date is None:
        end_date = date.today() + timedelta(days=365)

    start_date = date.today()

    calendar = []
    current_date = start_date

    while current_date <= end_date:
        availability = Availability.query.filter_by(
            venue_id=venue_id,
            date=current_date
        ).first()

        if availability:
            status = availability.status.value
        else:
            status = AvailabilityStatus.AVAILABLE.value

        calendar.append({
            'date': current_date.isoformat(),
            'status': status,
            'note': availability.note if availability else None
        })

        current_date += timedelta(days=1)

    return calendar
