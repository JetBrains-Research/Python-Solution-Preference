from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import Optional, List
from datetime import datetime, date, timedelta

from models import Venue, TourSlot, TourBooking, get_db, BlockedDate, WeddingBooking
from schemas import TourSlotCreate, TourSlotResponse, TourBookingCreate, TourBookingResponse, TourBookingUpdate
from utils import (
    is_date_available,
    check_slot_overlap,
    is_24_hours_in_advance
)

router = APIRouter(prefix="/tours", tags=["tours"])

# Tour Slot Routes

@router.get("/slots/venue/{venue_id}", response_model=List[TourSlotResponse])
def list_tour_slots(
    venue_id: int,
    manager_id: Optional[int] = Query(None, description="Filter by manager"),
    db: Session = Depends(get_db)
):
    """
    List all tour slots for a venue.
    """
    venue = db.query(Venue).filter(Venue.id == venue_id).first()
    
    if not venue:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Venue not found"
        )
    
    slots = db.query(TourSlot).filter(TourSlot.venue_id == venue_id).all()
    
    result = []
    for slot in slots:
        result.append({
            "id": slot.id,
            "venue_id": slot.venue_id,
            "slot_date": slot.slot_date,
            "slot_time": slot.slot_time,
            "duration_minutes": slot.duration_minutes,
            "capacity": slot.capacity,
            "remaining_capacity": slot.remaining_capacity,
            "is_full": slot.remaining_capacity <= 0
        })
    
    return result

@router.post("/slots/venue/{venue_id}", response_model=TourSlotResponse, status_code=status.HTTP_201_CREATED)
def create_tour_slot(
    venue_id: int,
    slot_data: TourSlotCreate,
    manager_id: int,
    db: Session = Depends(get_db)
):
    """
    Create a tour slot. Only the venue's manager can create slots.
    No slots on Blocked/Booked dates. No overlapping slots.
    """
    venue = db.query(Venue).filter(Venue.id == venue_id).first()
    
    if not venue:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Venue not found"
        )
    
    if venue.manager_id != manager_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to create slots for this venue"
        )
    
    # Check if date is available (not blocked or booked)
    if not is_date_available(db, venue_id, slot_data.slot_date):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot create slot on a blocked or booked date"
        )
    
    # Check for overlapping slots
    if check_slot_overlap(db, venue_id, slot_data.slot_date, slot_data.slot_time, slot_data.duration_minutes):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Slot overlaps with an existing slot"
        )
    
    new_slot = TourSlot(
        venue_id=venue_id,
        slot_date=slot_data.slot_date,
        slot_time=slot_data.slot_time,
        duration_minutes=slot_data.duration_minutes,
        capacity=slot_data.capacity,
        remaining_capacity=slot_data.capacity
    )
    
    db.add(new_slot)
    db.commit()
    db.refresh(new_slot)
    
    return new_slot

@router.delete("/slots/{slot_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_tour_slot(
    slot_id: int,
    manager_id: int,
    db: Session = Depends(get_db)
):
    """
    Delete a tour slot. Only the venue's manager can delete.
    """
    slot = db.query(TourSlot).filter(TourSlot.id == slot_id).first()
    
    if not slot:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tour slot not found"
        )
    
    venue = db.query(Venue).filter(Venue.id == slot.venue_id).first()
    
    if venue.manager_id != manager_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to delete this slot"
        )
    
    # Check if there are any bookings for this slot
    existing_bookings = db.query(TourBooking).filter(TourBooking.slot_id == slot_id).all()
    if existing_bookings:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete slot with existing bookings"
        )
    
    db.delete(slot)
    db.commit()

# Tour Booking Routes

@router.get("/bookings/slot/{slot_id}", response_model=List[TourBookingResponse])
def list_tour_bookings(
    slot_id: int,
    db: Session = Depends(get_db)
):
    """
    List all bookings for a tour slot.
    """
    bookings = db.query(TourBooking).filter(TourBooking.slot_id == slot_id).all()
    return bookings

@router.post("/bookings", response_model=TourBookingResponse, status_code=status.HTTP_201_CREATED)
def book_tour_slot(
    booking_data: TourBookingCreate,
    couple_id: int,
    db: Session = Depends(get_db)
):
    """
    Book a tour slot. Must book 24+ hours in advance.
    """
    slot = db.query(TourSlot).filter(TourSlot.id == booking_data.slot_id).first()
    
    if not slot:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tour slot not found"
        )
    
    # Check if booking is 24+ hours in advance
    if not is_24_hours_in_advance(slot.slot_date, slot.slot_time):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Must book at least 24 hours in advance"
        )
    
    # Check if slot is full (remaining_capacity <= 0 means no more approvals possible)
    # But we still allow pending requests - they just can't be approved
    # Actually, let's allow the booking but it will be pending
    
    new_booking = TourBooking(
        slot_id=booking_data.slot_id,
        couple_id=couple_id,
        tour_type=booking_data.tour_type.value,
        attendee_count=booking_data.attendee_count,
        notes=booking_data.notes,
        status="Pending"
    )
    
    db.add(new_booking)
    db.commit()
    db.refresh(new_booking)
    
    return new_booking

@router.put("/bookings/{booking_id}", response_model=TourBookingResponse)
def update_tour_booking(
    booking_id: int,
    update_data: TourBookingUpdate,
    manager_id: int,
    db: Session = Depends(get_db)
):
    """
    Approve or deny a tour booking. Only managers can do this.
    Approving decrements remaining capacity by 1.
    Full slots cannot have new approvals - pending requests must be denied.
    """
    booking = db.query(TourBooking).filter(TourBooking.id == booking_id).first()
    
    if not booking:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tour booking not found"
        )
    
    # Verify manager owns the venue
    slot = db.query(TourSlot).filter(TourSlot.id == booking.slot_id).first()
    venue = db.query(Venue).filter(Venue.id == slot.venue_id).first()
    
    if venue.manager_id != manager_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to update this booking"
        )
    
    if update_data.status == "Approved":
        # Check if slot is full
        if slot.remaining_capacity <= 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot approve booking - slot is full"
            )
        
        # Decrement remaining capacity
        slot.remaining_capacity -= 1
        booking.status = "Approved"
    elif update_data.status == "Denied":
        booking.status = "Denied"
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid status"
        )
    
    db.commit()
    db.refresh(booking)
    
    return booking
