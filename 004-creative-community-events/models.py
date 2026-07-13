from datetime import datetime, timezone
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import func

db = SQLAlchemy()

class User(db.Model):
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)
    is_admin = db.Column(db.Boolean, default=False)

    # Profile fields
    full_name = db.Column(db.String(120))
    phone = db.Column(db.String(20))
    location = db.Column(db.String(120))
    creative_role = db.Column(db.String(30))
    bio = db.Column(db.String(500))
    profile_complete = db.Column(db.Boolean, default=False)

    created_at = db.Column(db.DateTime, default=lambda: datetime.utcnow())

    attendances = db.relationship('Attendance', backref='user', lazy='dynamic',
                                  cascade='all, delete-orphan')

    def to_dict_basic(self):
        return {
            'id': self.id,
            'username': self.username,
            'email': self.email,
            'full_name': self.full_name,
            'is_admin': self.is_admin,
            'created_at': self.created_at.isoformat(),
        }

class InviteCode(db.Model):
    __tablename__ = 'invite_codes'

    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(50), unique=True, nullable=False)
    type = db.Column(db.String(10), nullable=False)  # 'single' or 'multi'
    max_uses = db.Column(db.Integer)
    current_uses = db.Column(db.Integer, default=0)
    expires_at = db.Column(db.DateTime, nullable=False)
    deactivated = db.Column(db.Boolean, default=False)
    description = db.Column(db.String(200))
    created_at = db.Column(db.DateTime, default=lambda: datetime.utcnow())

    registrations = db.relationship('CodeUsage', backref='invite_code', lazy='dynamic',
                                    cascade='all, delete-orphan')

    @property
    def status(self):
        if self.deactivated:
            return 'deactivated'
        if datetime.utcnow() > self.expires_at:
            return 'expired'
        if self.type == 'single' and self.current_uses >= 1:
            return 'exhausted'
        if self.type == 'multi' and self.max_uses and self.current_uses >= self.max_uses:
            return 'exhausted'
        return 'active'

    @property
    def can_use(self):
        return self.status == 'active'

    def to_dict(self):
        return {
            'id': self.id,
            'code': self.code,
            'type': self.type,
            'max_uses': self.max_uses,
            'current_uses': self.current_uses,
            'expires_at': self.expires_at.isoformat(),
            'status': self.status,
            'description': self.description,
            'created_at': self.created_at.isoformat(),
        }

class CodeUsage(db.Model):
    __tablename__ = 'code_usages'
    id = db.Column(db.Integer, primary_key=True)
    invite_code_id = db.Column(db.Integer, db.ForeignKey('invite_codes.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    used_at = db.Column(db.DateTime, default=lambda: datetime.utcnow())

class Event(db.Model):
    __tablename__ = 'events'

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(120), nullable=False)
    description = db.Column(db.Text, nullable=False)
    event_datetime = db.Column(db.DateTime, nullable=False)
    location = db.Column(db.String(200), nullable=False)
    category = db.Column(db.String(20), nullable=False)  # workshop, networking, exhibition, screening, social
    capacity = db.Column(db.Integer, nullable=False)
    price_cents = db.Column(db.Integer, default=0)  # in cents, 0 for free
    created_at = db.Column(db.DateTime, default=lambda: datetime.utcnow())
    deleted = db.Column(db.Boolean, default=False)

    attendances = db.relationship('Attendance', backref='event', lazy='dynamic',
                                  cascade='all, delete-orphan')

    def spots_remaining(self):
        rsvp_count = self.attendances.filter_by(deleted=False).count()
        return max(0, self.capacity - rsvp_count)

    def is_full(self):
        return self.spots_remaining() == 0

    def is_past(self):
        return self.event_datetime < datetime.utcnow()

    def truncated_description(self, max_len=100):
        if len(self.description) <= max_len:
            return self.description
        return self.description[:max_len-3] + '...'

    def price_display(self):
        if self.price_cents == 0:
            return 'Free'
        dollars = self.price_cents / 100
        return f"${dollars:.2f}"

    def to_dict_list(self):
        remaining = self.spots_remaining()
        return {
            'id': self.id,
            'title': self.title,
            'description': self.truncated_description(),
            'event_datetime': self.event_datetime.isoformat(),
            'location': self.location,
            'category': self.category,
            'capacity': self.capacity,
            'spots_remaining': remaining,
            'capacity_display': 'Full' if remaining == 0 else f"{remaining} spots remaining",
            'price': self.price_display(),
            'price_cents': self.price_cents,
            'is_past': self.is_past(),
        }

    def to_dict_detail(self, user_rsvpd=False):
        base = self.to_dict_list()
        base['description'] = self.description  # full description
        base['attendees'] = []
        if user_rsvpd:
            attendees = Attendance.query.filter_by(event_id=self.id, deleted=False).all()
            base['attendees'] = [{
                'full_name': att.user.full_name,
                'creative_role': att.user.creative_role
            } for att in attendees]
        return base

class Attendance(db.Model):
    __tablename__ = 'attendances'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    event_id = db.Column(db.Integer, db.ForeignKey('events.id'), nullable=False)
    rsvp_at = db.Column(db.DateTime, default=lambda: datetime.utcnow())
    deleted = db.Column(db.Boolean, default=False)

    # Payment/attendance tracking
    attended = db.Column(db.Boolean, default=False)
    no_show_fee_applied = db.Column(db.Boolean, default=False)
    payment_status = db.Column(db.String(15), default='unpaid')  # unpaid, processing, paid
    payment_date = db.Column(db.DateTime, nullable=True)
    admin_notes = db.Column(db.String(500))

    # Ticket price at time of RSVP (in cents)
    ticket_price_cents = db.Column(db.Integer, nullable=False)

    @property
    def amount_owed_cents(self):
        total = self.ticket_price_cents
        if self.no_show_fee_applied:
            total += 5000  # $50
        return total

    def amount_owed_display(self):
        return f"${self.amount_owed_cents / 100:.2f}"

    def to_dict_member(self):
        return {
            'id': self.id,
            'event_id': self.event_id,
            'event_title': self.event.title,
            'event_datetime': self.event.event_datetime.isoformat(),
            'amount_owed': self.amount_owed_display(),
            'amount_owed_cents': self.amount_owed_cents,
            'payment_status': self.payment_status,
        }

    def to_dict_admin(self):
        return {
            'id': self.id,
            'user_id': self.user_id,
            'user_full_name': self.user.full_name,
            'user_email': self.user.email,
            'event_id': self.event_id,
            'event_title': self.event.title,
            'event_datetime': self.event.event_datetime.isoformat(),
            'attended': self.attended,
            'no_show_fee_applied': self.no_show_fee_applied,
            'payment_status': self.payment_status,
            'payment_date': self.payment_date.isoformat() if self.payment_date else None,
            'amount_owed_cents': self.amount_owed_cents,
            'amount_owed_display': self.amount_owed_display(),
            'admin_notes': self.admin_notes,
        }

    # For uniqueness: one RSVP per member per event (non-deleted)
