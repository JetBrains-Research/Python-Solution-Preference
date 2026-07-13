from flask import Flask, request, jsonify, g
from functools import wraps
from database import db, init_db
from models import User, Category, Stage, Supplier, PurchaseRequest, RFQ, Quote, PurchaseOrder, StageHistory, OrderStatusHistory
from auth import login_required, admin_required
from datetime import datetime, timedelta
import jwt
import secrets
import re

app = Flask(__name__)
app.config['SECRET_KEY'] = secrets.token_hex(32)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///procurement.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# init_db called in main

# JWT configuration
JWT_EXPIRY = 3600  # 1 hour

def generate_token(user):
    payload = {
        'user_id': user.id,
        'username': user.username,
        'role': user.role,
        'exp': datetime.utcnow() + timedelta(seconds=JWT_EXPIRY)
    }
    return jwt.encode(payload, app.config['SECRET_KEY'], algorithm='HS256')

def verify_token(token):
    try:
        payload = jwt.decode(token, app.config['SECRET_KEY'], algorithms=['HS256'])
        return payload
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None

@app.before_request
def before_request():
    if request.path.startswith('/api/auth') or request.path.startswith('/api/quotes/token'):
        return
    
    auth_header = request.headers.get('Authorization')
    if not auth_header:
        return jsonify({'error': 'Authorization header required'}), 401
    
    token = auth_header.replace('Bearer ', '')
    payload = verify_token(token)
    if not payload:
        return jsonify({'error': 'Invalid or expired token'}), 401
    
    user = User.query.get(payload['user_id'])
    if not user or not user.is_active:
        return jsonify({'error': 'User not found or inactive'}), 401
    
    g.user = user

# Authentication routes
@app.route('/api/auth/login', methods=['POST'])
def login():
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')
    
    if not username or not password:
        return jsonify({'error': 'Username and password required'}), 400
    
    user = User.query.filter_by(username=username).first()
    if not user or user.password != password:
        return jsonify({'error': 'Invalid credentials'}), 401
    
    if not user.is_active:
        return jsonify({'error': 'Account is inactive'}), 403
    
    token = generate_token(user)
    return jsonify({
        'token': token,
        'user': {
            'id': user.id,
            'username': user.username,
            'role': user.role
        }
    })

# Dashboard route
@app.route('/api/dashboard', methods=['GET'])
@login_required
def dashboard():
    action_items = []
    
    # RFQs ready for review (all quotes submitted)
    ready_rfqs = RFQ.query.filter_by(status='ready_for_review').all()
    for rfq in ready_rfqs:
        action_items.append({
            'type': 'rfq_review',
            'id': rfq.id,
            'title': rfq.title,
            'description': f"RFQ {rfq.id} is ready for review"
        })
    
    # Overdue orders
    now = datetime.utcnow()
    overdue_orders = PurchaseOrder.query.filter(
        PurchaseOrder.expected_delivery < now,
        PurchaseOrder.status != 'delivered'
    ).all()
    for order in overdue_orders:
        action_items.append({
            'type': 'overdue_order',
            'id': order.id,
            'title': f"Order {order.order_number}",
            'description': f"Order {order.order_number} is overdue"
        })
    
    # Stale purchase requests (in "New" stage for more than 7 days)
    new_stage = Stage.query.filter_by(name='New').first()
    if new_stage:
        seven_days_ago = now - timedelta(days=7)
        stale_prs = PurchaseRequest.query.filter(
            PurchaseRequest.stage_id == new_stage.id,
            PurchaseRequest.created_at < seven_days_ago
        ).all()
        for pr in stale_prs:
            action_items.append({
                'type': 'stale_request',
                'id': pr.id,
                'title': pr.title,
                'description': f"Purchase request {pr.id} has been in New stage for more than 7 days"
            })
    
    return jsonify({'action_items': action_items})

# User management routes (Admin only)
@app.route('/api/users', methods=['GET'])
@login_required
@admin_required
def get_users():
    users = User.query.all()
    return jsonify({
        'users': [{
            'id': u.id,
            'username': u.username,
            'role': u.role,
            'is_active': u.is_active
        } for u in users]
    })

@app.route('/api/users', methods=['POST'])
@login_required
@admin_required
def create_user():
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')
    role = data.get('role', 'buyer')
    
    if not username or not password:
        return jsonify({'error': 'Username and password required'}), 400
    
    if role not in ['admin', 'buyer']:
        return jsonify({'error': 'Invalid role'}), 400
    
    if User.query.filter_by(username=username).first():
        return jsonify({'error': 'Username already exists'}), 400
    
    user = User(username=username, password=password, role=role)
    db.session.add(user)
    db.session.commit()
    
    return jsonify({'user': {'id': user.id, 'username': user.username, 'role': user.role, 'is_active': True}}), 201

@app.route('/api/users/<int:user_id>', methods=['GET'])
@login_required
@admin_required
def get_user(user_id):
    user = User.query.get(user_id)
    if not user:
        return jsonify({'error': 'User not found'}), 404
    
    return jsonify({
        'id': user.id,
        'username': user.username,
        'role': user.role,
        'is_active': user.is_active
    })

