from datetime import datetime
from ..models import db, ProductStatus, generate_token

class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=False)
    price = db.Column(db.Float, nullable=False)
    category = db.Column(db.String(50), nullable=False)
    condition = db.Column(db.String(20), nullable=False)
    location = db.Column(db.String(100), nullable=False)
    image_path = db.Column(db.String(200), nullable=False)
    seller_name = db.Column(db.String(100), nullable=False)
    seller_email = db.Column(db.String(100), nullable=False)
    status = db.Column(db.String(20), nullable=False, default=ProductStatus.AVAILABLE)

    # Token for seller to manage this product
    seller_token = db.Column(db.String(64), unique=True, nullable=False)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationship to orders
    order = db.relationship('Order', backref='product', uselist=False)

    def __repr__(self):
        return f'<Product {self.title}>'

    def to_dict(self):
        return {
            'id': self.id,
            'title': self.title,
            'description': self.description,
            'price': self.price,
            'category': self.category,
            'condition': self.condition,
            'location': self.location,
            'image_path': self.image_path,
            'seller_name': self.seller_name,
            'seller_email': self.seller_email,
            'status': self.status,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }

    def to_browse_dict(self):
        """Return minimal info for browse view"""
        return {
            'id': self.id,
            'image_path': self.image_path,
            'condition': self.condition,
            'title': self.title,
            'price': self.price,
            'location': self.location,
            'seller_name': self.seller_name
        }
