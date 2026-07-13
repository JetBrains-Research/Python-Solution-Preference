from fastapi import FastAPI, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import date, datetime

from app.database import engine, get_db, Base
from app.models import User, Property, Equipment, Booking, Job, JobNote, JobPhoto, Invoice, UserRole, JobStatus, InvoiceStatus
from app.schemas import (
    UserCreate, UserOut, Token, PropertyCreate, PropertyOut, 
    EquipmentCreate, EquipmentOut, BookingCreate, BookingOut, 
    JobConvert, JobOut, JobStatusUpdate, JobNoteCreate, JobNoteOut, 
    JobPhotoCreate, JobPhotoOut, InvoiceCreate, InvoiceOut, InvoiceStatusUpdate
)
from app.auth import (
    get_password_hash, verify_password, create_access_token, 
    get_current_user, require_role
)
from app.crud import (
    get_user_by_email, create_user, create_property, delete_property,
    create_equipment, create_booking, convert_booking_to_job, 
    update_job_status, add_job_note, add_job_photo, create_invoice, update_invoice_status
)
from fastapi.security import OAuth2PasswordRequestForm

Base.metadata.create_all(bind=engine)

app = FastAPI()

# --- AUTH ---

@app.post("/auth/signup", response_model=Token)
def signup(user: UserCreate, db: Session = Depends(get_db)):
    db_user = get_user_by_email(db, user.email)
    if db_user:
        raise HTTPException(status_code=400, detail="Email already registered")
    user_obj = create_user(db, user)
    access_token = create_access_token(data={"sub": user_obj.email})
    return {"access_token": access_token, "token_type": "bearer"}

@app.post("/auth/login", response_model=Token)
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = get_user_by_email(db, form_data.username)
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(status_code=400, detail="Incorrect email or password")
    access_token = create_access_token(data={"sub": user.email})
    return {"access_token": access_token, "token_type": "bearer"}

# --- PROPERTIES & EQUIPMENT ---

@app.post("/properties", response_model=PropertyOut)
def add_property(prop: PropertyCreate, current_user: User = Depends(require_role("Client")), db: Session = Depends(get_db)):
    return create_property(db, prop, current_user.id)

@app.get("/properties", response_model=List[PropertyOut])
def list_properties(current_user: User = Depends(require_role("Client")), db: Session = Depends(get_db)):
    return db.query(Property).filter(Property.owner_id == current_user.id).all()

@app.delete("/properties/{property_id}")
def remove_property(property_id: int, current_user: User = Depends(require_role("Client")), db: Session = Depends(get_db)):
    prop = db.query(Property).filter(Property.id == property_id, Property.owner_id == current_user.id).first()
    if not prop:
        raise HTTPException(status_code=404, detail="Property not found")
    delete_property(db, property_id)
    return {"detail": "Property deleted"}

@app.post("/equipment", response_model=EquipmentOut)
def add_equipment(equip: EquipmentCreate, current_user: User = Depends(require_role("Client")), db: Session = Depends(get_db)):
    prop = db.query(Property).filter(Property.id == equip.property_id, Property.owner_id == current_user.id).first()
    if not prop:
        raise HTTPException(status_code=404, detail="Property not found or not owned by user")
    return create_equipment(db, equip)

# --- BOOKINGS ---