@app.route('/api/users/<int:user_id>', methods=['PUT'])
@login_required
@admin_required
def update_user(user_id):
    user = User.query.get(user_id)
    if not user:
        return jsonify({'error': 'User not found'}), 404
    
    data = request.get_json()
    
    # Username is immutable
    if 'username' in data:
        return jsonify({'error': 'Username cannot be changed'}), 400
    
    if 'role' in data:
        if data['role'] not in ['admin', 'buyer']:
            return jsonify({'error': 'Invalid role'}), 400
        user.role = data['role']
    
    if 'is_active' in data:
        # Cannot deactivate own account
        if data['is_active'] == False and user_id == g.user.id:
            return jsonify({'error': 'Cannot deactivate own account'}), 400
        user.is_active = data['is_active']
    
    db.session.commit()
    
    return jsonify({
        'id': user.id,
        'username': user.username,
        'role': user.role,
        'is_active': user.is_active
    })

# Category management routes (Admin only)
@app.route('/api/categories', methods=['GET'])
@login_required
def get_categories():
    categories = Category.query.all()
    return jsonify({'categories': [{'id': c.id, 'name': c.name} for c in categories]})

@app.route('/api/categories', methods=['POST'])
@login_required
@admin_required
def create_category():
    data = request.get_json()
    name = data.get('name')
    
    if not name:
        return jsonify({'error': 'Category name required'}), 400
    
    if Category.query.filter_by(name=name).first():
        return jsonify({'error': 'Category already exists'}), 400
    
    category = Category(name=name)
    db.session.add(category)
    db.session.commit()
    
    return jsonify({'id': category.id, 'name': category.name}), 201

@app.route('/api/categories/<int:category_id>', methods=['PUT'])
@login_required
@admin_required
def update_category(category_id):
    category = Category.query.get(category_id)
    if not category:
        return jsonify({'error': 'Category not found'}), 404
    
    data = request.get_json()
    name = data.get('name')
    
    if name:
        if Category.query.filter_by(name=name).first() and name != category.name:
            return jsonify({'error': 'Category name already exists'}), 400
        category.name = name
    
    db.session.commit()
    
    return jsonify({'id': category.id, 'name': category.name})

@app.route('/api/categories/<int:category_id>', methods=['DELETE'])
@login_required
@admin_required
def delete_category(category_id):
    category = Category.query.get(category_id)
    if not category:
        return jsonify({'error': 'Category not found'}), 404
    
    # Check if category is used by any purchase request or supplier
    pr_count = PurchaseRequest.query.filter_by(category_id=category_id).count()
    supplier_count = Supplier.query.filter_by(category_id=category_id).count()
    
    if pr_count > 0 or supplier_count > 0:
        return jsonify({'error': 'Cannot delete category in use'}), 400
    
    db.session.delete(category)
    db.session.commit()
    
    return jsonify({'message': 'Category deleted'})

# Stage management routes (Admin only)
@app.route('/api/stages', methods=['GET'])
@login_required
def get_stages():
    stages = Stage.query.order_by(Stage.order).all()
    return jsonify({
        'stages': [{
            'id': s.id,
            'name': s.name,
            'color': s.color,
            'order': s.order
        } for s in stages]
    })

@app.route('/api/stages', methods=['POST'])
@login_required
@admin_required
def create_stage():
    data = request.get_json()
    name = data.get('name')
    color = data.get('color', '#6c757d')
    
    if not name:
        return jsonify({'error': 'Stage name required'}), 400
    
    if Stage.query.filter_by(name=name).first():
        return jsonify({'error': 'Stage already exists'}), 400
    
    # Get max order
    max_order = db.session.query(db.func.max(Stage.order)).scalar() or 0
    
    stage = Stage(name=name, color=color, order=max_order + 1)
    db.session.add(stage)
    db.session.commit()
    
    return jsonify({'id': stage.id, 'name': stage.name, 'color': stage.color, 'order': stage.order}), 201

@app.route('/api/stages/<int:stage_id>', methods=['PUT'])
@login_required
@admin_required
def update_stage(stage_id):
    stage = Stage.query.get(stage_id)
    if not stage:
        return jsonify({'error': 'Stage not found'}), 404
    
    data = request.get_json()
    
    if 'name' in data:
        if Stage.query.filter_by(name=data['name']).first() and data['name'] != stage.name:
            return jsonify({'error': 'Stage name already exists'}), 400
        stage.name = data['name']
    
    if 'color' in data:
        stage.color = data['color']
    
    if 'order' in data:
        # Reorder stages
        stages = Stage.query.all()
        for s in stages:
            if s.id != stage_id:
                s.order = data['order'] if s.order > stage.order else s.order
        stage.order = data['order']
    
    db.session.commit()
    
    return jsonify({'id': stage.id, 'name': stage.name, 'color': stage.color, 'order': stage.order})

@app.route('/api/stages/<int:stage_id>', methods=['DELETE'])
@login_required
@admin_required
def delete_stage(stage_id):
    stage = Stage.query.get(stage_id)
    if not stage:
        return jsonify({'error': 'Stage not found'}), 404
    
    # Check if stage has any requests
    pr_count = PurchaseRequest.query.filter_by(stage_id=stage_id).count()
    if pr_count > 0:
        return jsonify({'error': 'Cannot delete stage with requests'}), 400
    
    db.session.delete(stage)
    db.session.commit()
    
    return jsonify({'message': 'Stage deleted'})

