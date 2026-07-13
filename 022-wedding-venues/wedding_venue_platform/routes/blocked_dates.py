from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import Optional, List

from models import Venue, BlockedDate, get_db
from schemas import BlockedDateCreate, BlockedDateResponse, BlockedDateUpdate

router = APIRouter(prefix="/blocked-dates", tags=["blocked-dates"])

@router.get("/venue/{venue_id}", response_model=List[BlockedDateResponse])
def list_blocked_dates(
    venue_id: int,
    manager_id: int,
    db: Session = Depends(get_db)
):
    """
    List all blocked dates for a venue. Only the venue's manager can access.
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
            detail="Not authorized to view blocked dates for this venue"
        )
    
    blocked_dates = db.query(BlockedDate).filter(BlockedDate.venue_id == venue_id).all()
    return blocked_dates

@router.post("/venue/{venue_id}", response_model=BlockedDateResponse, status_code=status.HTTP_201_CREATED)
def create_blocked_date(
    venue_id: int,
    blocked_data: BlockedDateCreate,
    manager_id: int,
    db: Session = Depends(get_db)
):
    """
    Create a blocked date for a venue. Only the venue's manager can create.
    Cannot block dates that are already booked.
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
            detail="Not authorized to block dates for this venue"
        )
    
    # Check if date is already blocked
    existing_blocked = db.query(BlockedDate).filter(
        BlockedDate.venue_id == venue_id,
        BlockedDate.blocked_date == blocked_data.blocked_date
    ).first()
    
    if existing_blocked:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Date is already blocked"
        )
    
    # Check if date is already booked (immutable)
    from models import WeddingBooking
    existing_booking = db.query(WeddingBooking).filter(
        WeddingBooking.venue_id == venue_id,
        WeddingBooking.booking_date == blocked_data.blocked_date,
        WeddingBooking.status == "Confirmed"
    ).first()
    
    if existing_booking:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot block a date that is already booked"
        )
    
    new_blocked = BlockedDate(
        venue_id=venue_id,
        blocked_date=blocked_data.blocked_date,
        note=blocked_data.note
    )
    
    db.add(new_blocked)
    db.commit()
    db.refresh(new_blocked)
    
    return new_blocked

@router.put("/venue/{venue_id}/{blocked_date}", response_model=BlockedDateResponse)
def update_blocked_date(
    venue_id: int,
    blocked_date: str,
    update_data: BlockedDateUpdate,
    manager_id: int,
    db: Session = Depends(get_db)
):
    """
    Update a blocked date's note. Only the venue's manager can update.
    """
    from datetime import date as date_type
    
    try:
        blocked_date_obj = date_type.fromisoformat(blocked_date)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid date format"
        )
    
    venue = db.query(Venue).filter(Venue.id == venue_id).first()
    
    if not venue:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Venue not found"
        )
    
    if venue.manager_id != manager_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to update blocked dates for this venue"
        )
    
    blocked = db.query(BlockedDate).filter(
        BlockedDate.venue_id == venue_id,
        BlockedDate.blocked_date == blocked_date_obj
    ).first()
    
    if not blocked:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Blocked date not found"
        )
    
    update_data_dict = update_data.model_dump(exclude_unset=True)
    for key, value in update_data_dict.items():
        setattr(blocked, key, value)
    
    db.commit()
    db.refresh(blocked)
    
    return blocked

@router.delete("/venue/{venue_id}/{blocked_date}", status_code=status.HTTP_204_NO_CONTENT)
def delete_blocked_date(
    venue_id: int,
    blocked_date: str,
    manager_id: int,
    db: Session = Depends(get_db)
):
    """
    Remove a blocked date. Only the venue's manager can delete.
    """
    from datetime import date as date_type
    
    try:
        blocked_date_obj = date_type.fromisoformat(blocked_date)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid date format"
        )
    
    venue = db.query(Venue).filter(Venue.id == venue_id).first()
    
    if not venue:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Venue not found"
        )
    
    if venue.manager_id != manager_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to delete blocked dates for this venue"
        )
    
    blocked = db.query(BlockedDate).filter(
        BlockedDate.venue_id == venue_id,
        BlockedDate.blocked_date == blocked_date_obj
    ).first()
    
    if not blocked:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Blocked date not found"
        )
    
    db.delete(blocked)
    db.commit()
