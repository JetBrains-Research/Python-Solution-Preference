import enum
import secrets
from datetime import datetime

from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

class CategoryEnum(enum.Enum):
    electronics = "Electronics"
    fashion = "Fashion"
    home_garden = "Home & Garden"
    vehicles = "Vehicles"
    collectibles = "Collectibles"
    sports = "Sports"
    books = "Books"
    other = "Other"

class ConditionEnum(enum.Enum):
    new = "new"
    like_new = "like-new"
    good = "good"
    fair = "fair"

class ProductStatus(enum.Enum):
    available = "available"
    pending = "pending"
    sold = "sold"

class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(120), nullable=False)
    description = db.Column(db.Text, nullable=False)
    price = db.Column(db.Float, nullable=False)
    category = db.Column(db.Enum(CategoryEnum), nullable=False)
    condition = db.Column(db.Enum(ConditionEnum), nullable=False)
    location = db.Column(db.String(120), nullable=False)
    image_url = db.Column(db.String(255), nullable=False)
    seller_name = db.Column(db.String(120), nullable=False)
    seller_email = db.Column(db.String(120), nullable=False)

    seller_token = db.Column(db.String(64), unique=True, nullable=False, default=lambda: secrets.token_urlsafe(32))
    status = db.Column(db.Enum(ProductStatus), nullable=False, default=ProductStatus.available)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationship to order
    order = db.relationship('Order', backref='product', uselist=False)

class OrderStatus(enum.Enum):
    pending = "pending"
    confirmed = "confirmed"
    cancelled = "cancelled"

class Order(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False, unique=True)
    buyer_name = db.Column(db.String(120), nullable=False)
    buyer_email = db.Column(db.String(120), nullable=False)
    buyer_phone = db.Column(db.String(30), nullable=False)
    buyer_token = db.Column(db.String(64), unique=True, nullable=False, default=lambda: secrets.token_urlsafe(32))
    status = db.Column(db.Enum(OrderStatus), nullable=False, default=OrderStatus.pending)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