# Supplier management routes
@app.route('/api/suppliers', methods=['GET'])
@login_required
def get_suppliers():
    suppliers = Supplier.query.filter_by(is_active=True).all()
    
    # Search
    search = request.args.get('search', '')
    if search:
        suppliers = Supplier.query.filter(
            (Supplier.name.ilike(f'%{search}%')) |
            (Supplier.email.ilike(f'%{search}%'))
        ).filter_by(is_active=True).all()
    
    # Filter by status
    status = request.args.get('status')
    if status:
        suppliers = Supplier.query.filter_by(is_active=(status == 'active')).all()
    
    # Filter by category
    category_id = request.args.get('category_id')
    if category_id:
        suppliers = Supplier.query.filter_by(category_id=int(category_id)).all()
    
    # Sort
    sort_by = request.args.get('sort', 'name')
    if sort_by == 'score':
        suppliers = sorted(suppliers, key=lambda s: s.calculate_score(), reverse=True)
    elif sort_by == 'name':
        suppliers = sorted(suppliers, key=lambda s: s.name)
    
    return jsonify({
        'suppliers': [{
            'id': s.id,
            'name': s.name,
            'tax_id': s.tax_id,
            'email': s.email,
            'category_id': s.category_id,
            'is_active': s.is_active,
            'punctuality': s.punctuality,
            'quality': s.quality,
            'reliability': s.reliability,
            'score': s.calculate_score()
        } for s in suppliers]
    })

@app.route('/api/suppliers', methods=['POST'])
@login_required
def create_supplier():
    data = request.get_json()
    name = data.get('name')
    tax_id = data.get('tax_id')
    email = data.get('email')
    category_id = data.get('category_id')
    
    if not name or not tax_id or not email or not category_id:
        return jsonify({'error': 'Name, tax_id, email, and category_id required'}), 400
    
    if Supplier.query.filter_by(tax_id=tax_id).first():
        return jsonify({'error': 'Tax ID already exists'}), 400
    
    if Supplier.query.filter_by(email=email).first():
        return jsonify({'error': 'Email already exists'}), 400
    
    category = Category.query.get(category_id)
    if not category:
        return jsonify({'error': 'Category not found'}), 400
    
    supplier = Supplier(name=name, tax_id=tax_id, email=email, category_id=category_id)
    db.session.add(supplier)
    db.session.commit()
    
    return jsonify({
        'id': supplier.id,
        'name': supplier.name,
        'tax_id': supplier.tax_id,
        'email': supplier.email,
        'category_id': supplier.category_id,
        'is_active': True,
        'punctuality': None,
        'quality': None,
        'reliability': None,
        'score': 0
    }), 201

@app.route('/api/suppliers/<int:supplier_id>', methods=['GET'])
@login_required
def get_supplier(supplier_id):
    supplier = Supplier.query.get(supplier_id)
    if not supplier:
        return jsonify({'error': 'Supplier not found'}), 404
    
    return jsonify({
        'id': supplier.id,
        'name': supplier.name,
        'tax_id': supplier.tax_id,
        'email': supplier.email,
        'category_id': supplier.category_id,
        'is_active': supplier.is_active,
        'punctuality': supplier.punctuality,
        'quality': supplier.quality,
        'reliability': supplier.reliability,
        'score': supplier.calculate_score()
    })

@app.route('/api/suppliers/<int:supplier_id>', methods=['PUT'])
@login_required
def update_supplier(supplier_id):
    supplier = Supplier.query.get(supplier_id)
    if not supplier:
        return jsonify({'error': 'Supplier not found'}), 404
    
    data = request.get_json()
    
    if 'name' in data:
        supplier.name = data['name']
    
    if 'email' in data:
        if Supplier.query.filter_by(email=data['email']).first() and data['email'] != supplier.email:
            return jsonify({'error': 'Email already exists'}), 400
        supplier.email = data['email']
    
    if 'category_id' in data:
        category = Category.query.get(data['category_id'])
        if not category:
            return jsonify({'error': 'Category not found'}), 400
        supplier.category_id = data['category_id']
    
    if 'is_active' in data:
        # Cannot deactivate if invited to active RFQ
        if not data['is_active']:
            active_rfqs = RFQ.query.filter(
                RFQ.suppliers.any(Supplier.id == supplier_id),
                RFQ.status.in_(['awaiting_quotes', 'ready_for_review'])
            ).first()
            if active_rfqs:
                return jsonify({'error': 'Cannot deactivate supplier with active RFQ'}), 400
        supplier.is_active = data['is_active']
    
    db.session.commit()
    
    return jsonify({
        'id': supplier.id,
        'name': supplier.name,
        'tax_id': supplier.tax_id,
        'email': supplier.email,
        'category_id': supplier.category_id,
        'is_active': supplier.is_active,
        'punctuality': supplier.punctuality,
        'quality': supplier.quality,
        'reliability': supplier.reliability,
        'score': supplier.calculate_score()
    })

@app.route('/api/suppliers/<int:supplier_id>', methods=['DELETE'])
@login_required
def delete_supplier(supplier_id):
    supplier = Supplier.query.get(supplier_id)
    if not supplier:
        return jsonify({'error': 'Supplier not found'}), 404
    
    # Check if supplier has RFQs or orders
    rfq_count = RFQ.query.filter(RFQ.suppliers.any(Supplier.id == supplier_id)).count()
    order_count = PurchaseOrder.query.filter_by(supplier_id=supplier_id).count()
    
    if rfq_count > 0 or order_count > 0:
        return jsonify({'error': 'Cannot delete supplier with existing RFQs or orders'}), 400
    
    db.session.delete(supplier)
    db.session.commit()
    
    return jsonify({'message': 'Supplier deleted'})

