from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import Optional, List, Any
from datetime import datetime
import json

from models import User, Venue, get_db, UserRole
from schemas import VenueCreate, VenueResponse, VenueUpdate

router = APIRouter(prefix="/venues", tags=["venues"])

@router.get("", response_model=List[VenueResponse])
def list_venues(
    manager_id: Optional[int] = Query(None, description="Filter by manager"),
    db: Session = Depends(get_db)
):
    """
    List all venues. Can filter by manager_id.
    """
    query = db.query(Venue)
    
    if manager_id:
        query = query.filter(Venue.manager_id == manager_id)
    
    venues = query.all()
    return venues

@router.get("/{venue_id}")
def get_venue(
    venue_id: int,
    guest_count: Optional[int] = Query(None, description="Calculate estimated price for this guest count"),
    db: Session = Depends(get_db)
):
    """
    Get venue details with optional estimated price and availability calendar.
    """
    venue = db.query(Venue).filter(Venue.id == venue_id).first()
    
    if not venue:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Venue not found"
        )
    
    # Parse images from JSON string
    images = None
    if venue.images:
        try:
            images = json.loads(venue.images)
        except:
            images = venue.images.split(",") if venue.images else None
    
    estimated_price = None
    if guest_count:
        from utils import calculate_price
        estimated_price = calculate_price(venue.base_fee, venue.per_person_fee, guest_count)
    
    # Generate 12-month availability calendar
    from datetime import date, timedelta
    from utils import generate_availability_calendar
    start_date = date.today()
    end_date = start_date + timedelta(days=365)
    availability_calendar = generate_availability_calendar(db, venue_id, start_date, end_date)
    
    result = {
        "id": venue.id,
        "manager_id": venue.manager_id,
        "name": venue.name,
        "address": venue.address,
        "postcode": venue.postcode,
        "description": venue.description,
        "contact_info": venue.contact_info,
        "min_capacity": venue.min_capacity,
        "max_capacity": venue.max_capacity,
        "base_fee": venue.base_fee,
        "per_person_fee": venue.per_person_fee,
        "venue_type": venue.venue_type,
        "status": venue.status,
        "main_image": venue.main_image,
        "images": images,
        "created_at": venue.created_at.isoformat() if venue.created_at else None,
        "estimated_price": estimated_price,
        "availability_calendar": availability_calendar
    }
    
    return result

@router.post("", response_model=VenueResponse, status_code=status.HTTP_201_CREATED)
def create_venue(
    venue_data: VenueCreate,
    manager_id: int,
    db: Session = Depends(get_db)
):
    """
    Create a new venue. Only managers can create venues.
    """
    # Verify manager exists
    manager = db.query(User).filter(User.id == manager_id, User.role == UserRole.MANAGER.value).first()
    if not manager:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Manager not found or unauthorized"
        )
    
    # Validate description length
    if len(venue_data.description) < 200:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Description must be at least 200 characters"
        )
    
    # Convert images list to JSON string
    images_json = None
    if venue_data.images:
        images_json = json.dumps(venue_data.images)
    
    # Get the venue_type value - handle both enum and string
    venue_type_val = venue_data.venue_type.value if hasattr(venue_data.venue_type, 'value') else venue_data.venue_type
    status_val = venue_data.status.value if hasattr(venue_data.status, 'value') else venue_data.status
    
    new_venue = Venue(
        manager_id=manager_id,
        name=venue_data.name,
        address=venue_data.address,
        postcode=venue_data.postcode,
        description=venue_data.description,
        contact_info=venue_data.contact_info,
        min_capacity=venue_data.min_capacity,
        max_capacity=venue_data.max_capacity,
        base_fee=venue_data.base_fee,
        per_person_fee=venue_data.per_person_fee,
        venue_type=venue_type_val,
        status=status_val,
        main_image=venue_data.main_image,
        images=images_json
    )
    
    db.add(new_venue)
    db.commit()
    db.refresh(new_venue)
    
    return new_venue

@router.put("/{venue_id}", response_model=VenueResponse)
def update_venue(
    venue_id: int,
    venue_data: VenueUpdate,
    manager_id: int,
    db: Session = Depends(get_db)
):
    """
    Update a venue. Only the venue's manager can update it.
    """
    venue = db.query(Venue).filter(Venue.id == venue_id).first()
    
    if not venue:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Venue not found"
        )
    
    # Verify ownership
    if venue.manager_id != manager_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to update this venue"
        )
    
    update_data = venue_data.model_dump(exclude_unset=True)
    
    # Handle images conversion
    if "images" in update_data and update_data["images"]:
        update_data["images"] = json.dumps(update_data["images"])
    
    for key, value in update_data.items():
        if key in ["venue_type", "status"] and value:
            setattr(venue, key, value.value if hasattr(value, 'value') else value)
        else:
            setattr(venue, key, value)
    
    db.commit()
    db.refresh(venue)
    
    return venue

@router.delete("/{venue_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_venue(
    venue_id: int,
    manager_id: int,
    db: Session = Depends(get_db)
):
    """
    Delete a venue. Only the venue's manager can delete it.
    """
    venue = db.query(Venue).filter(Venue.id == venue_id).first()
    
    if not venue:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Venue not found"
        )
    
    # Verify ownership
    if venue.manager_id != manager_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to delete this venue"
        )
    
    db.delete(venue)
    db.commit()
