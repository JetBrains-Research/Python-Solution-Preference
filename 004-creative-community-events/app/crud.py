from sqlalchemy.orm import Session
from app.models import User, InviteCode, Event, Attendance
from app.schemas import UserCreate, UserProfileUpdate, EventCreate, InviteCodeCreate
from app.auth import get_password_hash
from datetime import datetime
from fastapi import HTTPException, status

def get_user_by_username(db: Session, username: str):
    return db.query(User).filter(User.username == username).first()

def create_user(db: Session, user_in: UserCreate):
    # Validate invite code
    code_obj = db.query(InviteCode).filter(InviteCode.code == user_in.invite_code).first()
    if not code_obj:
        raise HTTPException(status_code=400, detail="Invalid invite code")
    
    now = datetime.utcnow()
    if not code_obj.is_active:
        raise HTTPException(status_code=400, detail="Invite code is deactivated")
    if code_obj.expiration_date < now:
        raise HTTPException(status_code=400, detail="Invite code has expired")
    if code_obj.uses >= code_obj.max_uses:
        raise HTTPException(status_code=400, detail="Invite code has been exhausted")

    # Create user
    db_user = User(
        username=user_in.username,
        email=user_in.email,
        hashed_password=get_password_hash(user_in.password)
    )
    db.add(db_user)
    
    # Update invite code
    code_obj.uses += 1
    
    db.commit()
    db.refresh(db_user)
    return db_user

def update_user_profile(db: Session, user_id: int, profile_in: UserProfileUpdate):
    db_user = db.query(User).filter(User.id == user_id).first()
    for var, value in profile_in.dict(exclude_unset=True).items():
        setattr(db_user, var, value)
    db.commit()
    db.refresh(db_user)
    return db_user

def get_events(db: Session):
    return db.query(Event).order_by(Event.date_time.asc()).all()

def create_event(db: Session, event_in: EventCreate):
    db_event = Event(**event_in.dict())
    db.add(db_event)
    db.commit()
    db.refresh(db_event)
    return db_event

def rsvp_to_event(db: Session, user_id: int, event_id: int):
    event = db.query(Event).filter(Event.id == event_id).first()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    
    if event.date_time < datetime.utcnow():
        raise HTTPException(status_code=400, detail="Event has passed")
    
    current_attendees = db.query(Attendance).filter(Attendance.event_id == event_id).count()
    if current_attendees >= event.capacity:
        raise HTTPException(status_code=400, detail="Event is full")
        
    existing = db.query(Attendance).filter(Attendance.user_id == user_id, Attendance.event_id == event_id).first()
    if existing:
        raise HTTPException(status_code=400, detail="Already RSVP'd to this event")
    
    payment_status = "paid" if event.price == 0 else "unpaid"
    attendance = Attendance(
        user_id=user_id,
        event_id=event_id,
        amount_owed=event.price,
        payment_status=payment_status
    )
    db.add(attendance)
    db.commit()
    db.refresh(attendance)
    return attendance

def create_invite_code(db: Session, code_in: InviteCodeCreate):
    db_code = InviteCode(**code_in.dict())
    db.add(db_code)
    db.commit()
    db.refresh(db_code)
    return db_code

def deactivate_invite_code(db: Session, code_id: int):
    db_code = db.query(InviteCode).filter(InviteCode.id == code_id).first()
    if db_code:
        db_code.is_active = False
        db.commit()
    return db_code

def delete_invite_code(db: Session, code_id: int):
    db_code = db.query(InviteCode).filter(InviteCode.id == code_id).first()
    if db_code:
        db.delete(db_code)
        db.commit()
    return db_code

def get_all_users(db: Session):
    return db.query(User).all()

def update_user_admin_status(db: Session, user_id: int, is_admin: bool):
    db_user = db.query(User).filter(User.id == user_id).first()
    if db_user:
        db_user.is_admin = is_admin
        db.commit()
    return db_user

def delete_user(db: Session, user_id: int):
    user = db.query(User).filter(User.id == user_id).first()
    if user:
        # Find all attendances for this user to restore capacity is not needed 
        # since capacity is checked against total attendance records.
        # However, removing the attendance record effectively restores the spot.
        db.query(Attendance).filter(Attendance.user_id == user_id).delete()
        db.delete(user)
        db.commit()
    return True

def update_attendance_status(db: Session, attendance_id: int, attended: bool):
    att = db.query(Attendance).filter(Attendance.id == attendance_id).first()
    if att:
        att.attended = attended
        db.commit()
    return att

def add_no_show_fee(db: Session, attendance_id: int):
    att = db.query(Attendance).filter(Attendance.id == attendance_id).first()
    if att:
        # Check if fee already applied? The request says "Can only be added once per attendance"
        # We can use admin_notes or a flag. Let's check if amount_owed > ticket price.
        event = db.query(Event).filter(Event.id == att.event_id).first()
        if att.amount_owed == event.price:
            att.amount_owed += 50.0
            att.payment_status = "unpaid"
            db.commit()
        else:
            raise HTTPException(status_code=400, detail="No-show fee already applied")
    return att

def update_payment_status(db: Session, attendance_id: int, status: str):
    att = db.query(Attendance).filter(Attendance.id == attendance_id).first()
    if att:
        att.payment_status = status
        if status == "paid":
            att.payment_date = datetime.utcnow()
        db.commit()
    return att