@app.route('/api/suppliers/<int:supplier_id>/rate', methods=['POST'])
@login_required
def rate_supplier(supplier_id):
    supplier = Supplier.query.get(supplier_id)
    if not supplier:
        return jsonify({'error': 'Supplier not found'}), 404
    
    data = request.get_json()
    punctuality = data.get('punctuality')
    quality = data.get('quality')
    reliability = data.get('reliability')
    
    if punctuality is not None:
        if not 0 <= punctuality <= 100:
            return jsonify({'error': 'Punctuality must be 0-100'}), 400
        supplier.punctuality = punctuality
    
    if quality is not None:
        if not 0 <= quality <= 100:
            return jsonify({'error': 'Quality must be 0-100'}), 400
        supplier.quality = quality
    
    if reliability is not None:
        if not 0 <= reliability <= 100:
            return jsonify({'error': 'Reliability must be 0-100'}), 400
        supplier.reliability = reliability
    
    db.session.commit()
    
    return jsonify({
        'id': supplier.id,
        'punctuality': supplier.punctuality,
        'quality': supplier.quality,
        'reliability': supplier.reliability,
        'score': supplier.calculate_score()
    })

# Purchase Request routes
@app.route('/api/purchase-requests', methods=['GET'])
@login_required
def get_purchase_requests():
    prs = PurchaseRequest.query.all()
    
    # Search
    search = request.args.get('search', '')
    if search:
        prs = PurchaseRequest.query.filter(
            (PurchaseRequest.title.ilike(f'%{search}%')) |
            (PurchaseRequest.notes.ilike(f'%{search}%'))
        ).all()
    
    # Filter by category
    category_id = request.args.get('category_id')
    if category_id:
        prs = PurchaseRequest.query.filter_by(category_id=int(category_id)).all()
    
    # Filter by priority
    priority = request.args.get('priority')
    if priority:
        prs = PurchaseRequest.query.filter_by(priority=priority).all()
    
    return jsonify({
        'purchase_requests': [{
            'id': pr.id,
            'title': pr.title,
            'priority': pr.priority,
            'category_id': pr.category_id,
            'stage_id': pr.stage_id,
            'stage_name': pr.stage.name,
            'created_at': pr.created_at.isoformat(),
            'deadline': pr.deadline.isoformat() if pr.deadline else None,
            'item_count': len(pr.line_items)
        } for pr in prs]
    })

@app.route('/api/purchase-requests', methods=['POST'])
@login_required
def create_purchase_request():
    data = request.get_json()
    title = data.get('title')
    category_id = data.get('category_id')
    priority = data.get('priority', 'medium')
    deadline = data.get('deadline')
    notes = data.get('notes')
    line_items = data.get('line_items', [])
    
    if not title or not line_items:
        return jsonify({'error': 'Title and at least one line item required'}), 400
    
    if priority not in ['low', 'medium', 'high', 'urgent']:
        return jsonify({'error': 'Invalid priority'}), 400
    
    category = Category.query.get(category_id)
    if not category:
        return jsonify({'error': 'Category not found'}), 400
    
    # Get default stage (New)
    default_stage = Stage.query.filter_by(name='New').first()
    if not default_stage:
        return jsonify({'error': 'Default stage not found'}), 500
    
    for item in line_items:
        if item.get('quantity', 0) < 1:
            return jsonify({'error': 'Line item quantity must be at least 1'}), 400
    
    pr = PurchaseRequest(
        title=title,
        category_id=category_id,
        priority=priority,
        deadline=datetime.fromisoformat(deadline) if deadline else None,
        notes=notes,
        stage_id=default_stage.id,
        line_items=line_items
    )
    db.session.add(pr)
    db.session.commit()
    
    return jsonify({
        'id': pr.id,
        'title': pr.title,
        'priority': pr.priority,
        'category_id': pr.category_id,
        'stage_id': pr.stage_id,
        'stage_name': pr.stage.name,
        'created_at': pr.created_at.isoformat(),
        'deadline': pr.deadline.isoformat() if pr.deadline else None,
        'notes': pr.notes,
        'line_items': pr.line_items
    }), 201

@app.route('/api/purchase-requests/<int:pr_id>', methods=['GET'])
@login_required
def get_purchase_request(pr_id):
    pr = PurchaseRequest.query.get(pr_id)
    if not pr:
        return jsonify({'error': 'Purchase request not found'}), 404
    
    return jsonify({
        'id': pr.id,
        'title': pr.title,
        'priority': pr.priority,
        'category_id': pr.category_id,
        'stage_id': pr.stage_id,
        'stage_name': pr.stage.name,
        'created_at': pr.created_at.isoformat(),
        'deadline': pr.deadline.isoformat() if pr.deadline else None,
        'notes': pr.notes,
        'line_items': pr.line_items,
        'stage_history': [{
            'from_stage': h.from_stage,
            'to_stage': h.to_stage,
            'timestamp': h.timestamp.isoformat(),
            'reason': h.reason
        } for h in pr.stage_history]
    })

