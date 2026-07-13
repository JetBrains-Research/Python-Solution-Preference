from flask import Flask, request, jsonify, session
from datetime import datetime, date
from uuid import uuid4
import re
import os

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'dev-secret-key-change-me')

# ---------------- In-memory data stores ----------------
users = {}  # user_id -> user dict
email_index = {}  # lowercase email -> user_id
username_index = {}  # lowercase username -> user_id
relationships = {}  # rel_id -> relationship dict
posts = {}  # post_id -> post dict

USERNAME_RE = re.compile(r'^[A-Za-z0-9_]{3,30}$')

RECIPROCAL = {
    'Spouse': 'Spouse',
    'Sibling': 'Sibling',
    'Parent': 'Child',
    'Child': 'Parent',
}

# ---------------- Helpers ----------------
def now_iso():
    return datetime.utcnow().isoformat() + 'Z'

def current_user():
    uid = session.get('user_id')
    if uid and uid in users:
        return users[uid]
    return None

def require_login():
    u = current_user()
    if not u:
        return None, (jsonify({'error': 'not authenticated'}), 401)
    return u, None

def require_profile_complete():
    u, err = require_login()
    if err:
        return None, err
    if not u.get('username') or not u.get('display_name'):
        return None, (jsonify({'error': 'profile not complete'}), 403)
    return u, None

def public_profile(u):
    active_rels = []
    for r in relationships.values():
        if r['status'] != 'Active':
            continue
        if u['id'] == r['sender_id']:
            other_id = r['recipient_id']
            my_type = r['sender_type']
        elif u['id'] == r['recipient_id']:
            other_id = r['sender_id']
            my_type = RECIPROCAL[r['sender_type']]
        else:
            continue
        other = users.get(other_id)
        if not other:
            continue
        active_rels.append({
            'user_id': other_id,
            'username': other['username'],
            'display_name': other['display_name'],
            'type': my_type,
        })
    # group by type, alphabetical by username
    grouped = {}
    for rel in active_rels:
        grouped.setdefault(rel['type'], []).append(rel)
    for t in grouped:
        grouped[t].sort(key=lambda x: x['username'].lower())
    return {
        'id': u['id'],
        'username': u['username'],
        'display_name': u['display_name'],
        'profile_photo': u.get('profile_photo'),
        'bio': u.get('bio'),
        'active_relationships': grouped,
    }

def has_active_relationship(a_id, b_id):
    if a_id == b_id:
        return False
    for r in relationships.values():
        if r['status'] != 'Active':
            continue
        pair = {r['sender_id'], r['recipient_id']}
        if pair == {a_id, b_id}:
            return True
    return False

def get_pair_relationship(a_id, b_id, statuses=None):
    for r in relationships.values():
        pair = {r['sender_id'], r['recipient_id']}
        if pair == {a_id, b_id}:
            if statuses is None or r['status'] in statuses:
                return r
    return None

def serialize_relationship(r, viewer_id):
    other_id = r['recipient_id'] if r['sender_id'] == viewer_id else r['sender_id']
    other = users.get(other_id)
    other_name = other['display_name'] if other else 'Deleted User'
    other_username = other['username'] if other else None
    if viewer_id == r['sender_id']:
        my_type = r['sender_type']
    else:
        my_type = RECIPROCAL[r['sender_type']] if r['status'] == 'Active' else r['sender_type']
        # For pending incoming, recipient sees the sender's selected type
    return {
        'id': r['id'],
        'other_user_id': other_id,
        'other_username': other_username,
        'other_display_name': other_name,
        'type': my_type,
        'status': r['status'],
        'created_at': r['created_at'],
        'updated_at': r.get('updated_at'),
        'past_status': r.get('past_status'),
        'moved_to_past_at': r.get('moved_to_past_at'),
    }

def serialize_post(p):
    author = users.get(p['author_id'])
    return {
        'id': p['id'],
        'author_id': p['author_id'],
        'author_username': author['username'] if author else None,
        'author_display_name': author['display_name'] if author else 'Deleted User',
        'caption': p['caption'],
        'images': p['images'],
        'created_at': p['created_at'],
        'updated_at': p.get('updated_at'),
    }

# ---------------- Auth ----------------
@app.post('/api/signup')
def signup():
    data = request.get_json(silent=True) or {}
    email = (data.get('email') or '').strip()
    password = data.get('password') or ''
    if not email or '@' not in email:
        return jsonify({'error': 'invalid email'}), 400
    if len(password) < 8:
        return jsonify({'error': 'password must be at least 8 characters'}), 400
    if email.lower() in email_index:
        return jsonify({'error': 'email already in use'}), 400
    uid = str(uuid4())
    users[uid] = {
        'id': uid,
        'email': email,
        'password': password,
        'username': None,
        'display_name': None,
        'bio': None,
        'profile_photo': None,
        'birth_date': None,
        'created_at': now_iso(),
    }
    email_index[email.lower()] = uid
    session['user_id'] = uid
    return jsonify({'id': uid, 'email': email, 'profile_complete': False}), 201

@app.post('/api/login')
def login():
    data = request.get_json(silent=True) or {}
    email = (data.get('email') or '').strip().lower()
    password = data.get('password') or ''
    uid = email_index.get(email)
    if not uid or users[uid]['password'] != password:
        return jsonify({'error': 'invalid credentials'}), 401
    session['user_id'] = uid
    u = users[uid]
    return jsonify({'id': uid, 'profile_complete': bool(u.get('username') and u.get('display_name'))})

@app.post('/api/logout')
def logout():
    session.pop('user_id', None)
    return jsonify({'ok': True})

@app.delete('/api/account')
def delete_account():
    u, err = require_login()
    if err:
        return err
    uid = u['id']
    # Delete posts
    to_del = [pid for pid, p in posts.items() if p['author_id'] == uid]
    for pid in to_del:
        del posts[pid]
    # Relationships: keep them but they will show "Deleted User"; per spec, all relationships involving user show Deleted User in other users' Past sections.
    # Move all active/pending to past as Ended? Spec says relationships (Active and Past) show Deleted User in Past sections.
    # Interpret: user's account deletion ends all active/pending, moves them to Past for others.
    for r in list(relationships.values()):
        if uid in (r['sender_id'], r['recipient_id']):
            if r['status'] in ('Active', 'Pending'):
                r['status'] = 'Past'
                r['past_status'] = 'Ended'
                r['moved_to_past_at'] = now_iso()
    # Remove indices
    email_index.pop(u['email'].lower(), None)
    if u.get('username'):
        username_index.pop(u['username'].lower(), None)
    del users[uid]
    session.pop('user_id', None)
    return jsonify({'ok': True})

# ---------------- Profile ----------------
@app.put('/api/profile')
def update_profile():
    u, err = require_login()
    if err:
        return err
    data = request.get_json(silent=True) or {}
    # Username
    if 'username' in data:
        username = (data.get('username') or '').strip()
        if not USERNAME_RE.match(username):
            return jsonify({'error': 'invalid username'}), 400
        existing = username_index.get(username.lower())
        if existing and existing != u['id']:
            return jsonify({'error': 'username already taken'}), 400
        if u.get('username'):
            username_index.pop(u['username'].lower(), None)
        u['username'] = username
        username_index[username.lower()] = u['id']
    if 'display_name' in data:
        dn = (data.get('display_name') or '').strip()
        if not dn:
            return jsonify({'error': 'display_name required'}), 400
        u['display_name'] = dn
    if 'bio' in data:
        u['bio'] = data.get('bio')
    if 'profile_photo' in data:
        u['profile_photo'] = data.get('profile_photo')
    if 'birth_date' in data:
        bd = data.get('birth_date')
        if bd:
            try:
                parsed = date.fromisoformat(bd)
            except Exception:
                return jsonify({'error': 'invalid birth_date'}), 400
            if parsed > date.today():
                return jsonify({'error': 'birth_date cannot be in the future'}), 400
            u['birth_date'] = bd
        else:
            u['birth_date'] = None
    if not u.get('username') or not u.get('display_name'):
        return jsonify({'error': 'username and display_name required'}), 400
    return jsonify(public_profile(u))

