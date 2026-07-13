from datetime import datetime, timedelta, date
from typing import List, Dict, Optional, Tuple
import csv
import math
import os
from passlib.context import CryptContext
from sqlalchemy.orm import Session

# Load postcode data
POSTCODE_DATA: Dict[str, Tuple[float, float]] = {}

def load_postcode_data():
    """Load postcode to lat/long mapping from CSV file."""
    global POSTCODE_DATA
    
    # Try multiple paths
    possible_paths = [
        "assets/postcode-outcodes.csv",
        "../assets/postcode-outcodes.csv",
        "/Users/ilia_all/Projects/routing-preference/data/workspaces/022-wedding-venues_583fc1a2/assets/postcode-outcodes.csv"
    ]
    
    for filepath in possible_paths:
        try:
            with open(filepath, 'r') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    postcode = row['postcode']
                    lat = float(row['latitude'])
                    lon = float(row['longitude'])
                    POSTCODE_DATA[postcode] = (lat, lon)
            print(f"Loaded postcode data from {filepath}")
            return
        except FileNotFoundError:
            continue
    
    print("Warning: Could not load postcode data")

# Initialize postcode data
load_postcode_data()

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def hash_password(password: str) -> str:
    return pwd_context.hash(password)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)

# Distance calculation using Haversine formula
def calculate_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate distance between two points in miles."""
    R = 3958.8  # Earth's radius in miles
    
    lat1_rad = math.radians(lat1)
    lat2_rad = math.radians(lat2)
    delta_lat = math.radians(lat2 - lat1)
    delta_lon = math.radians(lon2 - lon1)
    
    a = math.sin(delta_lat / 2) ** 2 + \
        math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(delta_lon / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    
    return R * c

def get_postcode_coordinates(postcode: str) -> Optional[Tuple[float, float]]:
    """Get lat/long for a postcode."""
    return POSTCODE_DATA.get(postcode)

def get_venue_coordinates(postcode: str) -> Optional[Tuple[float, float]]:
    """Get lat/long for a venue's postcode."""
    return POSTCODE_DATA.get(postcode)

def is_within_radius(search_postcode: str, venue_postcode: str, max_miles: float = 30.0) -> bool:
    """Check if venue is within max_miles of search postcode."""
    search_coords = get_postcode_coordinates(search_postcode)
    venue_coords = get_venue_coordinates(venue_postcode)
    
    if not search_coords or not venue_coords:
        return False
    
    distance = calculate_distance(
        search_coords[0], search_coords[1],
        venue_coords[0], venue_coords[1]
    )
    
    return distance <= max_miles

def calculate_venue_distance(search_postcode: str, venue_postcode: str) -> Optional[float]:
    """Calculate distance in miles between search postcode and venue."""
    search_coords = get_postcode_coordinates(search_postcode)
    venue_coords = get_venue_coordinates(venue_postcode)
    
    if not search_coords or not venue_coords:
        return None
    
    return calculate_distance(
        search_coords[0], search_coords[1],
        venue_coords[0], venue_coords[1]
    )

def calculate_price(base_fee: float, per_person_fee: float, guest_count: int) -> float:
    """Calculate total price for a wedding."""
    return base_fee + (per_person_fee * guest_count)

def is_date_available(db: Session, venue_id: int, booking_date: date) -> bool:
    """Check if a date is available (not blocked or booked) for a venue."""
    from models import BlockedDate, WeddingBooking
    
    # Check if blocked
    blocked = db.query(BlockedDate).filter(
        BlockedDate.venue_id == venue_id,
        BlockedDate.blocked_date == booking_date
    ).first()
    if blocked:
        return False
    
    # Check if already booked (Confirmed status)
    existing = db.query(WeddingBooking).filter(
        WeddingBooking.venue_id == venue_id,
        WeddingBooking.booking_date == booking_date,
        WeddingBooking.status == "Confirmed"
    ).first()
    if existing:
        return False
    
    return True

def get_date_status(db: Session, venue_id: int, booking_date: date) -> str:
    """Get the status of a date for a venue."""
    from models import BlockedDate, WeddingBooking
    
    # Check if blocked
    blocked = db.query(BlockedDate).filter(
        BlockedDate.venue_id == venue_id,
        BlockedDate.blocked_date == booking_date
    ).first()
    if blocked:
        return "Blocked"
    
    # Check if booked
    existing = db.query(WeddingBooking).filter(
        WeddingBooking.venue_id == venue_id,
        WeddingBooking.booking_date == booking_date,
        WeddingBooking.status == "Confirmed"
    ).first()
    if existing:
        return "Booked"
    
    return "Available"

def generate_availability_calendar(db: Session, venue_id: int, start_date: date, end_date: date) -> List[Dict]:
    """Generate availability calendar for 12 months."""
    from models import BlockedDate, WeddingBooking
    
    calendar = []
    current_date = start_date
    
    while current_date <= end_date:
        status = get_date_status(db, venue_id, current_date)
        
        # Get note if blocked
        note = None
        if status == "Blocked":
            blocked = db.query(BlockedDate).filter(
                BlockedDate.venue_id == venue_id,
                BlockedDate.blocked_date == current_date
            ).first()
            if blocked:
                note = blocked.note
        
        calendar.append({
            "date": current_date.isoformat(),
            "status": status,
            "note": note
        })
        
        current_date += timedelta(days=1)
    
    return calendar

def is_24_hours_in_advance(slot_date: date, slot_time: str) -> bool:
    """Check if slot is at least 24 hours in advance."""
    slot_datetime = datetime.combine(slot_date, datetime.strptime(slot_time, "%H:%M").time())
    return slot_datetime > datetime.utcnow() + timedelta(hours=24)

def check_slot_overlap(db: Session, venue_id: int, slot_date: date, slot_time: str, duration_minutes: int, exclude_id: Optional[int] = None) -> bool:
    """Check if a new slot overlaps with existing slots."""
    from models import TourSlot
    
    # Parse slot time
    slot_start = datetime.strptime(slot_time, "%H:%M")
    slot_end = slot_start + timedelta(minutes=duration_minutes)
    
    existing_slots = db.query(TourSlot).filter(
        TourSlot.venue_id == venue_id,
        TourSlot.slot_date == slot_date
    ).all()
    
    if exclude_id:
        existing_slots = [s for s in existing_slots if s.id != exclude_id]
    
    for slot in existing_slots:
        existing_start = datetime.strptime(slot.slot_time, "%H:%M")
        existing_end = existing_start + timedelta(minutes=slot.duration_minutes)
        
        # Check for overlap
        if not (slot_end <= existing_start or slot_start >= existing_end):
            return True
    
    return False

def venue_type_matches_filter(venue_type: str, filter_type: Optional[str]) -> bool:
    """Check if venue type matches the filter."""
    if not filter_type:
        return True
    
    filter_upper = filter_type.capitalize()
    
    if filter_upper == "Indoor":
        return venue_type in ["Indoor", "Both"]
    elif filter_upper == "Outdoor":
        return venue_type in ["Outdoor", "Both"]
    elif filter_upper == "Both":
        return venue_type == "Both"
    elif filter_upper == "Either":
        return True
    
    return True

def get_pending_or_confirmed_booking(db: Session, venue_id: int, booking_date: date) -> Optional:
    """Check if there's a pending or confirmed booking for venue/date."""
    from models import WeddingBooking
    
    return db.query(WeddingBooking).filter(
        WeddingBooking.venue_id == venue_id,
        WeddingBooking.booking_date == booking_date,
        WeddingBooking.status.in_(["Pending", "Confirmed"])
    ).first()