@app.route('/api/purchase-requests/<int:pr_id>', methods=['PUT'])
@login_required
def update_purchase_request(pr_id):
    pr = PurchaseRequest.query.get(pr_id)
    if not pr:
        return jsonify({'error': 'Purchase request not found'}), 404
    
    data = request.get_json()
    
    # Check if RFQ exists
    existing_rfq = RFQ.query.filter_by(purchase_request_id=pr_id, status='cancelled').first()
    if existing_rfq and existing_rfq.status != 'cancelled':
        return jsonify({'error': 'Cannot edit request with active RFQ'}), 400
    
    if 'title' in data:
        pr.title = data['title']
    
    if 'priority' in data:
        if data['priority'] not in ['low', 'medium', 'high', 'urgent']:
            return jsonify({'error': 'Invalid priority'}), 400
        pr.priority = data['priority']
    
    if 'category_id' in data:
        category = Category.query.get(data['category_id'])
        if not category:
            return jsonify({'error': 'Category not found'}), 400
        pr.category_id = data['category_id']
    
    if 'deadline' in data:
        pr.deadline = datetime.fromisoformat(data['deadline']) if data['deadline'] else None
    
    if 'notes' in data:
        pr.notes = data['notes']
    
    if 'line_items' in data:
        for item in data['line_items']:
            if item.get('quantity', 0) < 1:
                return jsonify({'error': 'Line item quantity must be at least 1'}), 400
        pr.line_items = data['line_items']
    
    db.session.commit()
    
    return jsonify({
        'id': pr.id,
        'title': pr.title,
        'priority': pr.priority,
        'category_id': pr.category_id,
        'stage_id': pr.stage_id,
        'stage_name': pr.stage.name,
        'created_at': pr.created_at.isoformat(),
        'deadline': pr.deadline.isoformat() if pr.deadline else None,
        'notes': pr.notes,
        'line_items': pr.line_items
    })

@app.route('/api/purchase-requests/<int:pr_id>', methods=['DELETE'])
@login_required
def delete_purchase_request(pr_id):
    pr = PurchaseRequest.query.get(pr_id)
    if not pr:
        return jsonify({'error': 'Purchase request not found'}), 404
    
    # Check if RFQ exists
    existing_rfq = RFQ.query.filter_by(purchase_request_id=pr_id).first()
    if existing_rfq:
        return jsonify({'error': 'Cannot delete request with existing RFQ'}), 400
    
    db.session.delete(pr)
    db.session.commit()
    
    return jsonify({'message': 'Purchase request deleted'})

@app.route('/api/purchase-requests/<int:pr_id>/move', methods=['POST'])
@login_required
def move_purchase_request(pr_id):
    pr = PurchaseRequest.query.get(pr_id)
    if not pr:
        return jsonify({'error': 'Purchase request not found'}), 404
    
    data = request.get_json()
    stage_id = data.get('stage_id')
    reason = data.get('reason', '')
    
    stage = Stage.query.get(stage_id)
    if not stage:
        return jsonify({'error': 'Stage not found'}), 404
    
    old_stage = pr.stage.name
    pr.stage_id = stage_id
    
    # Record stage history
    history = StageHistory(
        purchase_request_id=pr_id,
        from_stage=old_stage,
        to_stage=stage.name,
        reason=reason
    )
    db.session.add(history)
    db.session.commit()
    
    return jsonify({
        'id': pr.id,
        'stage_id': pr.stage_id,
        'stage_name': pr.stage.name
    })

@app.route('/api/purchase-requests/<int:pr_id>/clone', methods=['POST'])
@login_required
def clone_purchase_request(pr_id):
    pr = PurchaseRequest.query.get(pr_id)
    if not pr:
        return jsonify({'error': 'Purchase request not found'}), 404
    
    default_stage = Stage.query.filter_by(name='New').first()
    if not default_stage:
        return jsonify({'error': 'Default stage not found'}), 500
    
    new_pr = PurchaseRequest(
        title=pr.title + ' (Copy)',
        category_id=pr.category_id,
        priority=pr.priority,
        deadline=pr.deadline,
        notes=pr.notes,
        stage_id=default_stage.id,
        line_items=pr.line_items
    )
    db.session.add(new_pr)
    db.session.commit()
    
    return jsonify({
        'id': new_pr.id,
        'title': new_pr.title,
        'priority': new_pr.priority,
        'category_id': new_pr.category_id,
        'stage_id': new_pr.stage_id,
        'stage_name': new_pr.stage.name,
        'line_items': new_pr.line_items
    }), 201

# RFQ routes
@app.route('/api/rfqs', methods=['GET'])
@login_required
def get_rfqs():
    rfqs = RFQ.query.all()
    return jsonify({
        'rfqs': [{
            'id': r.id,
            'title': r.title,
            'purchase_request_id': r.purchase_request_id,
            'status': r.status,
            'deadline': r.deadline.isoformat() if r.deadline else None,
            'created_at': r.created_at.isoformat()
        } for r in rfqs]
    })

