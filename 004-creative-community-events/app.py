import os
from flask import Flask, request, jsonify
from functools import wraps
from werkzeug.security import generate_password_hash, check_password_hash
import jwt
from datetime import datetime, timezone, timedelta
from config import Config
from models import db, User, InviteCode, CodeUsage, Event, Attendance

app = Flask(__name__)
app.config.from_object(Config)
db.init_app(app)

JWT_SECRET = app.config['SECRET_KEY']
JWT_ALGORITHM = 'HS256'

# ===========================================
# Helpers
# ===========================================

def token_for(user):
    payload = {
        'user_id': user.id,
        'exp': datetime.utcnow() + timedelta(hours=24)
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)

def get_current_user():
    token = request.headers.get('Authorization', '').replace('Bearer ', '')
    if not token:
        return None
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        user_id = payload.get('user_id')
        if user_id:
            return db.session.get(User, user_id)
    except jwt.ExpiredSignatureError:
        pass
    except jwt.InvalidTokenError:
        pass
    return None

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        user = get_current_user()
        if not user:
            return jsonify({'error': 'Authentication required'}), 401
        return f(user, *args, **kwargs)
    return decorated

def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        user = get_current_user()
        if not user:
            return jsonify({'error': 'Authentication required'}), 401
        if not user.is_admin:
            return jsonify({'error': 'Admin privileges required'}), 403
        return f(user, *args, **kwargs)
    return decorated

def profile_complete_required(f):
    @wraps(f)
    def decorated(user, *args, **kwargs):
        if not user.profile_complete:
            return jsonify({'error': 'Profile must be completed before this action'}), 400
        return f(user, *args, **kwargs)
    return decorated

# ===========================================
# Auth routes
# ===========================================

@app.route('/auth/register', methods=['POST'])
def register():
    data = request.get_json()
    if not data:
        return jsonify({'error': 'No data provided'}), 400

    username = data.get('username', '').strip()
    email = data.get('email', '').strip()
    password = data.get('password', '')
    invite_code = data.get('invite_code', '').strip()

    errors = []
    if not username:
        errors.append('Username is required')
    if not email:
        errors.append('Email is required')
    if not password:
        errors.append('Password is required')
    if not invite_code:
        errors.append('Invite code is required')

    # Check unique username/email
    if User.query.filter_by(username=username).first():
        errors.append('Username already taken')
    if User.query.filter_by(email=email).first():
        errors.append('Email already registered')

    # Validate invite code
    code_obj = InviteCode.query.filter_by(code=invite_code).first()
    if not code_obj:
        errors.append('Invalid invite code')
    elif not code_obj.can_use:
        errors.append('Invite code is no longer valid')

    if errors:
        return jsonify({'error': ', '.join(errors)}), 400

    # Create user
    user = User(
        username=username,
        email=email,
        password_hash=generate_password_hash(password),
    )
    db.session.add(user)
    db.session.commit()

    # Record code usage
    code_obj.current_uses += 1
    usage = CodeUsage(invite_code_id=code_obj.id, user_id=user.id)
    db.session.add(usage)
    db.session.commit()

    # Auto-login
    token = token_for(user)
    return jsonify({
        'message': 'Registration successful',
        'token': token,
        'user': user.to_dict_basic(),
    }), 201

@app.route('/auth/login', methods=['POST'])
def login():
    data = request.get_json()
    if not data:
        return jsonify({'error': 'No data provided'}), 400

    username = data.get('username', '')
    password = data.get('password', '')

    user = User.query.filter_by(username=username).first()
    if not user or not check_password_hash(user.password_hash, password):
        return jsonify({'error': 'Invalid username or password'}), 401

    token = token_for(user)
    return jsonify({
        'token': token,
        'user': user.to_dict_basic(),
    })

# ===========================================
# Profile routes
# ===========================================

@app.route('/profile', methods=['GET'])
@login_required
def get_profile(user):
    return jsonify({
        'username': user.username,
        'email': user.email,
        'full_name': user.full_name,
        'phone': user.phone,
        'location': user.location,
        'creative_role': user.creative_role,
        'bio': user.bio,
        'profile_complete': user.profile_complete,
        'is_admin': user.is_admin,
    })

