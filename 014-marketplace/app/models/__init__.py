from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import secrets

# Product status constants
class ProductStatus:
    AVAILABLE = 'available'
    PENDING = 'pending'
    SOLD = 'sold'

# Order status constants
class OrderStatus:
    PENDING = 'pending'
    CONFIRMED = 'confirmed'
    CANCELLED = 'cancelled'

# Valid categories and conditions
VALID_CATEGORIES = [
    'Electronics', 'Fashion', 'Home & Garden', 'Vehicles',
    'Collectibles', 'Sports', 'Books', 'Other'
]

VALID_CONDITIONS = ['new', 'like-new', 'good', 'fair']

def generate_token():
    """Generate a cryptographically secure random token"""
    return secrets.token_urlsafe(32)

# Create db instance here - this will be imported and used everywhere
db = SQLAlchemy()

# Import models after db is defined
from .product import Product
from .order import Order
