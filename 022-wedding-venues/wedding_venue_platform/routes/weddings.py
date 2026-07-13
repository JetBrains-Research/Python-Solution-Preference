from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import Optional, List

from models import Venue, WeddingBooking, get_db
from schemas import WeddingBookingCreate, WeddingBookingResponse, WeddingBookingUpdate
from utils import calculate_price, get_pending_or_confirmed_booking

router = APIRouter(prefix="/weddings", tags=["weddings"])

@router.get("/requests", response_model=List[WeddingBookingResponse])
def list_wedding_requests(
    couple_id: Optional[int] = Query(None, description="Filter by couple"),
    db: Session = Depends(get_db)
):
    """
    List wedding booking requests. Couples see their own, managers see all.
    """
    query = db.query(WeddingBooking)
    
    if couple_id:
        query = query.filter(WeddingBooking.couple_id == couple_id)
    
    bookings = query.all()
    return bookings

@router.get("/requests/venue/{venue_id}", response_model=List[WeddingBookingResponse])
def list_venue_requests(
    venue_id: int,
    manager_id: int,
    db: Session = Depends(get_db)
):
    """
    List wedding booking requests for a venue. Only the venue's manager can access.
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
            detail="Not authorized to view requests for this venue"
        )
    
    bookings = db.query(WeddingBooking).filter(WeddingBooking.venue_id == venue_id).all()
    return bookings

@router.post("/requests", response_model=WeddingBookingResponse, status_code=status.HTTP_201_CREATED)
def create_wedding_request(
    request_data: WeddingBookingCreate,
    couple_id: int,
    db: Session = Depends(get_db)
):
    """
    Request a wedding date.
    Constraint: No Pending or Confirmed booking can exist for the same venue/date.
    """
    venue = db.query(Venue).filter(Venue.id == request_data.venue_id).first()
    
    if not venue:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Venue not found"
        )
    
    # Check if date is available
    from utils import is_date_available
    if not is_date_available(db, request_data.venue_id, request_data.booking_date):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Date is not available (blocked or already booked)"
        )
    
    # Check for pending or confirmed booking on same venue/date
    existing = get_pending_or_confirmed_booking(db, request_data.venue_id, request_data.booking_date)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A pending or confirmed booking already exists for this venue and date"
        )
    
    # Check guest count within capacity
    if request_data.guest_count < venue.min_capacity or request_data.guest_count > venue.max_capacity:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Guest count is outside venue capacity"
        )
    
    # Calculate estimated price
    estimated_price = calculate_price(venue.base_fee, venue.per_person_fee, request_data.guest_count)
    
    new_booking = WeddingBooking(
        venue_id=request_data.venue_id,
        couple_id=couple_id,
        booking_date=request_data.booking_date,
        guest_count=request_data.guest_count,
        note=request_data.note,
        status="Pending",
        estimated_price=estimated_price
    )
    
    db.add(new_booking)
    db.commit()
    db.refresh(new_booking)
    
    return new_booking

@router.get("/requests/{booking_id}", response_model=WeddingBookingResponse)
def get_wedding_request(
    booking_id: int,
    couple_id: Optional[int] = Query(None),
    manager_id: Optional[int] = Query(None),
    db: Session = Depends(get_db)
):
    """
    Get wedding booking request details.
    """
    booking = db.query(WeddingBooking).filter(WeddingBooking.id == booking_id).first()
    
    if not booking:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Wedding booking not found"
        )
    
    # Verify authorization
    if couple_id and booking.couple_id != couple_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to view this booking"
        )
    
    if manager_id:
        venue = db.query(Venue).filter(Venue.id == booking.venue_id).first()
        if venue.manager_id != manager_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to view this booking"
            )
    
    # Include couple info for managers
    if manager_id:
        from models import User
        couple = db.query(User).filter(User.id == booking.couple_id).first()
        if couple:
            return {
                **booking.model_dump(),
                "couple_info": {
                    "email": couple.email,
                    "partner_name": couple.partner_name,
                    "wedding_date": couple.wedding_date.isoformat() if couple.wedding_date else None
                }
            }
    
    return booking

@router.put("/requests/{booking_id}", response_model=WeddingBookingResponse)
def update_wedding_request(
    booking_id: int,
    update_data: WeddingBookingUpdate,
    manager_id: int,
    db: Session = Depends(get_db)
):
    """
    Confirm or decline a wedding booking request. Only managers can do this.
    Confirming makes the date Booked (immutable).
    """
    booking = db.query(WeddingBooking).filter(WeddingBooking.id == booking_id).first()
    
    if not booking:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Wedding booking not found"
        )
    
    # Verify manager owns the venue
    venue = db.query(Venue).filter(Venue.id == booking.venue_id).first()
    
    if venue.manager_id != manager_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to update this booking"
        )
    
    # Check if booking is already confirmed (Booked dates are immutable)
    if booking.status == "Confirmed":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot modify a confirmed booking"
        )
    
    if update_data.status == "Confirmed":
        booking.status = "Confirmed"
    elif update_data.status == "Declined":
        booking.status = "Declined"
        booking.decline_reason = update_data.decline_reason
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid status"
        )
    
    db.commit()
    db.refresh(booking)
    
    return booking
