import os
import json
import re
import datetime
import secrets
import hashlib
from functools import wraps
from flask import Flask, request, jsonify, g

app = Flask(__name__)
app.config['JSON_SORT_KEYS'] = False

DATABASE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'family_social.db')

# Database helpers
import sqlite3


def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(DATABASE)
        db.row_factory = sqlite3.Row
    return db


@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()


def init_db():
    db = sqlite3.connect(DATABASE)
    db.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            username TEXT UNIQUE,
            display_name TEXT,
            bio TEXT,
            profile_photo TEXT,
            birth_date TEXT,
            is_profile_complete INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            token TEXT NOT NULL UNIQUE,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS relationships (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            requester_id INTEGER NOT NULL,
            recipient_id INTEGER NOT NULL,
            status TEXT NOT NULL CHECK(status IN ('Pending','Active','Past')),
            requester_type TEXT NOT NULL CHECK(requester_type IN ('Parent','Child','Spouse','Sibling')),
            recipient_type TEXT NOT NULL CHECK(recipient_type IN ('Parent','Child','Spouse','Sibling')),
            moved_to_past_at TEXT,
            past_status TEXT CHECK(past_status IN ('Declined','Canceled','Ended'))
        );
        CREATE TABLE IF NOT EXISTS posts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            author_id INTEGER NOT NULL,
            caption TEXT,
            images TEXT NOT NULL DEFAULT '[]',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
    """)
    db.commit()
    db.close()


# Password helpers
def hash_password(password):
    salt = secrets.token_hex(16)
    pw_hash = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), 100000).hex()
    return salt + pw_hash


def verify_password(password, hashed):
    salt = hashed[:32]
    pw_hash = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), 100000).hex()
    return (salt + pw_hash) == hashed


def generate_token():
    return secrets.token_urlsafe(32)


# Auth helpers
def get_auth_user():
    auth = request.headers.get('Authorization', '')
    if not auth.startswith('Bearer '):
        return None
    token = auth[7:]
    db = get_db()
    row = db.execute(
        'SELECT s.user_id, u.* FROM sessions s JOIN users u ON s.user_id = u.id WHERE s.token = ?',
        (token,)
    ).fetchone()
    if row is None:
        return None
    return dict(row)


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        user = get_auth_user()
        if user is None:
            return jsonify({'error': 'Authentication required'}), 401
        g.current_user = user
        return f(*args, **kwargs)
    return decorated


def profile_complete_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        user = get_auth_user()
        if user is None:
            return jsonify({'error': 'Authentication required'}), 401
        if not user['is_profile_complete']:
            return jsonify({'error': 'Profile must be completed first'}), 403
        g.current_user = user
        return f(*args, **kwargs)
    return decorated


# Validation helpers
EMAIL_RE = re.compile(r'^[^@]+@[^@]+\.[^@]+$')
USERNAME_RE = re.compile(r'^[A-Za-z0-9_]+$')


def validate_email(email):
    return EMAIL_RE.match(email) is not None


def validate_username(username):
    return USERNAME_RE.match(username) is not None and 3 <= len(username) <= 30


def validate_password(password):
    return len(password) >= 8


def parse_birth_date(date_str):
    if not date_str:
        return None
    try:
        d = datetime.datetime.strptime(date_str, '%Y-%m-%d').date()
        if d > datetime.date.today():
            return None
        return date_str
    except ValueError:
        return None


# User helper
def get_user_by_id(user_id):
    db = get_db()
    row = db.execute('SELECT * FROM users WHERE id = ?', (user_id,)).fetchone()
    if row is None:
        return None
    return dict(row)


def reciprocal_type(sender_type):
    if sender_type in ('Spouse', 'Sibling'):
        return sender_type
    elif sender_type == 'Parent':
        return 'Child'
    elif sender_type == 'Child':
        return 'Parent'
    return sender_type


def has_active_relationship(user_a, user_b):
    if user_a == user_b:
        return True
    db = get_db()
    row = db.execute("""
        SELECT 1 FROM relationships
        WHERE status = 'Active'
        AND ((requester_id = ? AND recipient_id = ?) OR (requester_id = ? AND recipient_id = ?))
    """, (user_a, user_b, user_b, user_a)).fetchone()
    return row is not None


def get_active_relationships_for_profile(user_id):
    db = get_db()
    rows = db.execute("""
        SELECT r.recipient_id AS other_id, r.requester_type AS rel_type, u.username
        FROM relationships r
        JOIN users u ON r.recipient_id = u.id
        WHERE r.status = 'Active' AND r.requester_id = ?
        UNION ALL
        SELECT r.requester_id AS other_id, r.recipient_type AS rel_type, u.username
        FROM relationships r
        JOIN users u ON r.requester_id = u.id
        WHERE r.status = 'Active' AND r.recipient_id = ?
    """, (user_id, user_id)).fetchall()

    groups = {}
    for r in rows:
        rel_type = r['rel_type']
        if rel_type not in groups:
            groups[rel_type] = []
        groups[rel_type].append({'user_id': r['other_id'], 'username': r['username']})
    for rel_type in groups:
        groups[rel_type].sort(key=lambda x: x['username'].lower())
    return groups


def _fetch_posts(author_id):
    db = get_db()
    rows = db.execute("""
        SELECT id, author_id, caption, images, created_at, updated_at
        FROM posts WHERE author_id = ? ORDER BY created_at DESC
    """, (author_id,)).fetchall()
    return [_format_post(r) for r in rows]


def _format_post(row):
    return {
        'id': row['id'],
        'author_id': row['author_id'],
        'caption': row['caption'],
        'images': json.loads(row['images']),
        'created_at': row['created_at'],
        'updated_at': row['updated_at']
    }


def get_visible_posts(author_id, viewer_id):
    if author_id == viewer_id:
        return _fetch_posts(author_id)
    if has_active_relationship(author_id, viewer_id):
        return _fetch_posts(author_id)
    return []


# Endpoints
@app.route('/health', methods=['GET'])
def health():
    return jsonify({'status': 'ok'})


@app.route('/register', methods=['POST'])
def register():
    data = request.get_json() or {}
    email = (data.get('email') or '').strip().lower()
    password = data.get('password') or ''

    if not email or not password:
        return jsonify({'error': 'Email and password required'}), 400
    if not validate_email(email):
        return jsonify({'error': 'Invalid email'}), 400
    if not validate_password(password):
        return jsonify({'error': 'Password must be at least 8 characters'}), 400

    db = get_db()
    existing = db.execute('SELECT 1 FROM users WHERE email = ?', (email,)).fetchone()
    if existing:
        return jsonify({'error': 'Email already registered'}), 409

    pw_hash = hash_password(password)
    now = datetime.datetime.utcnow().isoformat()
    cursor = db.execute(
        'INSERT INTO users (email, password_hash, is_profile_complete, created_at) VALUES (?, ?, 0, ?)',
        (email, pw_hash, now)
    )
    user_id = cursor.lastrowid
    token = generate_token()
    db.execute('INSERT INTO sessions (user_id, token, created_at) VALUES (?, ?, ?)', (user_id, token, now))
    db.commit()
    return jsonify({'user_id': user_id, 'token': token}), 201


@app.route('/login', methods=['POST'])
def login():
    data = request.get_json() or {}
    email = (data.get('email') or '').strip().lower()
    password = data.get('password') or ''

    db = get_db()
    user = db.execute('SELECT * FROM users WHERE email = ?', (email,)).fetchone()
    if user is None or not verify_password(password, user['password_hash']):
        return jsonify({'error': 'Invalid email or password'}), 401

    token = generate_token()
    now = datetime.datetime.utcnow().isoformat()
    db.execute('INSERT INTO sessions (user_id, token, created_at) VALUES (?, ?, ?)', (user['id'], token, now))
    db.commit()
    return jsonify({'user_id': user['id'], 'token': token})


@app.route('/logout', methods=['POST'])
@login_required
def logout():
    auth = request.headers.get('Authorization', '')
    token = auth[7:]
    db = get_db()
    db.execute('DELETE FROM sessions WHERE token = ?', (token,))
    db.commit()
    return jsonify({'message': 'Logged out'})


@app.route('/account', methods=['DELETE'])
@login_required
def delete_account():
    user = g.current_user
    user_id = user['id']
    now = datetime.datetime.utcnow().isoformat()
    db = get_db()

    db.execute("""
        UPDATE relationships
        SET status = 'Past', past_status = 'Ended', moved_to_past_at = ?
        WHERE status IN ('Active', 'Pending') AND (requester_id = ? OR recipient_id = ?)
    """, (now, user_id, user_id))

    db.execute('DELETE FROM posts WHERE author_id = ?', (user_id,))
    db.execute('DELETE FROM sessions WHERE user_id = ?', (user_id,))
    db.execute('DELETE FROM users WHERE id = ?', (user_id,))
    db.commit()
    return jsonify({'message': 'Account deleted'})


@app.route('/profile', methods=['POST'])
@login_required
def complete_profile():
    user = g.current_user
    if user['is_profile_complete']:
        return jsonify({'error': 'Profile already complete'}), 400

    data = request.get_json() or {}
    username = (data.get('username') or '').strip()
    display_name = (data.get('display_name') or '').strip()

    if not username or not display_name:
        return jsonify({'error': 'Username and display name required'}), 400
    if not validate_username(username):
        return jsonify({'error': 'Username must be 3-30 characters, alphanumeric and underscores only'}), 400

    db = get_db()
    existing = db.execute('SELECT 1 FROM users WHERE LOWER(username) = ?', (username.lower(),)).fetchone()
    if existing:
        return jsonify({'error': 'Username already taken'}), 409

    bio = data.get('bio')
    profile_photo = data.get('profile_photo')
    birth_date = None
    if data.get('birth_date'):
        birth_date = parse_birth_date(data['birth_date'])
        if birth_date is None:
            return jsonify({'error': 'Invalid birth date'}), 400

    db.execute("""
        UPDATE users
        SET username = ?, display_name = ?, bio = ?, profile_photo = ?, birth_date = ?, is_profile_complete = 1
        WHERE id = ?
    """, (username, display_name, bio, profile_photo, birth_date, user['id']))
    db.commit()
    return jsonify({'message': 'Profile completed'})


@app.route('/profile', methods=['PATCH'])
@profile_complete_required
def update_profile():
    user = g.current_user
    data = request.get_json() or {}
    db = get_db()

    updates = []
    params = []

    if 'display_name' in data:
        val = data['display_name'].strip()
        if not val:
            return jsonify({'error': 'Display name cannot be empty'}), 400
        updates.append('display_name = ?')
        params.append(val)

    if 'bio' in data:
        updates.append('bio = ?')
        params.append(data['bio'])

    if 'profile_photo' in data:
        updates.append('profile_photo = ?')
        params.append(data['profile_photo'])

    if 'birth_date' in data:
        bd = parse_birth_date(data['birth_date'])
        if data['birth_date'] and bd is None:
            return jsonify({'error': 'Invalid birth date'}), 400
        updates.append('birth_date = ?')
        params.append(bd)

    if not updates:
        return jsonify({'error': 'No fields to update'}), 400

    params.append(user['id'])
    db.execute(f"UPDATE users SET {', '.join(updates)} WHERE id = ?", params)
    db.commit()
    return jsonify({'message': 'Profile updated'})


@app.route('/me', methods=['GET'])
@login_required
def get_me():
    user = g.current_user
    return jsonify({
        'id': user['id'],
        'email': user['email'],
        'username': user['username'],
        'display_name': user['display_name'],
        'bio': user['bio'],
        'profile_photo': user['profile_photo'],
        'birth_date': user['birth_date'],
        'is_profile_complete': bool(user['is_profile_complete'])
    })


@app.route('/profile/<int:user_id>', methods=['GET'])
@profile_complete_required
def get_profile(user_id):
    viewer = g.current_user
    db = get_db()
    user = get_user_by_id(user_id)
    if user is None:
        return jsonify({'error': 'User not found'}), 404

    has_active = has_active_relationship(viewer['id'], user_id)

    result = {
        'id': user['id'],
        'username': user['username'],
        'display_name': user['display_name'],
        'profile_photo': user['profile_photo'],
        'bio': user['bio'],
        'active_relationships': get_active_relationships_for_profile(user_id)
    }

    if viewer['id'] == user_id or has_active:
        result['birth_date'] = user['birth_date']
        result['posts'] = get_visible_posts(user_id, viewer['id'])
    else:
        result['birth_date'] = None
        result['posts'] = None

    return jsonify(result)


# Relationships
@app.route('/relationships/request', methods=['POST'])
@profile_complete_required
def request_relationship():
    user = g.current_user
    data = request.get_json() or {}
    recipient_id = data.get('recipient_id')
    rel_type = data.get('type')

    if recipient_id is None or not isinstance(recipient_id, int):
        return jsonify({'error': 'recipient_id required'}), 400
    if not rel_type or rel_type not in ('Parent', 'Child', 'Spouse', 'Sibling'):
        return jsonify({'error': 'Invalid relationship type'}), 400
    if recipient_id == user['id']:
        return jsonify({'error': 'Cannot request relationship with yourself'}), 400

    db = get_db()
    recipient = get_user_by_id(recipient_id)
    if recipient is None or not recipient['is_profile_complete']:
        return jsonify({'error': 'Recipient not found or profile incomplete'}), 404

    existing = db.execute("""
        SELECT 1 FROM relationships
        WHERE status IN ('Pending', 'Active')
        AND ((requester_id = ? AND recipient_id = ?) OR (requester_id = ? AND recipient_id = ?))
    """, (user['id'], recipient_id, recipient_id, user['id'])).fetchone()
    if existing:
        return jsonify({'error': 'Relationship already exists or is pending'}), 409

    recip_type = reciprocal_type(rel_type)
    db.execute("""
        INSERT INTO relationships (requester_id, recipient_id, status, requester_type, recipient_type)
        VALUES (?, ?, 'Pending', ?, ?)
    """, (user['id'], recipient_id, rel_type, recip_type))
    db.commit()
    return jsonify({'message': 'Relationship request sent'}), 201


@app.route('/relationships/<int:rel_id>/accept', methods=['POST'])
@profile_complete_required
def accept_relationship(rel_id):
    user = g.current_user
    db = get_db()
    rel = db.execute('SELECT * FROM relationships WHERE id = ?', (rel_id,)).fetchone()
    if rel is None or rel['status'] != 'Pending' or rel['recipient_id'] != user['id']:
        return jsonify({'error': 'Request not found'}), 404
    db.execute("UPDATE relationships SET status = 'Active' WHERE id = ?", (rel_id,))
    db.commit()
    return jsonify({'message': 'Relationship accepted'})


@app.route('/relationships/<int:rel_id>/decline', methods=['POST'])
@profile_complete_required
def decline_relationship(rel_id):
    user = g.current_user
    db = get_db()
    rel = db.execute('SELECT * FROM relationships WHERE id = ?', (rel_id,)).fetchone()
    if rel is None or rel['status'] != 'Pending' or rel['recipient_id'] != user['id']:
        return jsonify({'error': 'Request not found'}), 404
    now = datetime.datetime.utcnow().isoformat()
    db.execute("""
        UPDATE relationships SET status = 'Past', past_status = 'Declined', moved_to_past_at = ?
        WHERE id = ?
    """, (now, rel_id))
    db.commit()
    return jsonify({'message': 'Relationship declined'})


@app.route('/relationships/<int:rel_id>/cancel', methods=['POST'])
@profile_complete_required
def cancel_relationship(rel_id):
    user = g.current_user
    db = get_db()
    rel = db.execute('SELECT * FROM relationships WHERE id = ?', (rel_id,)).fetchone()
    if rel is None or rel['status'] != 'Pending' or rel['requester_id'] != user['id']:
        return jsonify({'error': 'Request not found'}), 404
    now = datetime.datetime.utcnow().isoformat()
    db.execute("""
        UPDATE relationships SET status = 'Past', past_status = 'Canceled', moved_to_past_at = ?
        WHERE id = ?
    """, (now, rel_id))
    db.commit()
    return jsonify({'message': 'Relationship canceled'})


@app.route('/relationships/<int:rel_id>/end', methods=['POST'])
@profile_complete_required
def end_relationship(rel_id):
    user = g.current_user
    db = get_db()
    rel = db.execute('SELECT * FROM relationships WHERE id = ?', (rel_id,)).fetchone()
    if rel is None or rel['status'] != 'Active':
        return jsonify({'error': 'Relationship not found'}), 404
    if rel['requester_id'] != user['id'] and rel['recipient_id'] != user['id']:
        return jsonify({'error': 'Relationship not found'}), 404
    now = datetime.datetime.utcnow().isoformat()
    db.execute("""
        UPDATE relationships SET status = 'Past', past_status = 'Ended', moved_to_past_at = ?
        WHERE id = ?
    """, (now, rel_id))
    db.commit()
    return jsonify({'message': 'Relationship ended'})


@app.route('/relationships/incoming', methods=['GET'])
@profile_complete_required
def incoming_requests():
    user = g.current_user
    db = get_db()
    rows = db.execute("""
        SELECT r.id, r.requester_id, r.requester_type, r.recipient_type, u.username, u.display_name
        FROM relationships r
        JOIN users u ON r.requester_id = u.id
        WHERE r.recipient_id = ? AND r.status = 'Pending'
    """, (user['id'],)).fetchall()
    return jsonify([{
        'id': r['id'],
        'requester_id': r['requester_id'],
        'type': r['requester_type'],
        'reciprocal_type': r['recipient_type'],
        'username': r['username'],
        'display_name': r['display_name']
    } for r in rows])


@app.route('/relationships/outgoing', methods=['GET'])
@profile_complete_required
def outgoing_requests():
    user = g.current_user
    db = get_db()
    rows = db.execute("""
        SELECT r.id, r.recipient_id, r.requester_type, r.recipient_type, u.username, u.display_name
        FROM relationships r
        JOIN users u ON r.recipient_id = u.id
        WHERE r.requester_id = ? AND r.status = 'Pending'
    """, (user['id'],)).fetchall()
    return jsonify([{
        'id': r['id'],
        'recipient_id': r['recipient_id'],
        'type': r['requester_type'],
        'reciprocal_type': r['recipient_type'],
        'username': r['username'],
        'display_name': r['display_name']
    } for r in rows])


@app.route('/relationships/active', methods=['GET'])
@profile_complete_required
def active_relationships():
    user = g.current_user
    db = get_db()
    rows = db.execute("""
        SELECT r.id, r.recipient_id AS other_id, r.requester_type AS rel_type, u.username, u.display_name
        FROM relationships r
        LEFT JOIN users u ON r.recipient_id = u.id
        WHERE r.status = 'Active' AND r.requester_id = ?
        UNION ALL
        SELECT r.id, r.requester_id AS other_id, r.recipient_type AS rel_type, u.username, u.display_name
        FROM relationships r
        LEFT JOIN users u ON r.requester_id = u.id
        WHERE r.status = 'Active' AND r.recipient_id = ?
    """, (user['id'], user['id'])).fetchall()

    groups = {}
    for r in rows:
        rel_type = r['rel_type']
        if rel_type not in groups:
            groups[rel_type] = []
        groups[rel_type].append({
            'relationship_id': r['id'],
            'user_id': r['other_id'],
            'username': r['username'] if r['username'] else 'Deleted User',
            'display_name': r['display_name'] if r['display_name'] else 'Deleted User'
        })
    for rel_type in groups:
        groups[rel_type].sort(key=lambda x: x['username'].lower())
    return jsonify(groups)


@app.route('/relationships/past', methods=['GET'])
@profile_complete_required
def past_relationships():
    user = g.current_user
    db = get_db()
    rows = db.execute("""
        SELECT r.id, r.recipient_id AS other_id, r.requester_type AS rel_type, r.past_status, r.moved_to_past_at, u.username, u.display_name
        FROM relationships r
        LEFT JOIN users u ON r.recipient_id = u.id
        WHERE r.status = 'Past' AND r.requester_id = ?
        UNION ALL
        SELECT r.id, r.requester_id AS other_id, r.recipient_type AS rel_type, r.past_status, r.moved_to_past_at, u.username, u.display_name
        FROM relationships r
        LEFT JOIN users u ON r.requester_id = u.id
        WHERE r.status = 'Past' AND r.recipient_id = ?
    """, (user['id'], user['id'])).fetchall()

    result = []
    for r in rows:
        if r['username']:
            other_name = r['username']
        else:
            other_name = 'Deleted User'
        result.append({
            'relationship_id': r['id'],
            'other_user_name': other_name,
            'type': r['rel_type'],
            'status': r['past_status'],
            'moved_to_past_at': r['moved_to_past_at']
        })
    return jsonify(result)


# Posts
@app.route('/posts', methods=['POST'])
@profile_complete_required
def create_post():
    user = g.current_user
    data = request.get_json() or {}
    caption = data.get('caption')
    images = data.get('images', [])

    if not isinstance(images, list):
        return jsonify({'error': 'images must be a list'}), 400

    has_caption = isinstance(caption, str) and caption.strip()
    has_images = len(images) > 0

    if not has_caption and not has_images:
        return jsonify({'error': 'Post requires caption or images'}), 400
    if len(images) > 4:
        return jsonify({'error': 'Up to 4 images allowed'}), 400

    now = datetime.datetime.utcnow().isoformat()
    db = get_db()
    cursor = db.execute("""
        INSERT INTO posts (author_id, caption, images, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?)
    """, (user['id'], caption if has_caption else None, json.dumps(images), now, now))
    db.commit()
    post_id = cursor.lastrowid
    return jsonify({'post_id': post_id, 'message': 'Post created'}), 201


@app.route('/posts/<int:post_id>', methods=['GET'])
@profile_complete_required
def get_post(post_id):
    viewer = g.current_user
    db = get_db()
    post = db.execute('SELECT * FROM posts WHERE id = ?', (post_id,)).fetchone()
    if post is None:
        return jsonify({'error': 'Post not found'}), 404
    if post['author_id'] != viewer['id'] and not has_active_relationship(post['author_id'], viewer['id']):
        return jsonify({'error': 'Post not found'}), 404
    return jsonify(_format_post(post))


@app.route('/posts/<int:post_id>', methods=['PATCH'])
@profile_complete_required
def edit_post(post_id):
    user = g.current_user
    db = get_db()
    post = db.execute('SELECT * FROM posts WHERE id = ?', (post_id,)).fetchone()
    if post is None:
        return jsonify({'error': 'Post not found'}), 404
    if post['author_id'] != user['id']:
        return jsonify({'error': 'Not authorized'}), 403

    data = request.get_json() or {}
    if 'caption' not in data:
        return jsonify({'error': 'Only caption can be edited'}), 400

    caption = data['caption']
    if not isinstance(caption, str) or not caption.strip():
        return jsonify({'error': 'Caption cannot be empty'}), 400

    now = datetime.datetime.utcnow().isoformat()
    db.execute('UPDATE posts SET caption = ?, updated_at = ? WHERE id = ?', (caption, now, post_id))
    db.commit()
    return jsonify({'message': 'Post updated'})


@app.route('/posts/<int:post_id>', methods=['DELETE'])
@profile_complete_required
def delete_post(post_id):
    user = g.current_user
    db = get_db()
    post = db.execute('SELECT * FROM posts WHERE id = ?', (post_id,)).fetchone()
    if post is None:
        return jsonify({'error': 'Post not found'}), 404
    if post['author_id'] != user['id']:
        return jsonify({'error': 'Not authorized'}), 403
    db.execute('DELETE FROM posts WHERE id = ?', (post_id,))
    db.commit()
    return jsonify({'message': 'Post deleted'})


# Feed
@app.route('/feed', methods=['GET'])
@profile_complete_required
def get_feed():
    user = g.current_user
    db = get_db()

    rel_rows = db.execute("""
        SELECT CASE WHEN requester_id = ? THEN recipient_id ELSE requester_id END AS other_id
        FROM relationships
        WHERE status = 'Active' AND (requester_id = ? OR recipient_id = ?)
    """, (user['id'], user['id'], user['id'])).fetchall()

    author_ids = [r['other_id'] for r in rel_rows]
    author_ids.append(user['id'])

    placeholders = ','.join('?' * len(author_ids))
    rows = db.execute(f"""
        SELECT * FROM posts
        WHERE author_id IN ({placeholders})
        ORDER BY created_at DESC
    """, author_ids).fetchall()

    return jsonify([_format_post(r) for r in rows])


# Search
@app.route('/search', methods=['GET'])
@profile_complete_required
def search_users():
    query = (request.args.get('q') or '').strip().lower()
    if not query:
        return jsonify([])

    db = get_db()
    rows = db.execute("""
        SELECT id, username, display_name, profile_photo, bio
        FROM users
        WHERE is_profile_complete = 1
        AND (LOWER(username) LIKE ? OR LOWER(display_name) LIKE ?)
        ORDER BY LOWER(username) ASC
    """, (f'%{query}%', f'%{query}%')).fetchall()

    return jsonify([{
        'id': r['id'],
        'username': r['username'],
        'display_name': r['display_name'],
        'profile_photo': r['profile_photo'],
        'bio': r['bio']
    } for r in rows])


if __name__ == '__main__':
    init_db()
    app.run(host='0.0.0.0', port=5001)
