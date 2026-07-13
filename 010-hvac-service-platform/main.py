from fastapi import FastAPI, Depends, HTTPException, status, Request, Response, Query
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_
from datetime import datetime, timedelta
from typing import Optional, List
import uuid
import secrets
from passlib.context import CryptContext

from database import get_db, engine
from models import (
    User, UserRole, Property, Equipment, Booking, BookingState,
    Job, JobStatus, JobNote, JobPhoto, Invoice, InvoiceStatus,
    ServiceType, BookingType, Category, Urgency, TimeWindow, EquipmentType
)
from schemas import (
    UserCreate, UserLogin, UserResponse,
    PropertyCreate, PropertyResponse,
    EquipmentCreate, EquipmentResponse,
    BookingCreate, BookingResponse, BookingSummary,
    JobCreate, JobNoteCreate, JobPhotoCreate, JobResponse, JobNoteResponse, JobPhotoResponse,
    InvoiceCreate, InvoiceResponse
)

app = FastAPI(title="HVAC/Plumbing Service Platform")
security = HTTPBearer()
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# In-memory session storage for logged-in users
active_sessions = {}


def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security), db: Session = Depends(get_db)) -> User:
    token = credentials.credentials
    if token in active_sessions:
        user_id = active_sessions[token]
        user = db.query(User).filter(User.id == user_id).first()
        if user:
            return user
    raise HTTPException(status_code=401, detail="Not authenticated")


def create_token(user_id: int) -> str:
    token = secrets.token_urlsafe(32)
    active_sessions[token] = user_id
    return token


def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password):
    return pwd_context.hash(password)