@app.route('/api/rfqs', methods=['POST'])
@login_required
def create_rfq():
    data = request.get_json()
    title = data.get('title')
    purchase_request_id = data.get('purchase_request_id')
    description = data.get('description')
    deadline = data.get('deadline')
    supplier_ids = data.get('supplier_ids', [])
    include_all_active = data.get('include_all_active', False)
    
    if not title or not purchase_request_id:
        return jsonify({'error': 'Title and purchase_request_id required'}), 400
    
    pr = PurchaseRequest.query.get(purchase_request_id)
    if not pr:
        return jsonify({'error': 'Purchase request not found'}), 400
    
    # Check if PR already has active RFQ
    existing_rfq = RFQ.query.filter_by(purchase_request_id=purchase_request_id).first()
    if existing_rfq and existing_rfq.status not in ['cancelled', 'winner_selected']:
        return jsonify({'error': 'Purchase request already has an active RFQ'}), 400
    
    # Move PR to In Review stage
    in_review_stage = Stage.query.filter_by(name='In Review').first()
    if in_review_stage and pr.stage_id != in_review_stage.id:
        old_stage = pr.stage.name
        pr.stage_id = in_review_stage.id
        history = StageHistory(
            purchase_request_id=pr_id,
            from_stage=old_stage,
            to_stage='In Review',
            reason='RFQ published'
        )
        db.session.add(history)
    
    # Get suppliers
    suppliers = []
    if include_all_active:
        suppliers = Supplier.query.filter_by(is_active=True).all()
    else:
        if supplier_ids:
            suppliers = Supplier.query.filter(Supplier.id.in_(supplier_ids)).filter_by(is_active=True).all()
        else:
            # Default to suppliers in PR category
            suppliers = Supplier.query.filter_by(category_id=pr.category_id, is_active=True).all()
    
    rfq = RFQ(
        title=title,
        purchase_request_id=pr_id,
        description=description,
        deadline=datetime.fromisoformat(deadline) if deadline else None,
        status='awaiting_quotes',
        suppliers=suppliers
    )
    db.session.add(rfq)
    db.session.commit()
    
    # Generate quote tokens for each supplier
    for supplier in suppliers:
        token = secrets.token_urlsafe(32)
        quote = Quote(
            rfq_id=rfq.id,
            supplier_id=supplier.id,
            token=token,
            status='pending'
        )
        db.session.add(quote)
    
    db.session.commit()
    
    return jsonify({
        'id': rfq.id,
        'title': rfq.title,
        'purchase_request_id': rfq.purchase_request_id,
        'status': rfq.status,
        'deadline': rfq.deadline.isoformat() if rfq.deadline else None,
        'supplier_count': len(suppliers)
    }), 201

@app.route('/api/rfqs/<int:rfq_id>', methods=['GET'])
@login_required
def get_rfq(rfq_id):
    rfq = RFQ.query.get(rfq_id)
    if not rfq:
        return jsonify({'error': 'RFQ not found'}), 404
    
    return jsonify({
        'id': rfq.id,
        'title': rfq.title,
        'description': rfq.description,
        'purchase_request_id': rfq.purchase_request_id,
        'status': rfq.status,
        'deadline': rfq.deadline.isoformat() if rfq.deadline else None,
        'created_at': rfq.created_at.isoformat(),
        'suppliers': [{
            'id': s.id,
            'name': s.name,
            'email': s.email
        } for s in rfq.suppliers],
        'quotes': [{
            'id': q.id,
            'supplier_id': q.supplier_id,
            'supplier_name': q.supplier.name,
            'status': q.status,
            'line_items': q.line_items,
            'delivery_days': q.delivery_days,
            'payment_terms': q.payment_terms,
            'notes': q.notes,
            'revision': q.revision,
            'token': q.token,
            'submitted_at': q.submitted_at.isoformat() if q.submitted_at else None
        } for q in rfq.quotes]
    })

@app.route('/api/rfqs/<int:rfq_id>', methods=['PUT'])
@login_required
def update_rfq(rfq_id):
    rfq = RFQ.query.get(rfq_id)
    if not rfq:
        return jsonify({'error': 'RFQ not found'}), 404
    
    data = request.get_json()
    
    # Check if locked
    if rfq.status in ['winner_selected', 'cancelled']:
        return jsonify({'error': 'RFQ is locked'}), 400
    
    # Check if quotes exist
    has_quotes = any(q.status == 'submitted' for q in rfq.quotes)
    
    if rfq.status == 'awaiting_quotes':
        if has_quotes:
            # Only allow deadline extension
            if 'deadline' not in data:
                return jsonify({'error': 'Only deadline can be extended after quotes received'}), 400
        else:
            # Can edit all fields
            if 'title' in data:
                rfq.title = data['title']
            if 'description' in data:
                rfq.description = data['description']
            if 'deadline' in data:
                rfq.deadline = datetime.fromisoformat(data['deadline']) if data['deadline'] else None
    
    elif rfq.status == 'ready_for_review':
        # Only can select winner or cancel
        pass
    
    elif rfq.status == 'overdue':
        # Only can select winner or cancel
        pass
    
    if 'deadline' in data:
        rfq.deadline = datetime.fromisoformat(data['deadline']) if data['deadline'] else None
    
    db.session.commit()
    
    return jsonify({
        'id': rfq.id,
        'title': rfq.title,
        'description': rfq.description,
        'deadline': rfq.deadline.isoformat() if rfq.deadline else None,
        'status': rfq.status
    })

@app.route('/api/rfqs/<int:rfq_id>/cancel', methods=['POST'])
@login_required
def cancel_rfq(rfq_id):
    rfq = RFQ.query.get(rfq_id)
    if not rfq:
        return jsonify({'error': 'RFQ not found'}), 404
    
    if rfq.status in ['winner_selected', 'cancelled']:
        return jsonify({'error': 'Cannot cancel RFQ in current status'}), 400
    
    rfq.status = 'cancelled'
    
    # Move PR back to New stage
    pr = PurchaseRequest.query.get(rfq.purchase_request_id)
    if pr:
        new_stage = Stage.query.filter_by(name='New').first()
        if new_stage and pr.stage_id != new_stage.id:
            old_stage = pr.stage.name
            pr.stage_id = new_stage.id
            history = StageHistory(
                purchase_request_id=pr.id,
                from_stage=old_stage,
                to_stage='New',
                reason='RFQ cancelled'
            )
            db.session.add(history)
    
    db.session.commit()
    
    return jsonify({'id': rfq.id, 'status': rfq.status})