@app.route('/profile', methods=['PUT'])
@login_required
def update_profile(user):
    data = request.get_json()
    if not data:
        return jsonify({'error': 'No data provided'}), 400

    errors = []
    full_name = data.get('full_name', '').strip()
    location = data.get('location', '').strip()
    creative_role = data.get('creative_role', '').strip()

    if not full_name:
        errors.append('Full name is required')
    if not location:
        errors.append('Location is required')
    if not creative_role:
        errors.append('Creative role is required')
    elif creative_role not in ['Photographer', 'Filmmaker', 'Designer', 'Writer', 'Visual Artist', 'Other']:
        errors.append('Invalid creative role')

    bio = data.get('bio', '').strip()
    if bio and len(bio) > 500:
        errors.append('Bio must be at most 500 characters')

    if errors:
        return jsonify({'error': ', '.join(errors)}), 400

    user.full_name = full_name
    user.phone = data.get('phone', '').strip()
    user.location = location
    user.creative_role = creative_role
    user.bio = bio
    user.profile_complete = True

    db.session.commit()

    return jsonify({'message': 'Profile updated successfully', 'profile_complete': True})

# ===========================================
# Event routes (discovery)
# ===========================================

@app.route('/events', methods=['GET'])
def list_events():
    # Public: anyone can browse events
    events = Event.query.filter_by(deleted=False).order_by(Event.event_datetime.asc()).all()
    return jsonify([e.to_dict_list() for e in events])

@app.route('/events/<int:event_id>', methods=['GET'])
def event_detail(event_id):
    event = db.session.get(Event, event_id)
    if not event or event.deleted:
        return jsonify({'error': 'Event not found'}), 404

    user = get_current_user()
    # Check if user has RSVP'd to this event
    user_rsvpd = False
    if user:
        attendance = Attendance.query.filter_by(
            user_id=user.id, event_id=event.id, deleted=False
        ).first()
        if attendance:
            user_rsvpd = True

    detail = event.to_dict_detail(user_rsvpd=user_rsvpd)
    if event.is_past():
        detail['message'] = 'Event has passed'
    return jsonify(detail)

# ===========================================
# RSVP
# ===========================================

@app.route('/events/<int:event_id>/rsvp', methods=['POST'])
@login_required
@profile_complete_required
def rsvp_event(user, event_id):
    event = db.session.get(Event, event_id)
    if not event or event.deleted:
        return jsonify({'error': 'Event not found'}), 404

    if event.is_past():
        return jsonify({'error': 'Cannot RSVP to a past event'}), 400

    if event.is_full():
        return jsonify({'error': 'Event is full'}), 400

    # Check for existing RSVP
    existing = Attendance.query.filter_by(
        user_id=user.id, event_id=event.id, deleted=False
    ).first()
    if existing:
        return jsonify({'error': 'You have already RSVP\'d to this event'}), 400

    # Determine payment status
    payment_status = 'paid' if event.price_cents == 0 else 'unpaid'

    attendance = Attendance(
        user_id=user.id,
        event_id=event.id,
        payment_status=payment_status,
        ticket_price_cents=event.price_cents,
    )
    db.session.add(attendance)
    db.session.commit()

    return jsonify({
        'message': 'RSVP successful',
        'payment_status': payment_status,
        'attendance_id': attendance.id,
    }), 201

# ===========================================
# My Events
# ===========================================

@app.route('/my-events', methods=['GET'])
@login_required
def my_events(user):
    attendances = Attendance.query.filter_by(
        user_id=user.id, deleted=False
    ).join(Event).order_by(Event.event_datetime.asc()).all()

    total_owed_cents = sum(
        a.amount_owed_cents for a in attendances if a.payment_status == 'unpaid'
    )

    records = []
    for a in attendances:
        rec = a.to_dict_member()
        rec['attended'] = a.attended  # add attended status
        records.append(rec)

    return jsonify({
        'events': records,
        'total_owed': f"${total_owed_cents / 100:.2f}",
        'total_owed_cents': total_owed_cents,
    })

# ===========================================
# Admin: Invite Codes
# ===========================================