@app.get('/api/me')
def get_me():
    u, err = require_login()
    if err:
        return err
    return jsonify({
        **public_profile(u),
        'email': u['email'],
        'birth_date': u.get('birth_date'),
        'profile_complete': bool(u.get('username') and u.get('display_name')),
    })

@app.get('/api/users/<user_id>')
def get_user(user_id):
    target = users.get(user_id)
    if not target:
        return jsonify({'error': 'not found'}), 404
    result = public_profile(target)
    viewer = current_user()
    if viewer and (viewer['id'] == target['id'] or has_active_relationship(viewer['id'], target['id'])):
        result['birth_date'] = target.get('birth_date')
        # posts list
        user_posts = [serialize_post(p) for p in posts.values() if p['author_id'] == target['id']]
        user_posts.sort(key=lambda p: p['created_at'], reverse=True)
        result['posts'] = user_posts
    return jsonify(result)

# ---------------- Search ----------------
@app.get('/api/search')
def search():
    u, err = require_profile_complete()
    if err:
        return err
    q = (request.args.get('q') or '').strip().lower()
    if not q:
        return jsonify([])
    results = []
    for user in users.values():
        if not user.get('username'):
            continue
        if q in user['username'].lower() or q in (user['display_name'] or '').lower():
            results.append({
                'id': user['id'],
                'username': user['username'],
                'display_name': user['display_name'],
                'profile_photo': user.get('profile_photo'),
            })
    results.sort(key=lambda x: x['username'].lower())
    return jsonify(results)

# ---------------- Relationships ----------------
@app.post('/api/relationships/requests')
def send_request():
    u, err = require_profile_complete()
    if err:
        return err
    data = request.get_json(silent=True) or {}
    target_id = data.get('user_id')
    rel_type = data.get('type')
    if rel_type not in RECIPROCAL:
        return jsonify({'error': 'invalid type'}), 400
    if not target_id or target_id == u['id']:
        return jsonify({'error': 'invalid target'}), 400
    target = users.get(target_id)
    if not target:
        return jsonify({'error': 'target not found'}), 404
    existing = get_pair_relationship(u['id'], target_id, statuses=['Pending', 'Active'])
    if existing:
        return jsonify({'error': 'relationship already exists'}), 400
    rid = str(uuid4())
    relationships[rid] = {
        'id': rid,
        'sender_id': u['id'],
        'recipient_id': target_id,
        'sender_type': rel_type,
        'status': 'Pending',
        'created_at': now_iso(),
    }
    return jsonify(serialize_relationship(relationships[rid], u['id'])), 201

@app.post('/api/relationships/<rel_id>/accept')
def accept_request(rel_id):
    u, err = require_profile_complete()
    if err:
        return err
    r = relationships.get(rel_id)
    if not r or r['status'] != 'Pending' or r['recipient_id'] != u['id']:
        return jsonify({'error': 'not found'}), 404
    r['status'] = 'Active'
    r['updated_at'] = now_iso()
    return jsonify(serialize_relationship(r, u['id']))

@app.post('/api/relationships/<rel_id>/decline')
def decline_request(rel_id):
    u, err = require_profile_complete()
    if err:
        return err
    r = relationships.get(rel_id)
    if not r or r['status'] != 'Pending' or r['recipient_id'] != u['id']:
        return jsonify({'error': 'not found'}), 404
    r['status'] = 'Past'
    r['past_status'] = 'Declined'
    r['moved_to_past_at'] = now_iso()
    return jsonify(serialize_relationship(r, u['id']))

@app.post('/api/relationships/<rel_id>/cancel')
def cancel_request(rel_id):
    u, err = require_profile_complete()
    if err:
        return err
    r = relationships.get(rel_id)
    if not r or r['status'] != 'Pending' or r['sender_id'] != u['id']:
        return jsonify({'error': 'not found'}), 404
    r['status'] = 'Past'
    r['past_status'] = 'Canceled'
    r['moved_to_past_at'] = now_iso()
    return jsonify(serialize_relationship(r, u['id']))

