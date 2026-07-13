from datetime import datetime
from ..models import db, OrderStatus, generate_token

class Order(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False)
    buyer_name = db.Column(db.String(100), nullable=False)
    buyer_email = db.Column(db.String(100), nullable=False)
    buyer_phone = db.Column(db.String(20), nullable=False)

    # Token for buyer to track their order
    buyer_token = db.Column(db.String(64), unique=True, nullable=True)

    status = db.Column(db.String(20), nullable=False, default=OrderStatus.PENDING)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f'<Order {self.id} for Product {self.product_id}>'

    def to_dict(self):
        return {
            'id': self.id,
            'product_id': self.product_id,
            'buyer_name': self.buyer_name,
            'buyer_email': self.buyer_email,
            'buyer_phone': self.buyer_phone,
            'status': self.status,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }
