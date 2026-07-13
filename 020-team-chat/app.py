from flask import Flask, request, jsonify
from functools import wraps
import csv
import time
import uuid

app = Flask(__name__)

# Load users from CSV
USERS = {}
with open('assets/users.csv', newline='') as csvfile:
    reader = csv.DictReader(csvfile)
    for row in reader:
        USERS[row['username']] = {
            'username': row['username'],
            'display_name': row['display_name'],
            'password': row['password']
        }

# In-memory storage
tokens = {}
general_messages = []
dms = {}
next_message_id = 1


def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth = request.headers.get('Authorization', '')
        if not auth.startswith('Bearer '):
            return jsonify({'error': 'Unauthorized'}), 401
        token = auth[7:]
        if token not in tokens:
            return jsonify({'error': 'Unauthorized'}), 401
        return f(*args, **kwargs)
    return decorated


def current_user():
    auth = request.headers.get('Authorization', '')
    if auth.startswith('Bearer '):
        return tokens.get(auth[7:])
    return None


@app.route('/login', methods=['POST'])
def login():
    data = request.get_json() or {}
    username = data.get('username', '')
    password = data.get('password', '')
    user = USERS.get(username)
    if not user or user['password'] != password:
        return jsonify({'error': 'Invalid credentials'}), 401
    token = str(uuid.uuid4())
    tokens[token] = username
    return jsonify({
        'token': token,
        'user': {
            'username': user['username'],
            'display_name': user['display_name']
        }
    })


@app.route('/logout', methods=['POST'])
@token_required
def logout():
    auth = request.headers.get('Authorization', '')
    tokens.pop(auth[7:], None)
    return jsonify({})


@app.route('/users/search', methods=['POST'])
@token_required
def search_users():
    data = request.get_json() or {}
    query = data.get('query', '').lower()
    me = current_user()
    results = []
    for u in USERS.values():
        if u['username'] == me:
            continue
        if query in u['username'].lower() or query in u['display_name'].lower():
            results.append({
                'username': u['username'],
                'display_name': u['display_name']
            })
    return jsonify({'results': results})


@app.route('/channels/general/messages', methods=['GET', 'POST'])
@token_required
def general_messages_endpoint():
    global next_message_id
    me = current_user()
    if request.method == 'POST':
        data = request.get_json() or {}
        text = data.get('text', '')
        if not text or not text.strip():
            return jsonify({'error': 'Message cannot be empty'}), 400
        if len(text) > 2000:
            return jsonify({'error': 'Message too long'}), 400
        msg = {
            'id': next_message_id,
            'sender': me,
            'text': text,
            'timestamp': int(time.time())
        }
        general_messages.append(msg)
        next_message_id += 1
        return jsonify(msg), 201
    else:
        return jsonify({'messages': general_messages})


@app.route('/dms/<username>/messages', methods=['GET', 'POST'])
@token_required
def dm_messages(username):
    global next_message_id
    me = current_user()
    if username not in USERS:
        return jsonify({'error': 'User not found'}), 404
    if username == me:
        return jsonify({'error': 'Cannot DM yourself'}), 400
    key = tuple(sorted([me, username]))
    if request.method == 'POST':
        if key not in dms:
            dms[key] = []
        data = request.get_json() or {}
        text = data.get('text', '')
        if not text or not text.strip():
            return jsonify({'error': 'Message cannot be empty'}), 400
        if len(text) > 2000:
            return jsonify({'error': 'Message too long'}), 400
        msg = {
            'id': next_message_id,
            'sender': me,
            'text': text,
            'timestamp': int(time.time())
        }
        dms[key].append(msg)
        next_message_id += 1
        return jsonify(msg), 201
    else:
        return jsonify({'messages': dms.get(key, [])})


@app.route('/conversations', methods=['GET'])
@token_required
def conversations():
    me = current_user()
    result = [{'type': 'channel', 'name': '#general'}]
    for key, msgs in dms.items():
        if me in key and msgs:
            other = key[0] if key[1] == me else key[1]
            result.append({
                'type': 'dm',
                'username': other,
                'display_name': USERS[other]['display_name']
            })
    return jsonify({'conversations': result})


@app.route('/search', methods=['GET'])
@token_required
def search():
    me = current_user()
    query = request.args.get('q', '').lower()
    if not query:
        return jsonify({'results': []})
    results = []
    for msg in general_messages:
        if query in msg['text'].lower():
            results.append({
                'id': msg['id'],
                'sender': msg['sender'],
                'text': msg['text'],
                'timestamp': msg['timestamp'],
                'conversation': {'type': 'channel', 'name': '#general'}
            })
    for key, msgs in dms.items():
        if me in key:
            other = key[0] if key[1] == me else key[1]
            for msg in msgs:
                if query in msg['text'].lower():
                    results.append({
                        'id': msg['id'],
                        'sender': msg['sender'],
                        'text': msg['text'],
                        'timestamp': msg['timestamp'],
                        'conversation': {
                            'type': 'dm',
                            'username': other,
                            'display_name': USERS[other]['display_name']
                        }
                    })
    results.sort(key=lambda x: (x["timestamp"], x["id"]), reverse=True)
    return jsonify({'results': results})


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)
