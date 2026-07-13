from fastapi import FastAPI, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime

from app.database import engine, Base, get_db
from app.models import User, Event, Attendance, InviteCode
from app.schemas import (
    UserCreate, UserOut, UserProfileUpdate, 
    InviteCodeCreate, InviteCodeOut, 
    EventCreate, EventListOut, EventDetailOut, 
    AttendeeOut, AttendanceOut, AttendanceAdminOut,
    Token
)
from app.auth import (
    get_password_hash, verify_password, create_access_token,
    get_current_user, get_current_member, get_current_admin
)
from app import crud

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Creative Community Events Platform")

# --- Initialization ---
def init_db():
    db = next(get_db())
    # Create Default Admin
    admin_username = "core_admin"
    if not db.query(User).filter(User.username == admin_username).first():
        admin = User(
            username=admin_username,
            email="admin@example.com",
            hashed_password=get_password_hash("CoreAdmin!2025"),
            is_admin=True,
            full_name="Core Admin",
            location="Bronx, NY",
            creative_role="Designer"
        )
        db.add(admin)
        db.commit()
    
    # Create a default invite code for testing if none exist
    if not db.query(InviteCode).first():
        code = InviteCode(
            code="WELCOME2025",
            code_type="multi",
            max_uses=100,
            expiration_date=datetime(2025, 12, 31),
            is_active=True,
            description="Initial batch of invite codes"
        )
        db.add(code)
        db.commit()

init_db()

# --- Auth Endpoints ---

@app.post("/register", response_model=Token)
def register(user_in: UserCreate, db: Session = Depends(get_db)):
    user = crud.create_user(db, user_in)
    access_token = create_access_token(data={"sub": user.username})
    return {"access_token": access_token, "token_type": "bearer"}

@app.post("/token", response_model=Token)
def login(form_data: UserCreate, db: Session = Depends(get_db)):
    # Using UserCreate as a simple way to get username/password from body for the MVP
    user = crud.get_user_by_username(db, form_data.username)
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(status_code=400, detail="Incorrect username or password")
    
    access_token = create_access_token(data={"sub": user.username})
    return {"access_token": access_token, "token_type": "bearer"}