@app.route('/admin/invite-codes', methods=['POST'])
@admin_required
def create_invite_code(user):
    data = request.get_json()
    code_str = data.get('code', '').strip()
    code_type = data.get('type', 'single')
    max_uses = data.get('max_uses')
    expires_at = data.get('expires_at')
    description = data.get('description', '')

    errors = []
    if not code_str:
        errors.append('Code is required')
    if InviteCode.query.filter_by(code=code_str).first():
        errors.append('Code already exists')
    if code_type not in ('single', 'multi'):
        errors.append('Type must be single or multi')
    if not expires_at:
        errors.append('Expiration date is required')
    else:
        try:
            expires_at = datetime.fromisoformat(expires_at)
        except:
            errors.append('Invalid expiration date format')
    if code_type == 'multi' and (not max_uses or max_uses < 1):
        errors.append('Max uses required for multi-use codes')

    if errors:
        return jsonify({'error': ', '.join(errors)}), 400

    code_obj = InviteCode(
        code=code_str,
        type=code_type,
        max_uses=max_uses if code_type == 'multi' else None,
        expires_at=expires_at,
        description=description,
    )
    db.session.add(code_obj)
    db.session.commit()

    return jsonify(code_obj.to_dict()), 201

@app.route('/admin/invite-codes', methods=['GET'])
@admin_required
def list_invite_codes(user):
    codes = InviteCode.query.order_by(InviteCode.created_at.desc()).all()
    return jsonify([c.to_dict() for c in codes])

@app.route('/admin/invite-codes/<int:code_id>', methods=['GET'])
@admin_required
def get_invite_code_detail(user, code_id):
    code_obj = db.session.get(InviteCode, code_id)
    if not code_obj:
        return jsonify({'error': 'Code not found'}), 404

    result = code_obj.to_dict()
    # Registration history
    usages = CodeUsage.query.filter_by(invite_code_id=code_obj.id).join(User).all()
    result['registrations'] = [
        {
            'user_id': u.user_id,
            'username': u.user.username,
            'email': u.user.email,
            'used_at': u.used_at.isoformat(),
        } for u in usages
    ]
    return jsonify(result)

@app.route('/admin/invite-codes/<int:code_id>/deactivate', methods=['POST'])
@admin_required
def deactivate_invite_code(user, code_id):
    code_obj = db.session.get(InviteCode, code_id)
    if not code_obj:
        return jsonify({'error': 'Code not found'}), 404
    code_obj.deactivated = True
    db.session.commit()
    return jsonify({'message': 'Code deactivated', 'status': code_obj.status})

@app.route('/admin/invite-codes/<int:code_id>', methods=['DELETE'])
@admin_required
def delete_invite_code(user, code_id):
    code_obj = db.session.get(InviteCode, code_id)
    if not code_obj:
        return jsonify({'error': 'Code not found'}), 404
    db.session.delete(code_obj)
    db.session.commit()
    return jsonify({'message': 'Code deleted'})

# ===========================================
# Admin: Events
# ===========================================

@app.route('/admin/events', methods=['POST'])
@admin_required
def create_event(user):
    data = request.get_json()
    title = data.get('title', '').strip()
    description = data.get('description', '').strip()
    event_datetime = data.get('event_datetime')
    location = data.get('location', '').strip()
    category = data.get('category', '').strip()
    capacity = data.get('capacity')
    price_cents = data.get('price_cents', 0)

    errors = []
    if not title:
        errors.append('Title is required')
    if not description:
        errors.append('Description is required')
    if not event_datetime:
        errors.append('Event date/time is required')
    else:
        try:
            event_datetime = datetime.fromisoformat(event_datetime)
        except:
            errors.append('Invalid date/time format')
    if not location:
        errors.append('Location is required')
    if category not in ['workshop', 'networking', 'exhibition', 'screening', 'social']:
        errors.append('Invalid category')
    if capacity is None or capacity < 1:
        errors.append('Capacity must be at least 1')
    if price_cents < 0:
        errors.append('Price cannot be negative')

    if errors:
        return jsonify({'error': ', '.join(errors)}), 400

    event = Event(
        title=title,
        description=description,
        event_datetime=event_datetime,
        location=location,
        category=category,
        capacity=capacity,
        price_cents=price_cents,
    )
    db.session.add(event)
    db.session.commit()

    return jsonify(event.to_dict_list()), 201