# Auth endpoints
@app.post("/signup", response_model=UserResponse)
def signup(user_data: UserCreate, db: Session = Depends(get_db), response: Response = None):
    existing_user = db.query(User).filter(User.email == user_data.email).first()
    if existing_user:
        raise HTTPException(status_code=400, detail="Email already registered")
    
    hashed_password = get_password_hash(user_data.password)
    user = User(
        name=user_data.name,
        email=user_data.email,
        password_hash=hashed_password,
        role=user_data.role.value
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    
    token = create_token(user.id)
    if response:
        response.headers["Authorization"] = f"Bearer {token}"
    return user


@app.post("/login", response_model=UserResponse)
def login(credentials: UserLogin, db: Session = Depends(get_db), response: Response = None):
    user = db.query(User).filter(User.email == credentials.email).first()
    if not user or not verify_password(credentials.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    token = create_token(user.id)
    if response:
        response.headers["Authorization"] = f"Bearer {token}"
    return user


@app.get("/me", response_model=UserResponse)
def get_me(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return user


# Property endpoints (Client only)
@app.get("/properties", response_model=List[PropertyResponse])
def list_properties(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if user.role != "Client":
        raise HTTPException(status_code=403, detail="Access denied")
    return db.query(Property).filter(Property.user_id == user.id).all()


@app.post("/properties", response_model=PropertyResponse)
def create_property(property_data: PropertyCreate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if user.role != "Client":
        raise HTTPException(status_code=403, detail="Access denied")
    
    property_obj = Property(
        user_id=user.id,
        label=property_data.label,
        street=property_data.street,
        city=property_data.city,
        state=property_data.state,
        zip_code=property_data.zip_code
    )
    db.add(property_obj)
    db.commit()
    db.refresh(property_obj)
    return property_obj


@app.delete("/properties/{property_id}", status_code=204)
def delete_property(property_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if user.role != "Client":
        raise HTTPException(status_code=403, detail="Access denied")
    
    property_obj = db.query(Property).filter(Property.id == property_id, Property.user_id == user.id).first()
    if not property_obj:
        raise HTTPException(status_code=404, detail="Property not found")
    
    db.delete(property_obj)
    db.commit()


# Equipment endpoints (Client only)
@app.get("/properties/{property_id}/equipment", response_model=List[EquipmentResponse])
def list_equipment(property_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if user.role != "Client":
        raise HTTPException(status_code=403, detail="Access denied")
    
    property_obj = db.query(Property).filter(Property.id == property_id, Property.user_id == user.id).first()
    if not property_obj:
        raise HTTPException(status_code=404, detail="Property not found")
    
    return db.query(Equipment).filter(Equipment.property_id == property_id).all()


@app.post("/properties/{property_id}/equipment", response_model=EquipmentResponse)
def create_equipment(property_id: int, equipment_data: EquipmentCreate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if user.role != "Client":
        raise HTTPException(status_code=403, detail="Access denied")
    
    property_obj = db.query(Property).filter(Property.id == property_id, Property.user_id == user.id).first()
    if not property_obj:
        raise HTTPException(status_code=404, detail="Property not found")
    
    equipment = Equipment(
        property_id=property_id,
        service_type=equipment_data.service_type.value,
        equipment_type=equipment_data.equipment_type.value,
        manufacturer=equipment_data.manufacturer,
        model=equipment_data.model,
        serial=equipment_data.serial,
        install_date=equipment_data.install_date,
        notes=equipment_data.notes
    )
    db.add(equipment)
    db.commit()
    db.refresh(equipment)
    return equipment


# Booking endpoints
@app.post("/bookings", response_model=BookingResponse)
def create_booking(booking_data: BookingCreate, request: Request, db: Session = Depends(get_db)):
    tracking_token = secrets.token_urlsafe(32)
    
    # Get optional user from auth header
    auth_header = request.headers.get("Authorization")
    user = None
    if auth_header:
        parts = auth_header.split()
        if len(parts) == 2 and parts[0].lower() == "bearer":
            token = parts[1]
            if token in active_sessions:
                user_id = active_sessions[token]
                user = db.query(User).filter(User.id == user_id).first()
    
    # Get address info - start with provided values
    name = booking_data.name
    email = booking_data.email
    phone = booking_data.phone
    street = booking_data.street
    city = booking_data.city
    state = booking_data.state
    zip_code = booking_data.zip_code
    
    # If user is authenticated client, use their info for name/email
    if user and user.role == "Client":
        if name is None:
            name = user.name
        if email is None:
            email = user.email
    
    # Handle property selection for address
    if booking_data.property_id and user and user.role == "Client":
        property_obj = db.query(Property).filter(Property.id == booking_data.property_id, Property.user_id == user.id).first()
        if property_obj:
            if street is None:
                street = property_obj.street
            if city is None:
                city = property_obj.city
            if state is None:
                state = property_obj.state
            if zip_code is None:
                zip_code = property_obj.zip_code
    
    # Validate required fields for guest bookings
    if not user or user.role != "Client":
        if not all([name, email, phone, street, city, state, zip_code]):
            raise HTTPException(status_code=400, detail="Name, email, phone, and address are required for guest bookings")
    
    # Commercial requires company name
    if booking_data.booking_type.value == "Commercial" and not booking_data.company_name:
        raise HTTPException(status_code=400, detail="Company name required for commercial bookings")
    
    # Validate preferred date
    if booking_data.preferred_date:
        if booking_data.preferred_date.date() < datetime.utcnow().date():
            raise HTTPException(status_code=400, detail="Preferred date cannot be in the past")
    
    booking = Booking(
        tracking_token=tracking_token,
        service_type=booking_data.service_type.value,
        booking_type=booking_data.booking_type.value,
        category=booking_data.category.value,
        urgency=booking_data.urgency.value,
        name=name,
        email=email,
        phone=phone,
        street=street,
        city=city,
        state=state,
        zip_code=zip_code,
        company_name=booking_data.company_name,
        preferred_date=booking_data.preferred_date,
        time_window=booking_data.time_window.value if booking_data.time_window else None,
        description=booking_data.description,
        booking_state="New",
        client_id=user.id if user and user.role == "Client" else None
    )
    db.add(booking)
    db.commit()
    db.refresh(booking)
    return booking


@app.get("/bookings", response_model=List[BookingResponse])
def list_bookings(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if user.role == "Client":
        return db.query(Booking).filter(Booking.client_id == user.id, Booking.booking_state == "New").all()
    elif user.role == "Technician":
        return db.query(Booking).filter(Booking.booking_state == "New").all()
    raise HTTPException(status_code=403, detail="Access denied")


@app.get("/bookings/{booking_id}", response_model=BookingResponse)
def get_booking(booking_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    booking = db.query(Booking).filter(Booking.id == booking_id).first()
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")
    
    if user.role == "Client" and booking.client_id == user.id:
        return booking
    if user.role == "Technician" and booking.booking_state == "New":
        return booking
    raise HTTPException(status_code=403, detail="Access denied")


@app.get("/bookings/token/{tracking_token}", response_model=BookingResponse)
def get_booking_by_token(tracking_token: str, db: Session = Depends(get_db)):
    booking = db.query(Booking).filter(Booking.tracking_token == tracking_token).first()
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")
    return booking


# Job endpoints
@app.post("/bookings/{booking_id}/convert", response_model=JobResponse)
def convert_booking_to_job(booking_id: int, job_data: JobCreate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if user.role != "Technician":
        raise HTTPException(status_code=403, detail="Access denied")
    
    booking = db.query(Booking).filter(Booking.id == booking_id, Booking.booking_state == "New").first()
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")
    
    if job_data.scheduled_date.date() < datetime.utcnow().date():
        raise HTTPException(status_code=400, detail="Scheduled date cannot be in the past")
    
    # Check if already converted
    existing_job = db.query(Job).filter(Job.booking_id == booking_id).first()
    if existing_job:
        raise HTTPException(status_code=400, detail="Booking already converted to job")
    
    job = Job(
        booking_id=booking_id,
        technician_id=user.id,
        scheduled_date=job_data.scheduled_date,
        time_window=job_data.time_window.value,
        status="Scheduled"
    )
    db.add(job)
    
    booking.booking_state = "Converted"
    booking.job_id = job.id
    db.commit()
    db.refresh(job)
    
    # Build response with notes and photos
    job_response = JobResponse(
        id=job.id,
        booking_id=job.booking_id,
        technician_name=user.name,
        scheduled_date=job.scheduled_date,
        time_window=job.time_window,
        status=job.status,
        street=booking.street,
        city=booking.city,
        state=booking.state,
        zip_code=booking.zip_code,
        notes=[],
        photos=[],
        created_at=job.created_at
    )
    return job_response


@app.get("/jobs", response_model=List[JobResponse])
def list_jobs(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if user.role != "Technician":
        raise HTTPException(status_code=403, detail="Access denied")
    
    jobs = db.query(Job).filter(Job.technician_id == user.id).all()
    result = []
    for job in jobs:
        booking = db.query(Booking).filter(Booking.id == job.booking_id).first()
        notes = db.query(JobNote).filter(JobNote.job_id == job.id).all()
        photos = db.query(JobPhoto).filter(JobPhoto.job_id == job.id).all()
        result.append(JobResponse(
            id=job.id,
            booking_id=job.booking_id,
            technician_name=user.name,
            scheduled_date=job.scheduled_date,
            time_window=job.time_window,
            status=job.status,
            street=booking.street,
            city=booking.city,
            state=booking.state,
            zip_code=booking.zip_code,
            notes=[JobNoteResponse(id=n.id, content=n.content, created_at=n.created_at) for n in notes],
            photos=[JobPhotoResponse(id=p.id, filename=p.filename, created_at=p.created_at) for p in photos],
            created_at=job.created_at
        ))
    return result


@app.get("/jobs/{job_id}", response_model=JobResponse)
def get_job(job_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    # Technician can only see their own jobs
    if user.role == "Technician" and job.technician_id != user.id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Client can only see jobs from their bookings
    if user.role == "Client":
        booking = db.query(Booking).filter(Booking.id == job.booking_id, Booking.client_id == user.id).first()
        if not booking:
            raise HTTPException(status_code=403, detail="Access denied")
    
    booking = db.query(Booking).filter(Booking.id == job.booking_id).first()
    notes = db.query(JobNote).filter(JobNote.job_id == job_id).all()
    photos = db.query(JobPhoto).filter(JobPhoto.job_id == job_id).all()
    
    technician = db.query(User).filter(User.id == job.technician_id).first()
    
    return JobResponse(
        id=job.id,
        booking_id=job.booking_id,
        technician_name=technician.name,
        scheduled_date=job.scheduled_date,
        time_window=job.time_window,
        status=job.status,
        street=booking.street,
        city=booking.city,
        state=booking.state,
        zip_code=booking.zip_code,
        notes=[JobNoteResponse(id=n.id, content=n.content, created_at=n.created_at) for n in notes],
        photos=[JobPhotoResponse(id=p.id, filename=p.filename, created_at=p.created_at) for p in photos],
        created_at=job.created_at
    )


@app.get("/jobs/token/{tracking_token}", response_model=JobResponse)
def get_job_by_token(tracking_token: str, db: Session = Depends(get_db)):
    booking = db.query(Booking).filter(Booking.tracking_token == tracking_token).first()
    if not booking or not booking.job_id:
        raise HTTPException(status_code=404, detail="Job not found")
    
    job = db.query(Job).filter(Job.id == booking.job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    notes = db.query(JobNote).filter(JobNote.job_id == job.id).all()
    photos = db.query(JobPhoto).filter(JobPhoto.job_id == job.id).all()
    technician = db.query(User).filter(User.id == job.technician_id).first()
    
    return JobResponse(
        id=job.id,
        booking_id=job.booking_id,
        technician_name=technician.name,
        scheduled_date=job.scheduled_date,
        time_window=job.time_window,
        status=job.status,
        street=booking.street,
        city=booking.city,
        state=booking.state,
        zip_code=booking.zip_code,
        notes=[JobNoteResponse(id=n.id, content=n.content, created_at=n.created_at) for n in notes],
        photos=[JobPhotoResponse(id=p.id, filename=p.filename, created_at=p.created_at) for p in photos],
        created_at=job.created_at
    )


@app.post("/jobs/{job_id}/notes", response_model=JobNoteResponse)
def add_job_note(job_id: int, note_data: JobNoteCreate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if user.role != "Technician":
        raise HTTPException(status_code=403, detail="Access denied")
    
    job = db.query(Job).filter(Job.id == job_id, Job.technician_id == user.id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    note = JobNote(job_id=job_id, content=note_data.content)
    db.add(note)
    db.commit()
    db.refresh(note)
    return note


@app.post("/jobs/{job_id}/photos", response_model=JobPhotoResponse)
def add_job_photo(job_id: int, photo_data: JobPhotoCreate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if user.role != "Technician":
        raise HTTPException(status_code=403, detail="Access denied")
    
    job = db.query(Job).filter(Job.id == job_id, Job.technician_id == user.id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    photo = JobPhoto(job_id=job_id, filename=photo_data.filename)
    db.add(photo)
    db.commit()
    db.refresh(photo)
    return photo


@app.post("/jobs/{job_id}/status")
def update_job_status(job_id: int, status: str = Query(...), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if user.role != "Technician":
        raise HTTPException(status_code=403, detail="Access denied")
    
    job = db.query(Job).filter(Job.id == job_id, Job.technician_id == user.id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    # Validate status transitions
    valid_transitions = {
        "Scheduled": ["In Progress"],
        "In Progress": ["Completed"],
        "Completed": []
    }
    
    if status not in valid_transitions.get(job.status, []):
        raise HTTPException(status_code=400, detail=f"Invalid status transition from {job.status} to {status}")
    
    # Completion requires at least one note
    if status == "Completed":
        notes = db.query(JobNote).filter(JobNote.job_id == job_id).count()
        if notes == 0:
            raise HTTPException(status_code=400, detail="Completion requires at least one note")
    
    job.status = status
    db.commit()
    return {"status": status}


# Invoice endpoints
@app.post("/jobs/{job_id}/invoices", response_model=InvoiceResponse)
def create_invoice(job_id: int, invoice_data: InvoiceCreate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if user.role != "Technician":
        raise HTTPException(status_code=403, detail="Access denied")
    
    job = db.query(Job).filter(Job.id == job_id, Job.technician_id == user.id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    if job.status != "Completed":
        raise HTTPException(status_code=400, detail="Job must be completed to create invoice")
    
    # Check for active invoice
    active_invoice = db.query(Invoice).filter(
        Invoice.job_id == job_id,
        Invoice.status.in_(["Draft", "Sent", "Overdue"])
    ).first()
    if active_invoice:
        raise HTTPException(status_code=400, detail="Active invoice already exists for this job")
    
    if invoice_data.due_date.date() < datetime.utcnow().date():
        raise HTTPException(status_code=400, detail="Due date must be today or in the future")
    
    invoice = Invoice(
        job_id=job_id,
        creator_id=user.id,
        amount=invoice_data.amount,
        due_date=invoice_data.due_date,
        status="Draft"
    )
    db.add(invoice)
    db.commit()
    db.refresh(invoice)
    return invoice


@app.get("/invoices", response_model=List[InvoiceResponse])
def list_invoices(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if user.role == "Technician":
        invoices = db.query(Invoice).join(Job).filter(
            Job.technician_id == user.id,
            Invoice.status != "Void"
        ).all()
    elif user.role == "Client":
        invoices = db.query(Invoice).join(Job).join(Booking).filter(
            Booking.client_id == user.id,
            Invoice.status.in_(["Sent", "Paid", "Overdue"])
        ).all()
    else:
        raise HTTPException(status_code=403, detail="Access denied")
    
    return invoices


@app.get("/invoices/{invoice_id}", response_model=InvoiceResponse)
def get_invoice(invoice_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    invoice = db.query(Invoice).filter(Invoice.id == invoice_id).first()
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")
    
    if user.role == "Technician":
        job = db.query(Job).filter(Job.id == invoice.job_id, Job.technician_id == user.id).first()
        if not job:
            raise HTTPException(status_code=403, detail="Access denied")
    elif user.role == "Client":
        if invoice.status == "Draft":
            raise HTTPException(status_code=403, detail="Access denied")
        booking = db.query(Booking).join(Job).filter(Job.id == invoice.job_id, Booking.client_id == user.id).first()
        if not booking:
            raise HTTPException(status_code=403, detail="Access denied")
    else:
        raise HTTPException(status_code=403, detail="Access denied")
    
    return invoice


@app.get("/invoices/token/{tracking_token}", response_model=List[InvoiceResponse])
def get_invoices_by_token(tracking_token: str, db: Session = Depends(get_db)):
    booking = db.query(Booking).filter(Booking.tracking_token == tracking_token).first()
    if not booking or not booking.job_id:
        raise HTTPException(status_code=404, detail="No job found for this token")
    
    invoices = db.query(Invoice).filter(
        Invoice.job_id == booking.job_id,
        Invoice.status.in_(["Sent", "Paid", "Overdue"])
    ).all()
    return invoices


@app.post("/invoices/{invoice_id}/send", response_model=InvoiceResponse)
def send_invoice(invoice_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if user.role != "Technician":
        raise HTTPException(status_code=403, detail="Access denied")
    
    invoice = db.query(Invoice).filter(
        Invoice.id == invoice_id,
        Invoice.creator_id == user.id,
        Invoice.status == "Draft"
    ).first()
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found or cannot be sent")
    
    invoice.status = "Sent"
    db.commit()
    db.refresh(invoice)
    return invoice


@app.post("/invoices/{invoice_id}/mark-paid", response_model=InvoiceResponse)
def mark_invoice_paid(invoice_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if user.role != "Technician":
        raise HTTPException(status_code=403, detail="Access denied")
    
    invoice = db.query(Invoice).filter(
        Invoice.id == invoice_id,
        Invoice.creator_id == user.id,
        Invoice.status.in_(["Sent", "Overdue"])
    ).first()
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found or cannot be marked paid")
    
    invoice.status = "Paid"
    db.commit()
    db.refresh(invoice)
    return invoice


@app.post("/invoices/{invoice_id}/void", response_model=InvoiceResponse)
def void_invoice(invoice_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if user.role != "Technician":
        raise HTTPException(status_code=403, detail="Access denied")
    
    invoice = db.query(Invoice).filter(
        Invoice.id == invoice_id,
        Invoice.creator_id == user.id,
        Invoice.status.in_(["Draft", "Sent", "Overdue"])
    ).first()
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found or cannot be voided")
    
    invoice.status = "Void"
    db.commit()
    db.refresh(invoice)
    return invoice


# Check for overdue invoices (should be called periodically)
@app.post("/invoices/check-overdue")
def check_overdue_invoices(db: Session = Depends(get_db)):
    now = datetime.utcnow()
    invoices = db.query(Invoice).filter(
        Invoice.status == "Sent",
        Invoice.due_date < now
    ).all()
    
    for invoice in invoices:
        invoice.status = "Overdue"
    
    db.commit()
    return {"updated": len(invoices)}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
