from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import Optional, List
from datetime import date

from models import Venue, get_db, BlockedDate, WeddingBooking
from schemas import SearchRequest, SearchResponse
from utils import (
    get_postcode_coordinates,
    calculate_venue_distance,
    is_within_radius,
    calculate_price,
    venue_type_matches_filter,
    is_date_available
)

router = APIRouter(prefix="/search", tags=["search"])

@router.post("", response_model=List[SearchResponse])
def search_venues(
    search_data: SearchRequest,
    sort_by: str = Query("distance", description="Sort by 'distance' or 'price'"),
    db: Session = Depends(get_db)
):
    """
    Search venues by postcode, date, and guest count.
    Filters: Active venues, available dates, within capacity, within 30-mile radius, price range.
    """
    # Get all active venues
    venues = db.query(Venue).filter(Venue.status == "Active").all()
    
    results = []
    
    for venue in venues:
        # Check if within 30-mile radius
        if not is_within_radius(search_data.postcode, venue.postcode, 30.0):
            continue
        
        # Check if date is available
        if not is_date_available(db, venue.id, search_data.date):
            continue
        
        # Check if guest count is within capacity
        if search_data.guest_count < venue.min_capacity or search_data.guest_count > venue.max_capacity:
            continue
        
        # Calculate estimated price
        estimated_price = calculate_price(venue.base_fee, venue.per_person_fee, search_data.guest_count)
        
        # Check price range filters
        if search_data.min_price is not None and estimated_price < search_data.min_price:
            continue
        if search_data.max_price is not None and estimated_price > search_data.max_price:
            continue
        
        # Check venue type filter
        if not venue_type_matches_filter(venue.venue_type, search_data.venue_type):
            continue
        
        # Calculate distance
        distance = calculate_venue_distance(search_data.postcode, venue.postcode)
        
        if distance is not None:
            results.append({
                "id": venue.id,
                "name": venue.name,
                "address": venue.address,
                "postcode": venue.postcode,
                "venue_type": venue.venue_type,
                "min_capacity": venue.min_capacity,
                "max_capacity": venue.max_capacity,
                "base_fee": venue.base_fee,
                "per_person_fee": venue.per_person_fee,
                "distance_miles": round(distance, 2),
                "estimated_price": round(estimated_price, 2)
            })
    
    # Sort results
    if sort_by == "price":
        results.sort(key=lambda x: x["estimated_price"])
    else:
        results.sort(key=lambda x: x["distance_miles"])
    
    return results
