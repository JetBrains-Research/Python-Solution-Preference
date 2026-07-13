from database import db
from datetime import datetime

class User(db.Model):
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(120), nullable=False)
    role = db.Column(db.String(20), nullable=False, default='buyer')
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def to_dict(self):
        return {
            'id': self.id,
            'username': self.username,
            'role': self.role,
            'is_active': self.is_active
        }

class Category(db.Model):
    __tablename__ = 'categories'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name
        }

class Stage(db.Model):
    __tablename__ = 'stages'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)
    color = db.Column(db.String(20), default='#6c757d')
    order = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'color': self.color,
            'order': self.order
        }

class Supplier(db.Model):
    __tablename__ = 'suppliers'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    tax_id = db.Column(db.String(50), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    category_id = db.Column(db.Integer, db.ForeignKey('categories.id'), nullable=False)
    is_active = db.Column(db.Boolean, default=True)
    punctuality = db.Column(db.Integer, nullable=True)
    quality = db.Column(db.Integer, nullable=True)
    reliability = db.Column(db.Integer, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def calculate_score(self):
        if self.punctuality is None or self.quality is None or self.reliability is None:
            return 0
        score = (self.punctuality * 0.35) + (self.quality * 0.35) + (self.reliability * 0.30)
        return round(score)
    
    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'tax_id': self.tax_id,
            'email': self.email,
            'category_id': self.category_id,
            'is_active': self.is_active,
            'punctuality': self.punctuality,
            'quality': self.quality,
            'reliability': self.reliability,
            'score': self.calculate_score()
        }

class PurchaseRequest(db.Model):
    __tablename__ = 'purchase_requests'
    
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    category_id = db.Column(db.Integer, db.ForeignKey('categories.id'), nullable=False)
    priority = db.Column(db.String(20), nullable=False, default='medium')
    deadline = db.Column(db.DateTime, nullable=True)
    notes = db.Column(db.Text, nullable=True)
    stage_id = db.Column(db.Integer, db.ForeignKey('stages.id'), nullable=False)
    line_items = db.Column(db.JSON, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    stage = db.relationship('Stage', backref='purchase_requests')
    stage_history = db.relationship('StageHistory', backref='purchase_request', lazy='dynamic')
    
    def to_dict(self):
        return {
            'id': self.id,
            'title': self.title,
            'priority': self.priority,
            'category_id': self.category_id,
            'stage_id': self.stage_id,
            'stage_name': self.stage.name if self.stage else None,
            'created_at': self.created_at.isoformat(),
            'deadline': self.deadline.isoformat() if self.deadline else None,
            'notes': self.notes,
            'line_items': self.line_items
        }

class StageHistory(db.Model):
    __tablename__ = 'stage_history'
    
    id = db.Column(db.Integer, primary_key=True)
    purchase_request_id = db.Column(db.Integer, db.ForeignKey('purchase_requests.id'), nullable=False)
    from_stage = db.Column(db.String(50), nullable=True)
    to_stage = db.Column(db.String(50), nullable=False)
    reason = db.Column(db.String(200), nullable=True)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

class RFQ(db.Model):
    __tablename__ = 'rfqs'
    
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=True)
    purchase_request_id = db.Column(db.Integer, db.ForeignKey('purchase_requests.id'), nullable=False)
    deadline = db.Column(db.DateTime, nullable=True)
    status = db.Column(db.String(50), default='awaiting_quotes')
    winner_quote_id = db.Column(db.Integer, db.ForeignKey('quotes.id'), nullable=True)
    winner_justification = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    purchase_request = db.relationship('PurchaseRequest', backref='rfqs')
    suppliers = db.relationship('Supplier', secondary='rfq_suppliers', backref='rfqs')
    # Use foreign_keys to specify which FK to use for the relationship
    quotes = db.relationship('Quote', backref='rfq', lazy='dynamic', foreign_keys='Quote.rfq_id')
    
    def to_dict(self):
        return {
            'id': self.id,
            'title': self.title,
            'description': self.description,
            'purchase_request_id': self.purchase_request_id,
            'deadline': self.deadline.isoformat() if self.deadline else None,
            'status': self.status,
            'created_at': self.created_at.isoformat()
        }

class RFQSupplier(db.Model):
    __tablename__ = 'rfq_suppliers'
    
    rfq_id = db.Column(db.Integer, db.ForeignKey('rfqs.id'), primary_key=True)
    supplier_id = db.Column(db.Integer, db.ForeignKey('suppliers.id'), primary_key=True)

class Quote(db.Model):
    __tablename__ = 'quotes'
    
    id = db.Column(db.Integer, primary_key=True)
    rfq_id = db.Column(db.Integer, db.ForeignKey('rfqs.id'), nullable=False)
    supplier_id = db.Column(db.Integer, db.ForeignKey('suppliers.id'), nullable=False)
    token = db.Column(db.String(64), unique=True, nullable=False)
    line_items = db.Column(db.JSON, nullable=True)
    delivery_days = db.Column(db.Integer, nullable=True)
    payment_terms = db.Column(db.String(200), nullable=True)
    notes = db.Column(db.Text, nullable=True)
    status = db.Column(db.String(20), default='pending')
    revision = db.Column(db.Integer, default=0)
    submitted_at = db.Column(db.DateTime, nullable=True)
    
    supplier = db.relationship('Supplier', backref='quotes')
    
    def to_dict(self):
        return {
            'id': self.id,
            'rfq_id': self.rfq_id,
            'supplier_id': self.supplier_id,
            'token': self.token,
            'line_items': self.line_items,
            'delivery_days': self.delivery_days,
            'payment_terms': self.payment_terms,
            'notes': self.notes,
            'status': self.status,
            'revision': self.revision,
            'submitted_at': self.submitted_at.isoformat() if self.submitted_at else None
        }

class PurchaseOrder(db.Model):
    __tablename__ = 'purchase_orders'
    
    id = db.Column(db.Integer, primary_key=True)
    order_number = db.Column(db.String(50), unique=True, nullable=False)
    supplier_id = db.Column(db.Integer, db.ForeignKey('suppliers.id'), nullable=False)
    rfq_id = db.Column(db.Integer, db.ForeignKey('rfqs.id'), nullable=True)
    purchase_request_id = db.Column(db.Integer, db.ForeignKey('purchase_requests.id'), nullable=True)
    line_items = db.Column(db.JSON, nullable=False)
    total = db.Column(db.Float, nullable=False)
    payment_terms = db.Column(db.String(200), nullable=True)
    expected_delivery = db.Column(db.DateTime, nullable=False)
    status = db.Column(db.String(20), default='pending')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    supplier = db.relationship('Supplier', backref='orders')
    status_history = db.relationship('OrderStatusHistory', backref='order', lazy='dynamic')
    
    def to_dict(self):
        return {
            'id': self.id,
            'order_number': self.order_number,
            'supplier_id': self.supplier_id,
            'rfq_id': self.rfq_id,
            'purchase_request_id': self.purchase_request_id,
            'line_items': self.line_items,
            'total': self.total,
            'payment_terms': self.payment_terms,
            'expected_delivery': self.expected_delivery.isoformat(),
            'status': self.status,
            'created_at': self.created_at.isoformat()
        }

class OrderStatusHistory(db.Model):
    __tablename__ = 'order_status_history'
    
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('purchase_orders.id'), nullable=False)
    status = db.Column(db.String(20), nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
