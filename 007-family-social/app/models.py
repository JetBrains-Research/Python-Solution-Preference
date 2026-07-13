from datetime import datetime, date
from app import db, login_manager
from flask_login import UserMixin
import enum

# Define string enums for SQLAlchemy compatibility
class RelationshipType:
    PARENT = 'Parent'
    CHILD = 'Child'
    SPOUSE = 'Spouse'
    SIBLING = 'Sibling'

class RelationshipStatus:
    PENDING = 'Pending'
    ACTIVE = 'Active'
    DECLINED = 'Declined'
    CANCELED = 'Canceled'
    ENDED = 'Ended'

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_active = db.Column(db.Boolean, default=True)

    # Relationships
    profile = db.relationship('Profile', backref='user', uselist=False)
    posts = db.relationship('Post', backref='author', lazy=True)

    # Family relationships
    outgoing_relationships = db.relationship('Relationship', foreign_keys='Relationship.requester_id', backref='requester', lazy=True)
    incoming_relationships = db.relationship('Relationship', foreign_keys='Relationship.recipient_id', backref='recipient', lazy=True)

    def set_password(self, password):
        from app import bcrypt
        self.password_hash = bcrypt.generate_password_hash(password).decode('utf-8')

    def check_password(self, password):
        from app import bcrypt
        return bcrypt.check_password_hash(self.password_hash, password)

class Profile(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), unique=True, nullable=False)

    username = db.Column(db.String(30), unique=True, nullable=False)
    display_name = db.Column(db.String(100), nullable=False)
    bio = db.Column(db.Text)
    profile_photo = db.Column(db.String(255))
    birth_date = db.Column(db.Date)

    is_complete = db.Column(db.Boolean, default=False)

    def __repr__(self):
        return f'<Profile {self.username}>'

class Relationship(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    requester_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    recipient_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

    # Type as selected by requester
    requester_type = db.Column(db.String(20), nullable=False)
    # Type as seen by recipient (reciprocal)
    recipient_type = db.Column(db.String(20), nullable=False)

    status = db.Column(db.String(20), default='Pending', nullable=False)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Ensure one relationship per user pair
    __table_args__ = (
        db.UniqueConstraint('requester_id', 'recipient_id', name='unique_relationship_pair_1'),
    )

    def __repr__(self):
        return f'<Relationship {self.id}>'

class Post(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    caption = db.Column(db.Text)
    images = db.Column(db.JSON)  # List of image URLs
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f'<Post {self.id}>'

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))