@app.patch("/profile", response_model=UserOut)
def update_profile(profile_in: UserProfileUpdate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return crud.update_user_profile(db, current_user.id, profile_in)

# --- Event Endpoints ---

@app.get("/events", response_model=List[EventListOut])
def list_events(db: Session = Depends(get_db)):
    events = crud.get_events(db)
    result = []
    for e in events:
        count = db.query(Attendance).filter(Attendance.event_id == e.id).count()
        result.append(EventListOut.from_orm_event(e, count))
    return result

@app.get("/events/{event_id}", response_model=EventDetailOut)
def get_event(event_id: int, db: Session = Depends(get_db)):
    event = db.query(Event).filter(Event.id == event_id).first()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    
    has_passed = event.date_time < datetime.utcnow()
    return {
        "id": event.id,
        "title": event.title,
        "description": event.description,
        "date_time": event.date_time,
        "location": event.location,
        "category": event.category,
        "capacity": event.capacity,
        "price": event.price,
        "has_passed": has_passed
    }

@app.post("/events/{event_id}/rsvp")
def rsvp(event_id: int, current_user: User = Depends(get_current_member), db: Session = Depends(get_db)):
    crud.rsvp_to_event(db, current_user.id, event_id)
    return {"message": "RSVP successful"}

@app.get("/events/{event_id}/attendees", response_model=List[AttendeeOut])
def get_attendees(event_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rsvp = db.query(Attendance).filter(Attendance.user_id == current_user.id, Attendance.event_id == event_id).first()
    if not rsvp:
        raise HTTPException(status_code=403, detail="You must RSVP to view the attendee list")
    
    attendances = db.query(Attendance).filter(Attendance.event_id == event_id).all()
    return [{"full_name": att.user.full_name, "creative_role": att.user.creative_role} for att in attendances]

# --- Member Endpoints ---

@app.get("/my-events", response_model=List[AttendanceOut])
def my_events(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    attendances = db.query(Attendance).filter(Attendance.user_id == current_user.id).all()
    return [
        {
            "event_name": att.event.title,
            "date_time": att.event.date_time,
            "amount_owed": att.amount_owed,
            "payment_status": att.payment_status
        } for att in attendances
    ]

@app.get("/my-events/total-owed")
def total_owed(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    unpaid_records = db.query(Attendance).filter(Attendance.user_id == current_user.id, Attendance.payment_status != "paid").all()
    total = sum(rec.amount_owed for rec in unpaid_records)
    return {"total_owed": total}

# --- Admin Endpoints ---

@app.post("/admin/codes", response_model=InviteCodeOut)
def admin_create_code(code_in: InviteCodeCreate, admin: User = Depends(get_current_admin), db: Session = Depends(get_db)):
    return crud.create_invite_code(db, code_in)

@app.get("/admin/codes", response_model=List[InviteCodeOut])
def admin_list_codes(admin: User = Depends(get_current_admin), db: Session = Depends(get_db)):
    return db.query(InviteCode).all()

@app.patch("/admin/codes/{code_id}/deactivate")
def admin_deactivate_code(code_id: int, admin: User = Depends(get_current_admin), db: Session = Depends(get_db)):
    crud.deactivate_invite_code(db, code_id)
    return {"message": "Code deactivated"}

@app.delete("/admin/codes/{code_id}")
def admin_delete_code(code_id: int, admin: User = Depends(get_current_admin), db: Session = Depends(get_db)):
    crud.delete_invite_code(db, code_id)
    return {"message": "Code deleted"}

@app.post("/admin/events", response_model=EventDetailOut)
def admin_create_event(event_in: EventCreate, admin: User = Depends(get_current_admin), db: Session = Depends(get_db)):
    event = crud.create_event(db, event_in)
    return event

@app.delete("/admin/events/{event_id}")
def admin_delete_event(event_id: int, admin: User = Depends(get_current_admin), db: Session = Depends(get_db)):
    event = db.query(Event).filter(Event.id == event_id).first()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    db.delete(event)
    db.commit()
    return {"message": "Event deleted"}

@app.get("/admin/users", response_model=List[UserOut])
def admin_list_users(admin: User = Depends(get_current_admin), db: Session = Depends(get_db)):
    return crud.get_all_users(db)

@app.patch("/admin/users/{user_id}/admin")
def admin_update_user_status(user_id: int, is_admin: bool, admin: User = Depends(get_current_admin), db: Session = Depends(get_db)):
    if admin.id == user_id: #’cannot change own status’
        raise HTTPException(status_code=400, detail="Cannot change own admin status")
    crud.update_user_admin_status(db, user_id, is_admin)
    return {"message": "Admin status updated"}

@app.delete("/admin/users/{user_id}")
def admin_delete_user(user_id: int, admin: User = Depends(get_current_admin), db: Session = Depends(get_db)):
    crud.delete_user(db, user_id)
    return {"message": "User deleted"}

@app.get("/admin/attendance", response_model=List[AttendanceAdminOut])
def admin_list_attendance(event_id: Optional[int] = None, status: Optional[str] = None, admin: User = Depends(get_current_admin), db: Session = Depends(get_db)):
    query = db.query(Attendance)
    if event_id:
        query = query.filter(Attendance.event_id == event_id)
    if status:
        query = query.filter(Attendance.payment_status == status)
    
    results = query.all()
    return [
        {
            "id": att.id,
            "user_id": att.user_id,
            "username": att.user.username,
            "full_name": att.user.full_name,
            "event_id": att.event_id,
            "event_title": att.event.title,
            "attended": att.attended,
            "amount_owed": att.amount_owed,
            "payment_status": att.payment_status,
            "payment_date": att.payment_date,
            "admin_notes": att.admin_notes
        } for att in results
    ]

@app.patch("/admin/attendance/{att_id}/attended")
def admin_mark_attendance(att_id: int, attended: bool, admin: User = Depends(get_current_admin), db: Session = Depends(get_db)):
    crud.update_attendance_status(db, att_id, attended)
    return {"message": "Attendance status updated"}

@app.post("/admin/attendance/{att_id}/no-show")
def admin_add_no_show(att_id: int, admin: User = Depends(get_current_admin), db: Session = Depends(get_db)):
    crud.add_no_show_fee(db, att_id)
    return {"message": "No-show fee applied"}

@app.patch("/admin/attendance/{att_id}/payment")
def admin_update_payment(att_id: int, status: str, admin: User = Depends(get_current_admin), db: Session = Depends(get_db)):
    crud.update_payment_status(db, att_id, status)
    return {"message": "Payment status updated"}

@app.get("/admin/payments/summary")
def admin_payment_summary(event_id: Optional[int] = None, status: Optional[str] = None, admin: User = Depends(get_current_admin), db: Session = Depends(get_db)):
    query = db.query(Attendance)
    if event_id:
        query = query.filter(Attendance.event_id == event_id)
    if status:
        query = query.filter(Attendance.payment_status == status)
    
    records = query.all()
    
    total_outstanding = sum(r.amount_owed for r in records if r.payment_status == "unpaid")
    total_collected = sum(r.amount_owed for r in records if r.payment_status == "paid")
    unpaid_count = len([r for r in records if r.payment_status == "unpaid"])
    
    return {
        "total_outstanding": total_outstanding,
        "total_collected": total_collected,
        "unpaid_count": unpaid_count
    }
