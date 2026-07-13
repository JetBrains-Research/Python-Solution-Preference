from sqlalchemy.orm import Session
from app.models import User, Property, Equipment, Booking, Job, JobNote, JobPhoto, Invoice, UserRole, JobStatus, InvoiceStatus
from app.schemas import UserCreate, PropertyCreate, EquipmentCreate, BookingCreate, JobConvert, JobNoteCreate, JobPhotoCreate, InvoiceCreate, InvoiceStatusUpdate
from app.auth import get_password_hash
from datetime import date
import uuid

def get_user_by_email(db: Session, email: str):
    return db.query(User).filter(User.email == email).first()

def create_user(db: Session, user: UserCreate):
    db_user = User(
        name=user.name,
        email=user.email,
        hashed_password=get_password_hash(user.password),
        role=user.role
    )
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user

def create_property(db: Session, property: PropertyCreate, owner_id: int):
    db_prop = Property(**property.dict(), owner_id=owner_id)
    db.add(db_prop)
    db.commit()
    db.refresh(db_prop)
    return db_prop

def delete_property(db: Session, property_id: int):
    db_prop = db.query(Property).filter(Property.id == property_id).first()
    if db_prop:
        db.delete(db_prop)
        db.commit()
    return db_prop

def create_equipment(db: Session, equipment: EquipmentCreate):
    db_equip = Equipment(**equipment.dict())
    db.add(db_equip)
    db.commit()
    db.refresh(db_equip)
    return db_equip

def create_booking(db: Session, booking: BookingCreate, client_id: int = None):
    booking_data = booking.dict()
    
    # Handle Property address autofill
    if booking_data.get('property_id'):
        prop = db.query(Property).filter(Property.id == booking_data['property_id']).first()
        if prop:
            booking_data['street'] = prop.street
            booking_data['city'] = prop.city
            booking_data['state'] = prop.state
            booking_data['zip_code'] = prop.zip_code

    # Commercial booking requirement
    if booking_data['booking_type'].value == "Commercial" and not booking_data.get('company_name'):
        raise ValueError("Company Name is required for Commercial bookings")

    # Handle Client flow
    if client_id:
        client = db.query(User).filter(User.id == client_id).first()
        booking_data['name'] = client.name
        booking_data['email'] = client.email
        booking_data['client_id'] = client_id

    db_booking = Booking(**booking_data)
    db.add(db_booking)
    db.commit()
    db.refresh(db_booking)
    return db_booking

def convert_booking_to_job(db: Session, booking_id: int, technician_id: int, job_data: JobConvert):
    booking = db.query(Booking).filter(Booking.id == booking_id, Booking.status == "New").first()
    if not booking:
        return None
    
    booking.status = "Converted"
    
    db_job = Job(
        booking_id=booking_id,
        scheduled_date=job_data.scheduled_date,
        scheduled_time=job_data.scheduled_time,
        technician_id=technician_id,
        status=JobStatus.Scheduled
    )
    db.add(db_job)
    db.commit()
    db.refresh(db_job)
    return db_job

def update_job_status(db: Session, job_id: int, new_status: JobStatus):
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        return None
    
    # Strict order: Scheduled -> In Progress -> Completed
    status_order = {JobStatus.Scheduled: 1, JobStatus.InProgress: 2, JobStatus.Completed: 3}
    if status_order[new_status] != status_order[job.status] + 1:
        raise ValueError("Invalid status transition")
    
    job.status = new_status
    db.commit()
    db.refresh(job)
    return job

def add_job_note(db: Session, job_id: int, note: JobNoteCreate):
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        return None
    db_note = JobNote(job_id=job_id, content=note.content)
    db.add(db_note)
    db.commit()
    db.refresh(db_note)
    return db_note

def add_job_photo(db: Session, job_id: int, photo: JobPhotoCreate):
    db_photo = JobPhoto(job_id=job_id, url=photo.url)
    db.add(db_photo)
    db.commit()
    db.refresh(db_photo)
    return db_photo

def create_invoice(db: Session, job_id: int, invoice_data: InvoiceCreate):
    # Check for active invoice (Draft/Sent/Overdue)
    active_invoice = db.query(Invoice).filter(
        Invoice.job_id == job_id, 
        Invoice.status.in_([InvoiceStatus.Draft, InvoiceStatus.Sent, InvoiceStatus.Overdue])
    ).first()
    
    if active_invoice:
        raise ValueError("An active invoice already exists for this job")
        
    db_invoice = Invoice(job_id=job_id, **invoice_data.dict(), status=InvoiceStatus.Draft)
    db.add(db_invoice)
    db.commit()
    db.refresh(db_invoice)
    return db_invoice

def update_invoice_status(db: Session, invoice_id: int, new_status: InvoiceStatus):
    invoice = db.query(Invoice).filter(Invoice.id == invoice_id).first()
    if not invoice:
        return None
    
    # Transitions: Draft -> Sent -> Paid (terminal); Draft/Sent -> Void; Sent -> Overdue -> Paid/Void
    current = invoice.status
    
    if new_status == InvoiceStatus.Paid:
        if current not in [InvoiceStatus.Sent, InvoiceStatus.Overdue]:
            raise ValueError("Invoice must be Sent or Overdue to be Paid")
    elif new_status == InvoiceStatus.Void:
        if current == InvoiceStatus.Paid:
            raise ValueError("Cannot void a paid invoice")
    elif new_status == InvoiceStatus.Sent:
        if current != InvoiceStatus.Draft:
            raise ValueError("Only Draft invoices can be Sent")
    elif new_status == InvoiceStatus.Overdue:
        if current != InvoiceStatus.Sent:
            raise ValueError("Only Sent invoices can become Overdue")
    else:
        raise ValueError("Invalid status transition")
        
    invoice.status = new_status
    db.commit()
    db.refresh(invoice)
    return invoice