@app.route('/api/rfqs/<int:rfq_id>/compare', methods=['GET'])
@login_required
def compare_quotes(rfq_id):
    rfq = RFQ.query.get(rfq_id)
    if not rfq:
        return jsonify({'error': 'RFQ not found'}), 404
    
    if rfq.status not in ['ready_for_review', 'overdue']:
        return jsonify({'error': 'RFQ not ready for comparison'}), 400
    
    comparisons = []
    lowest_total = float('inf')
    
    for quote in rfq.quotes:
        if quote.status != 'submitted':
            continue
        
        total = sum(item['quantity'] * item['unit_price'] for item in quote.line_items)
        is_lowest = total < lowest_total
        if is_lowest:
            lowest_total = total
        
        comparisons.append({
            'id': quote.id,
            'supplier_id': quote.supplier_id,
            'supplier_name': quote.supplier.name,
            'supplier_score': quote.supplier.calculate_score(),
            'line_items': quote.line_items,
            'total': total,
            'delivery_days': quote.delivery_days,
            'payment_terms': quote.payment_terms,
            'is_lowest': is_lowest
        })
    
    return jsonify({
        'rfq_id': rfq_id,
        'comparisons': comparisons,
        'lowest_total': lowest_total
    })

@app.route('/api/rfqs/<int:rfq_id>/select-winner', methods=['POST'])
@login_required
def select_winner(rfq_id):
    rfq = RFQ.query.get(rfq_id)
    if not rfq:
        return jsonify({'error': 'RFQ not found'}), 404
    
    if rfq.status not in ['ready_for_review', 'overdue']:
        return jsonify({'error': 'Cannot select winner in current status'}), 400
    
    data = request.get_json()
    quote_id = data.get('quote_id')
    justification = data.get('justification', '')
    
    quote = Quote.query.get(quote_id)
    if not quote or quote.rfq_id != rfq_id:
        return jsonify({'error': 'Quote not found'}), 404
    
    if quote.status != 'submitted':
        return jsonify({'error': 'Quote not submitted'}), 400
    
    # Check if lowest priced
    lowest_total = float('inf')
    for q in rfq.quotes:
        if q.status == 'submitted':
            total = sum(item['quantity'] * item['unit_price'] for item in q.line_items)
            if total < lowest_total:
                lowest_total = total
    
    quote_total = sum(item['quantity'] * item['unit_price'] for item in quote.line_items)
    if quote_total != lowest_total and not justification:
        return jsonify({'error': 'Justification required for non-lowest quote'}), 400
    
    rfq.status = 'winner_selected'
    rfq.winner_quote_id = quote_id
    rfq.winner_justification = justification
    
    # Move PR to Approved stage
    pr = PurchaseRequest.query.get(rfq.purchase_request_id)
    if pr:
        approved_stage = Stage.query.filter_by(name='Approved').first()
        if approved_stage and pr.stage_id != approved_stage.id:
            old_stage = pr.stage.name
            pr.stage_id = approved_stage.id
            history = StageHistory(
                purchase_request_id=pr.id,
                from_stage=old_stage,
                to_stage='Approved',
                reason='RFQ winner selected'
            )
            db.session.add(history)
    
    # Auto-create purchase order
    order_number = f"PO-{rfq.id}-{datetime.utcnow().year}"
    expected_delivery = datetime.utcnow() + timedelta(days=quote.delivery_days)
    
    order = PurchaseOrder(
        order_number=order_number,
        supplier_id=quote.supplier_id,
        rfq_id=rfq_id,
        purchase_request_id=pr.id,
        line_items=quote.line_items,
        total=quote_total,
        payment_terms=quote.payment_terms,
        expected_delivery=expected_delivery,
        status='pending'
    )
    db.session.add(order)
    
    # Move PR to Ordered stage
    ordered_stage = Stage.query.filter_by(name='Ordered').first()
    if ordered_stage and pr.stage_id != ordered_stage.id:
        old_stage = pr.stage.name
        pr.stage_id = ordered_stage.id
        history = StageHistory(
            purchase_request_id=pr.id,
            from_stage=old_stage,
            to_stage='Ordered',
            reason='Purchase order created'
        )
        db.session.add(history)
    
    db.session.commit()
    
    return jsonify({
        'rfq_id': rfq_id,
        'winner_quote_id': quote_id,
        'order_id': order.id,
        'order_number': order.order_number
    })

# Quote routes (supplier-facing, no login)
@app.route('/api/quotes/token/<token>', methods=['GET'])
def get_quote_by_token(token):
    quote = Quote.query.filter_by(token=token).first()
    if not quote:
        return jsonify({'error': 'Invalid token'}), 404
    
    rfq = RFQ.query.get(quote.rfq_id)
    if not rfq:
        return jsonify({'error': 'RFQ not found'}), 404
    
    # Get line items from purchase request
    pr = PurchaseRequest.query.get(rfq.purchase_request_id)
    if not pr:
        return jsonify({'error': 'Purchase request not found'}), 404
    
    return jsonify({
        'quote_id': quote.id,
        'token': token,
        'rfq_title': rfq.title,
        'description': rfq.description,
        'deadline': rfq.deadline.isoformat() if rfq.deadline else None,
        'supplier_name': quote.supplier.name,
        'line_items': pr.line_items,
        'status': quote.status,
        'revision': quote.revision
    })

