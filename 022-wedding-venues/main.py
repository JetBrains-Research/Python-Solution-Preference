from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime, timedelta
from database import engine, get_db, Base
import models, schemas, services

Base.metadata.create_all(bind=engine)

app = FastAPI()

@app.post("/signup/couple", response_model=schemas.UserResponse)
def signup_couple(user: schemas.CoupleSignUp, db: Session = Depends(get_db)):
    return services.create_user(db, user)

@app.post("/signup/manager", response_model=schemas.UserResponse)
def signup_manager(user: schemas.ManagerSignUp, db: Session = Depends(get_db)):
    return services.create_user(db, user)

@app.post("/venues", response_model=schemas.VenueResponse)
def create_venue(venue: schemas.VenueCreate, manager_id: int, db: Session = Depends(get_db)):
    # In a real app, we would verify the manager_id via authentication
    return services.create_venue(db, manager_id, venue)

@app.post("/search", response_model=List[schemas.VenueResponse])
def search(params: schemas.SearchParams, db: Session = Depends(get_db)):
    venues = services.search_venues(db, params)
    return venues

@app.get("/venues/{venue_id}")
def get_venue(venue_id: int, guest_count: Optional[int] = None, db: Session = Depends(get_db)):
    details = services.get_venue_details(db, venue_id, guest_count)
    if not details:
        raise HTTPException(status_code=404, detail="Venue not found")
    return details

@app.post("/venues/{venue_id}/availability")
def update_availability(venue_id: int, update: schemas.AvailabilityUpdate, db: Session = Depends(get_db)):
    avail = db.query(models.Availability).filter(
        models.Availability.venue_id == venue_id, 
        models.Availability.date == update.date.date()
    ).first()
    if not avail:
        avail = models.Availability(venue_id=venue_id, date=update.date.date())
        db.add(avail)
    avail.status = update.status
    avail.note = update.note
    db.commit()
    return {"status": "updated"}

@app.post("/venues/{venue_id}/tours/slots")
def create_tour_slot(venue_id: int, slot_data: schemas.TourSlotCreate, db: Session = Depends(get_db)):
    try:
        # Convert date + time to datetime
        start_time = datetime.combine(slot_data.date.date(), 
                                     datetime.strptime(slot_data.time, "%H:%M").time())
        # We need to adapt services.create_tour_slot slightly or just pass the datetime
        # I'll create a small helper here since I can't easily edit services.py again without another turn
        # But wait, I can just redefine the call.
        
        # I need to modify services.py to accept the combined datetime.
        # Let me check my services.py code. It expects slot_data.start_time.
        # I will wrap it.
        
        # Since I can't edit services.py easily without a turn, I will use a modified call.
        # Let's assume slot_data is a Pydantic model, I'll create a dummy object for the service.
        
        class SlotDataHelper:
            def __init__(self, date, start_time, duration_minutes, capacity):
                self.date = date
                self.start_time = start_time
                self.duration_minutes = duration_minutes
                self.capacity = capacity
        
        helper = SlotDataHelper(slot_data.date, start_time, slot_data.duration_minutes, slot_data.capacity)
        return services.create_tour_slot(db, venue_id, helper)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/tours/book", response_model=schemas.TourBookingResponse)
def book_tour(booking: schemas.TourBookingRequest, couple_id: int, db: Session = Depends(get_db)):
    try:
        return services.book_tour(db, couple_id, booking)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/tours/bookings/{booking_id}/handle")
def handle_tour(booking_id: int, approve: bool, db: Session = Depends(get_db)):
    try:
        return services.handle_tour_request(db, booking_id, approve)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/weddings/request", response_model=schemas.WeddingBookingResponse)
def request_wedding(request: schemas.WeddingBookingRequest, couple_id: int, db: Session = Depends(get_db)):
    try:
        return services.request_wedding(db, couple_id, request)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/weddings/bookings/{booking_id}/handle")
def handle_wedding(booking_id: int, approve: bool, reason: Optional[str] = None, db: Session = Depends(get_db)):
    try:
        return services.handle_wedding_request(db, booking_id, approve, reason)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