@app.post("/bookings", response_model=BookingOut)
def submit_booking(booking: BookingCreate, current_user: Optional[User] = Depends(get_current_user), db: Session = Depends(get_db)):
    try:
        client_id = current_user.id if current_user else None
        return create_booking(db, booking, client_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/bookings", response_model=List[BookingOut])
def list_bookings(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if current_user.role.value == "Technician":
        return db.query(Booking).filter(Booking.status == "New").all()
    else:
        return db.query(Booking).filter(Booking.status == "New", Booking.client_id == current_user.id).all()

@app.get("/bookings/track/{token}", response_model=BookingOut)
def track_booking(token: str, db: Session = Depends(get_db)):
    booking = db.query(Booking).filter(Booking.tracking_token == token).first()
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")
    return booking

# --- JOBS ---

@app.post("/jobs/convert/{booking_id}", response_model=JobOut)
def convert_booking(booking_id: int, job_data: JobConvert, current_user: User = Depends(require_role("Technician")), db: Session = Depends(get_db)):
    job = convert_booking_to_job(db, booking_id, current_user.id, job_data)
    if not job:
        raise HTTPException(status_code=400, detail="Booking cannot be converted")
    return job

@app.get("/jobs/{job_id}", response_model=JobOut)
def get_job(job_id: int, current_user: Optional[User] = Depends(get_current_user), token: Optional[str] = None, db: Session = Depends(get_db)):
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    # Authorization
    if token:
        if job.booking.tracking_token == token:
            return job
    if current_user:
        if current_user.id == job.technician_id or (job.booking.client_id and current_user.id == job.booking.client_id):
            return job
            
    raise HTTPException(status_code=403, detail="Access denied")

@app.patch("/jobs/{job_id}/status", response_model=JobOut)
def update_status(job_id: int, status_upd: JobStatusUpdate, current_user: User = Depends(require_role("Technician")), db: Session = Depends(get_db)):
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job or job.technician_id != current_user.id:
        raise HTTPException(status_code=404, detail="Job not found or not assigned to you")
    
    try:
        return update_job_status(db, job_id, status_upd.status)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/jobs/{job_id}/notes", response_model=JobNoteOut)
def add_note(job_id: int, note: JobNoteCreate, current_user: User = Depends(require_role("Technician")), db: Session = Depends(get_db)):
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job or job.technician_id != current_user.id:
        raise HTTPException(status_code=404, detail="Job not found or not assigned to you")
    return add_job_note(db, job_id, note)

@app.post("/jobs/{job_id}/photos", response_model=JobPhotoOut)
def add_photo(job_id: int, photo: JobPhotoCreate, current_user: User = Depends(require_role("Technician")), db: Session = Depends(get_db)):
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job or job.technician_id != current_user.id:
        raise HTTPException(status_code=404, detail="Job not found or not assigned to you")
    return add_job_photo(db, job_id, photo)

# --- INVOICES ---

@app.post("/invoices", response_model=InvoiceOut)
def create_inv(invoice: InvoiceCreate, current_user: User = Depends(require_role("Technician")), db: Session = Depends(get_db)):
    # Need to check if job is Completed and technician is assigned
    job = db.query(Job).filter(Job.id == invoice.job_id, Job.technician_id == current_user.id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found or not assigned to you")
    if job.status != JobStatus.Completed:
        raise HTTPException(status_code=400, detail="Job must be Completed before invoicing")
    
    try:
        return create_invoice(db, invoice.job_id, invoice)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.patch("/invoices/{invoice_id}/status", response_model=InvoiceOut)
def update_inv_status(invoice_id: int, status_upd: InvoiceStatusUpdate, current_user: User = Depends(require_role("Technician")), db: Session = Depends(get_db)):
    inv = db.query(Invoice).filter(Invoice.id == invoice_id).first()
    if not inv:
        raise HTTPException(status_code=404, detail="Invoice not found")
    
    # Only the assigned technician for the job can manage the invoice
    job = inv.job
    if job.technician_id != current_user.id:
        raise HTTPException(status_code=403, detail="Only the assigned technician can manage this invoice")
        
    try:
        return update_invoice_status(db, invoice_id, status_upd.status)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/invoices/{invoice_id}", response_model=InvoiceOut)
def get_invoice(invoice_id: int, current_user: Optional[User] = Depends(get_current_user), token: Optional[str] = None, db: Session = Depends(get_db)):
    inv = db.query(Invoice).filter(Invoice.id == invoice_id).first()
    if not inv:
        raise HTTPException(status_code=404, detail="Invoice not found")
    
    if inv.status == InvoiceStatus.Draft:
        # Only Technician can see Draft
        if not current_user or current_user.id != inv.job.technician_id:
            raise HTTPException(status_code=403, detail="Invoice is not yet available")
        return inv

    # Sent, Paid, Void, Overdue: Client, Guest, or Tech can see
    if token:
        if inv.job.booking.tracking_token == token:
            return inv
    if current_user:
        if current_user.id == inv.job.technician_id or (inv.job.booking.client_id and current_user.id == inv.job.booking.client_id):
            return inv
            
    raise HTTPException(status_code=403, detail="Access denied")

# --- BACKGROUND TASK FOR OVERDUE ---
# In a real app, this would be a celery task. Here we could implement a simple check
# on invoice retrieval or a separate endpoint. For MVP, we assume the system
# handles "Overdue" via an update call or external trigger.