@app.route('/admin/events/<int:event_id>', methods=['PUT'])
@admin_required
def edit_event(user, event_id):
    event = db.session.get(Event, event_id)
    if not event or event.deleted:
        return jsonify({'error': 'Event not found'}), 404

    data = request.get_json()

    if 'title' in data:
        event.title = data['title'].strip()
    if 'description' in data:
        event.description = data['description'].strip()
    if 'event_datetime' in data:
        try:
            event.event_datetime = datetime.fromisoformat(data['event_datetime'])
        except:
            return jsonify({'error': 'Invalid date/time format'}), 400
    if 'location' in data:
        event.location = data['location'].strip()
    if 'category' in data:
        if data['category'] not in ['workshop', 'networking', 'exhibition', 'screening', 'social']:
            return jsonify({'error': 'Invalid category'}), 400
        event.category = data['category']
    if 'capacity' in data:
        if data['capacity'] < 1:
            return jsonify({'error': 'Capacity must be at least 1'}), 400
        event.capacity = data['capacity']
    if 'price_cents' in data:
        if data['price_cents'] < 0:
            return jsonify({'error': 'Price cannot be negative'}), 400
        event.price_cents = data['price_cents']

    db.session.commit()
    return jsonify(event.to_dict_list())

@app.route('/admin/events/<int:event_id>', methods=['DELETE'])
@admin_required
def delete_event(user, event_id):
    event = db.session.get(Event, event_id)
    if not event or event.deleted:
        return jsonify({'error': 'Event not found'}), 404

    db.session.delete(event)
    db.session.commit()

    return jsonify({'message': 'Event deleted'})

# Admin: Users
# ===========================================

@app.route('/admin/users', methods=['GET'])
@admin_required
def list_users(user):
    users = User.query.order_by(User.created_at.asc()).all()
    result = []
    for u in users:
        result.append({
            'id': u.id,
            'full_name': u.full_name,
            'email': u.email,
            'creative_role': u.creative_role,
            'is_admin': u.is_admin,
            'join_date': u.created_at.isoformat(),
        })
    return jsonify(result)

@app.route('/admin/users/<int:user_id>/admin', methods=['POST'])
@admin_required
def toggle_admin(admin_user, user_id):
    if admin_user.id == user_id:
        return jsonify({'error': 'Cannot change your own admin status'}), 400

    user = db.session.get(User, user_id)
    if not user:
        return jsonify({'error': 'User not found'}), 404

    action = request.json.get('action', 'grant')
    if action == 'grant':
        user.is_admin = True
        message = f'Admin privileges granted to {user.username}'
    elif action == 'revoke':
        user.is_admin = False
        message = f'Admin privileges revoked from {user.username}'
    else:
        return jsonify({'error': 'Action must be grant or revoke'}), 400

    db.session.commit()
    return jsonify({'message': message})

@app.route('/admin/users/<int:user_id>', methods=['DELETE'])
@admin_required
def delete_user(admin_user, user_id):
    if admin_user.id == user_id:
        return jsonify({'error': 'Cannot delete your own account'}), 400

    user = db.session.get(User, user_id)
    if not user:
        return jsonify({'error': 'User not found'}), 404

    # Cascade will delete attendances, restoring capacity
    db.session.delete(user)
    db.session.commit()

    return jsonify({'message': 'User deleted'})

# ===========================================
# Admin: Attendance & Payments
# ===========================================

@app.route('/admin/attendance', methods=['GET'])
@admin_required
def list_attendance_records(admin_user):
    event_id = request.args.get('event_id', type=int)
    payment_status = request.args.get('payment_status')
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')

    query = Attendance.query.filter_by(deleted=False).join(Event).join(User)

    if event_id:
        query = query.filter(Attendance.event_id == event_id)

    if payment_status:
        query = query.filter(Attendance.payment_status == payment_status)

    if start_date:
        try:
            start_dt = datetime.fromisoformat(start_date)
            query = query.filter(Attendance.payment_date >= start_dt)
        except:
            pass

    if end_date:
        try:
            end_dt = datetime.fromisoformat(end_date)
            query = query.filter(Attendance.payment_date <= end_dt)
        except:
            pass

    records = query.order_by(Event.event_datetime.asc()).all()
    return jsonify([r.to_dict_admin() for r in records])