@app.route('/api/quotes/token/<token>', methods=['POST'])
def submit_quote(token):
    quote = Quote.query.filter_by(token=token).first()
    if not quote:
        return jsonify({'error': 'Invalid token'}), 404
    
    rfq = RFQ.query.get(quote.rfq_id)
    if not rfq:
        return jsonify({'error': 'RFQ not found'}), 404
    
    # Check if submission is blocked
    if rfq.status in ['winner_selected', 'cancelled']:
        return jsonify({'error': 'RFQ is closed'}), 400
    
    if rfq.deadline and datetime.utcnow() > rfq.deadline:
        return jsonify({'error': 'Quote deadline has passed'}), 400
    
    data = request.get_json()
    line_items = data.get('line_items', [])
    delivery_days = data.get('delivery_days')
    payment_terms = data.get('payment_terms')
    notes = data.get('notes')
    
    if not line_items or not delivery_days or not payment_terms:
        return jsonify({'error': 'Line items, delivery days, and payment terms required'}), 400
    
    if delivery_days < 1:
        return jsonify({'error': 'Delivery days must be at least 1'}), 400
    
    # Validate line items
    pr = PurchaseRequest.query.get(rfq.purchase_request_id)
    if not pr:
        return jsonify({'error': 'Purchase request not found'}), 400
    
    for item in line_items:
        if item.get('unit_price', 0) <= 0:
            return jsonify({'error': 'Unit price must be positive'}), 400
    
    quote.line_items = line_items
    quote.delivery_days = delivery_days
    quote.payment_terms = payment_terms
    quote.notes = notes
    quote.status = 'submitted'
    quote.revision = (quote.revision or 0) + 1
    quote.submitted_at = datetime.utcnow()
    
    db.session.commit()
    
    # Check if all suppliers have responded
    all_submitted = all(q.status == 'submitted' for q in rfq.quotes)
    if all_submitted and rfq.status == 'awaiting_quotes':
        rfq.status = 'ready_for_review'
        db.session.commit()
    
    return jsonify({
        'quote_id': quote.id,
        'reference_number': f"QRF-{quote.id}",
        'revision': quote.revision
    })

# Purchase Order routes
@app.route('/api/orders', methods=['GET'])
@login_required
def get_orders():
    orders = PurchaseOrder.query.all()
    return jsonify({
        'orders': [{
            'id': o.id,
            'order_number': o.order_number,
            'supplier_id': o.supplier_id,
            'supplier_name': o.supplier.name,
            'status': o.status,
            'total': o.total,
            'expected_delivery': o.expected_delivery.isoformat(),
            'created_at': o.created_at.isoformat()
        } for o in orders]
    })

@app.route('/api/orders/<int:order_id>', methods=['GET'])
@login_required
def get_order(order_id):
    order = PurchaseOrder.query.get(order_id)
    if not order:
        return jsonify({'error': 'Order not found'}), 404
    
    return jsonify({
        'id': order.id,
        'order_number': order.order_number,
        'supplier_id': order.supplier_id,
        'supplier_name': order.supplier.name,
        'rfq_id': order.rfq_id,
        'purchase_request_id': order.purchase_request_id,
        'line_items': order.line_items,
        'total': order.total,
        'payment_terms': order.payment_terms,
        'expected_delivery': order.expected_delivery.isoformat(),
        'status': order.status,
        'created_at': order.created_at.isoformat(),
        'status_history': [{
            'status': h.status,
            'timestamp': h.timestamp.isoformat()
        } for h in order.status_history]
    })

@app.route('/api/orders/<int:order_id>/status', methods=['POST'])
@login_required
def update_order_status(order_id):
    order = PurchaseOrder.query.get(order_id)
    if not order:
        return jsonify({'error': 'Order not found'}), 404
    
    data = request.get_json()
    new_status = data.get('status')
    
    valid_progression = ['pending', 'confirmed', 'shipped', 'delivered']
    current_idx = valid_progression.index(order.status) if order.status in valid_progression else -1
    
    if new_status not in valid_progression:
        return jsonify({'error': 'Invalid status'}), 400
    
    new_idx = valid_progression.index(new_status)
    if new_idx <= current_idx:
        return jsonify({'error': 'Status can only move forward'}), 400
    
    old_status = order.status
    order.status = new_status
    
    # Record status history
    history = OrderStatusHistory(order_id=order_id, status=new_status)
    db.session.add(history)
    
    # If delivered, allow rating supplier (but don't auto-rate)
    
    db.session.commit()
    
    return jsonify({
        'id': order.id,
        'status': order.status
    })

@app.route('/api/orders/<int:order_id>/reorder', methods=['POST'])
@login_required
def reorder(order_id):
    order = PurchaseOrder.query.get(order_id)
    if not order:
        return jsonify({'error': 'Order not found'}), 404
    
    default_stage = Stage.query.filter_by(name='New').first()
    if not default_stage:
        return jsonify({'error': 'Default stage not found'}), 500
    
    pr = PurchaseRequest(
        title=f"Re-order: {order.order_number}",
        category_id=order.supplier.category_id,
        priority='medium',
        deadline=None,
        notes=f"Re-order from {order.order_number}",
        stage_id=default_stage.id,
        line_items=order.line_items
    )
    db.session.add(pr)
    db.session.commit()
    
    return jsonify({
        'id': pr.id,
        'title': pr.title,
        'line_items': pr.line_items
    }), 201


if __name__ == '__main__':
    with app.app_context():
        init_db(app)
    app.run(debug=True, host='0.0.0.0', port=12345)