@app.post('/api/relationships/<rel_id>/end')
def end_relationship(rel_id):
    u, err = require_profile_complete()
    if err:
        return err
    r = relationships.get(rel_id)
    if not r or r['status'] != 'Active' or u['id'] not in (r['sender_id'], r['recipient_id']):
        return jsonify({'error': 'not found'}), 404
    r['status'] = 'Past'
    r['past_status'] = 'Ended'
    r['moved_to_past_at'] = now_iso()
    return jsonify(serialize_relationship(r, u['id']))

@app.get('/api/relationships')
def list_relationships():
    u, err = require_profile_complete()
    if err:
        return err
    incoming, outgoing, active, past = [], [], [], []
    for r in relationships.values():
        if u['id'] not in (r['sender_id'], r['recipient_id']):
            continue
        s = serialize_relationship(r, u['id'])
        if r['status'] == 'Pending':
            if r['sender_id'] == u['id']:
                outgoing.append(s)
            else:
                incoming.append(s)
        elif r['status'] == 'Active':
            active.append(s)
        elif r['status'] == 'Past':
            past.append(s)
    return jsonify({
        'incoming': incoming,
        'outgoing': outgoing,
        'active': active,
        'past': past,
    })

# ---------------- Posts ----------------
@app.post('/api/posts')
def create_post():
    u, err = require_profile_complete()
    if err:
        return err
    data = request.get_json(silent=True) or {}
    caption = (data.get('caption') or '').strip()
    images = data.get('images') or []
    if not isinstance(images, list):
        return jsonify({'error': 'invalid images'}), 400
    if len(images) > 4:
        return jsonify({'error': 'max 4 images'}), 400
    if not caption and not images:
        return jsonify({'error': 'post requires caption or images'}), 400
    pid = str(uuid4())
    posts[pid] = {
        'id': pid,
        'author_id': u['id'],
        'caption': caption,
        'images': images,
        'created_at': now_iso(),
    }
    return jsonify(serialize_post(posts[pid])), 201

@app.get('/api/posts/<post_id>')
def get_post(post_id):
    p = posts.get(post_id)
    if not p:
        return jsonify({'error': 'not found'}), 404
    viewer = current_user()
    if not viewer:
        return jsonify({'error': 'forbidden'}), 403
    if viewer['id'] != p['author_id'] and not has_active_relationship(viewer['id'], p['author_id']):
        return jsonify({'error': 'forbidden'}), 403
    return jsonify(serialize_post(p))

@app.put('/api/posts/<post_id>')
def edit_post(post_id):
    u, err = require_profile_complete()
    if err:
        return err
    p = posts.get(post_id)
    if not p or p['author_id'] != u['id']:
        return jsonify({'error': 'not found'}), 404
    data = request.get_json(silent=True) or {}
    if 'caption' in data:
        new_caption = (data.get('caption') or '').strip()
        if not new_caption and not p['images']:
            return jsonify({'error': 'post requires caption or images'}), 400
        p['caption'] = new_caption
        p['updated_at'] = now_iso()
    return jsonify(serialize_post(p))

@app.delete('/api/posts/<post_id>')
def delete_post(post_id):
    u, err = require_profile_complete()
    if err:
        return err
    p = posts.get(post_id)
    if not p or p['author_id'] != u['id']:
        return jsonify({'error': 'not found'}), 404
    del posts[post_id]
    return jsonify({'ok': True})

@app.get('/api/feed')
def feed():
    u, err = require_profile_complete()
    if err:
        return err
    visible_authors = {u['id']}
    for r in relationships.values():
        if r['status'] != 'Active':
            continue
        if r['sender_id'] == u['id']:
            visible_authors.add(r['recipient_id'])
        elif r['recipient_id'] == u['id']:
            visible_authors.add(r['sender_id'])
    feed_posts = [serialize_post(p) for p in posts.values() if p['author_id'] in visible_authors]
    feed_posts.sort(key=lambda p: p['created_at'], reverse=True)
    return jsonify(feed_posts)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)), debug=False)