@app.route('/admin/attendance/<int:attendance_id>/mark-attended', methods=['POST'])
@admin_required
def mark_attended(admin_user, attendance_id):
    attendance = db.session.get(Attendance, attendance_id)
    if not attendance or attendance.deleted:
        return jsonify({'error': 'Attendance record not found'}), 404

    attendance.attended = request.json.get('attended', True)
    db.session.commit()
    return jsonify({'message': 'Attendance updated', 'attended': attendance.attended})

@app.route('/admin/attendance/<int:attendance_id>/no-show-fee', methods=['POST'])
@admin_required
def apply_no_show_fee(admin_user, attendance_id):
    attendance = db.session.get(Attendance, attendance_id)
    if not attendance or attendance.deleted:
        return jsonify({'error': 'Attendance record not found'}), 404

    if attendance.no_show_fee_applied:
        return jsonify({'error': 'No-show fee already applied'}), 400

    attendance.no_show_fee_applied = True
    attendance.payment_status = 'unpaid'
    db.session.commit()
    return jsonify({
        'message': 'No-show fee applied',
        'amount_owed': attendance.amount_owed_display(),
    })

@app.route('/admin/attendance/<int:attendance_id>/payment-status', methods=['POST'])
@admin_required
def update_payment_status(admin_user, attendance_id):
    attendance = db.session.get(Attendance, attendance_id)
    if not attendance or attendance.deleted:
        return jsonify({'error': 'Attendance record not found'}), 404

    new_status = request.json.get('status')
    if new_status not in ('unpaid', 'processing', 'paid'):
        return jsonify({'error': 'Status must be unpaid, processing, or paid'}), 400

    attendance.payment_status = new_status
    if new_status == 'paid':
        attendance.payment_date = datetime.utcnow()
    db.session.commit()
    return jsonify({
        'message': 'Payment status updated',
        'payment_status': attendance.payment_status,
        'payment_date': attendance.payment_date.isoformat() if attendance.payment_date else None,
    })

@app.route('/admin/payment-summary', methods=['GET'])
@admin_required
def payment_summary(admin_user):
    event_id = request.args.get('event_id', type=int)
    payment_status = request.args.get('payment_status')
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')

    query = Attendance.query.filter_by(deleted=False).join(Event)

    if event_id:
        query = query.filter(Attendance.event_id == event_id)

    if payment_status:
        query = query.filter(Attendance.payment_status == payment_status)

    if start_date:
        try:
            start_dt = datetime.fromisoformat(start_date)
            query = query.filter(Attendance.payment_date >= start_dt)
        except:
            pass

    if end_date:
        try:
            end_dt = datetime.fromisoformat(end_date)
            query = query.filter(Attendance.payment_date <= end_dt)
        except:
            pass

    all_records = query.all()

    total_outstanding = sum(a.amount_owed_cents for a in all_records if a.payment_status == 'unpaid')
    total_collected = sum(a.amount_owed_cents for a in all_records if a.payment_status == 'paid')
    unpaid_count = sum(1 for a in all_records if a.payment_status == 'unpaid')

    return jsonify({
        'total_outstanding': f"${total_outstanding / 100:.2f}",
        'total_outstanding_cents': total_outstanding,
        'total_collected': f"${total_collected / 100:.2f}",
        'total_collected_cents': total_collected,
        'unpaid_count': unpaid_count,
    })

# ===========================================
# Database initialization and default admin
# ===========================================

def init_db():
    db.create_all()

    # Create default admin if not exists
    admin = User.query.filter_by(username='core_admin').first()
    if not admin:
        admin = User(
            username='core_admin',
            email='core_admin@example.com',
            password_hash=generate_password_hash('CoreAdmin!2025'),
            is_admin=True,
            full_name='Core Admin',
            location='Bronx, NY',
            creative_role='Designer',
            profile_complete=True,
        )
        db.session.add(admin)
        db.session.commit()

if __name__ == '__main__':
    with app.app_context():
        init_db()
    app.run(debug=False, port=int(os.environ.get("PORT", 5000)))
