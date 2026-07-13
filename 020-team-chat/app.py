from flask import Flask, request, jsonify, make_response
import csv
import uuid
from datetime import datetime
import re

app = Flask(__name__)

# Load users from CSV
users = []
with open('assets/users.csv', mode='r') as file:
    reader = csv.DictReader(file)
    for row in reader:
        users.append({
            'username': row['username'],
            'display_name': row['display_name'],
            'password': row['password']
        })

# In-memory storage
messages = []  # All messages (general and DMs)
dm_conversations = {}  # Key: frozenset({user1, user2}), Value: list of message IDs
user_sessions = {}  # Key: session_token, Value: username

# Helper functions
def generate_session_token():
    return str(uuid.uuid4())

def validate_user(username, password):
    for user in users:
        if user['username'] == username and user['password'] == password:
            return True
    return False

def get_user_by_username(username):
    for user in users:
        if user['username'] == username:
            return user
    return None

def get_current_user():
    session_token = request.cookies.get('session_token')
    if not session_token or session_token not in user_sessions:
        return None
    return user_sessions[session_token]

def require_auth(f):
    def wrapper(*args, **kwargs):
        current_user = get_current_user()
        if not current_user:
            return jsonify({'error': 'Unauthorized'}), 401
        return f(current_user, *args, **kwargs)
    wrapper.__name__ = f.__name__
    return wrapper

def find_user_by_search(query, exclude_username=None):
    query = query.lower()
    results = []
    for user in users:
        if exclude_username and user['username'] == exclude_username:
            continue
        if (query in user['username'].lower() or
            query in user['display_name'].lower()):
            results.append({
                'username': user['username'],
                'display_name': user['display_name']
            })
    return results

def get_dm_key(user1, user2):
    return frozenset({user1, user2})

def create_message(sender, conversation_type, conversation_id, content):
    message_id = str(uuid.uuid4())
    timestamp = datetime.utcnow().isoformat() + 'Z'
    message = {
        'id': message_id,
        'sender': sender,
        'conversation_type': conversation_type,  # 'general' or 'dm'
        'conversation_id': conversation_id,
        'content': content,
        'timestamp': timestamp
    }
    messages.append(message)
    return message

# Routes
@app.route('/login', methods=['POST'])
def login():
    data = request.get_json()
    if not data or 'username' not in data or 'password' not in data:
        return jsonify({'error': 'Username and password required'}), 400

    username = data['username']
    password = data['password']

    if not validate_user(username, password):
        return jsonify({'error': 'Invalid credentials'}), 401

    session_token = generate_session_token()
    user_sessions[session_token] = username

    response = make_response(jsonify({'status': 'ok'}))
    response.set_cookie('session_token', session_token, httponly=True)
    return response

@app.route('/logout', methods=['POST'])
def logout():
    session_token = request.cookies.get('session_token')
    if session_token and session_token in user_sessions:
        del user_sessions[session_token]

    response = make_response(jsonify({'status': 'ok'}))
    response.delete_cookie('session_token')
    return response

@app.route('/users/search', methods=['GET'])
@require_auth
def search_users(current_user):
    query = request.args.get('q', '')
    if not query:
        return jsonify({'users': []})

    found_users = find_user_by_search(query, exclude_username=current_user)
    return jsonify({'users': found_users})

@app.route('/conversations', methods=['GET'])
@require_auth
def list_conversations(current_user):
    conversations = []

    # General channel
    general_messages = [m for m in messages if m['conversation_type'] == 'general']
    general_messages.sort(key=lambda x: x['timestamp'])
    conversations.append({
        'id': 'general',
        'type': 'channel',
        'name': '#general',
        'last_message': general_messages[-1] if general_messages else None
    })

    # DM conversations
    for dm_key in dm_conversations:
        if current_user in dm_key:
            other_user = [u for u in dm_key if u != current_user][0]
            dm_messages = [m for m in messages if m['id'] in dm_conversations[dm_key]]
            dm_messages.sort(key=lambda x: x['timestamp'])

            other_user_obj = get_user_by_username(other_user)
            conversations.append({
                'id': str(dm_key),
                'type': 'dm',
                'name': other_user_obj['display_name'] if other_user_obj else other_user,
                'last_message': dm_messages[-1] if dm_messages else None,
                'with_user': other_user
            })

    return jsonify({'conversations': conversations})

@app.route('/conversations/general/messages', methods=['GET'])
@require_auth
def get_general_messages(current_user):
    general_messages = [m for m in messages if m['conversation_type'] == 'general']
    general_messages.sort(key=lambda x: x['timestamp'])
    return jsonify({'messages': general_messages})

@app.route('/conversations/general/messages', methods=['POST'])
@require_auth
def send_general_message(current_user):
    data = request.get_json()
    if not data or 'content' not in data:
        return jsonify({'error': 'Content is required'}), 400

    content = data['content'].strip()
    if not content:
        return jsonify({'error': 'Message cannot be empty'}), 400

    if len(content) > 2000:
        return jsonify({'error': 'Message too long (max 2000 characters)'}), 400

    message = create_message(
        sender=current_user,
        conversation_type='general',
        conversation_id='general',
        content=content
    )

    return jsonify(message), 201

@app.route('/conversations/dm/<other_username>/messages', methods=['GET'])
@require_auth
def get_dm_messages(current_user, other_username):
    if not get_user_by_username(other_username):
        return jsonify({'error': 'User not found'}), 404

    dm_key = get_dm_key(current_user, other_username)
    if dm_key not in dm_conversations:
        return jsonify({'messages': []})

    dm_message_ids = dm_conversations[dm_key]
    dm_messages = [m for m in messages if m['id'] in dm_message_ids]
    dm_messages.sort(key=lambda x: x['timestamp'])

    return jsonify({'messages': dm_messages})

@app.route('/conversations/dm/<other_username>/messages', methods=['POST'])
@require_auth
def send_dm_message(current_user, other_username):
    if not get_user_by_username(other_username):
        return jsonify({'error': 'User not found'}), 404

    data = request.get_json()
    if not data or 'content' not in data:
        return jsonify({'error': 'Content is required'}), 400

    content = data['content'].strip()
    if not content:
        return jsonify({'error': 'Message cannot be empty'}), 400

    if len(content) > 2000:
        return jsonify({'error': 'Message too long (max 2000 characters)'}), 400

    dm_key = get_dm_key(current_user, other_username)
    if dm_key not in dm_conversations:
        dm_conversations[dm_key] = []

    message = create_message(
        sender=current_user,
        conversation_type='dm',
        conversation_id=str(dm_key),
        content=content
    )

    dm_conversations[dm_key].append(message['id'])
    return jsonify(message), 201

@app.route('/search', methods=['GET'])
@require_auth
def search_messages(current_user):
    query = request.args.get('q', '')
    if not query:
        return jsonify({'results': []})

    query = query.lower()
    results = []

    # Search in general channel
    general_messages = [m for m in messages if m['conversation_type'] == 'general']
    for msg in general_messages:
        if query in msg['content'].lower():
            results.append({
                'message_id': msg['id'],
                'sender': msg['sender'],
                'content': msg['content'],
                'timestamp': msg['timestamp'],
                'conversation_type': 'channel',
                'conversation_name': '#general'
            })

    # Search in user's DMs
    for dm_key in dm_conversations:
        if current_user in dm_key:
            other_user = [u for u in dm_key if u != current_user][0]
            dm_message_ids = dm_conversations[dm_key]
            dm_messages = [m for m in messages if m['id'] in dm_message_ids]
            for msg in dm_messages:
                if query in msg['content'].lower():
                    other_user_obj = get_user_by_username(other_user)
                    results.append({
                        'message_id': msg['id'],
                        'sender': msg['sender'],
                        'content': msg['content'],
                        'timestamp': msg['timestamp'],
                        'conversation_type': 'dm',
                        'conversation_name': other_user_obj['display_name'] if other_user_obj else other_user
                    })

    # Sort by timestamp (newest first)
    results.sort(key=lambda x: x['timestamp'], reverse=True)
    return jsonify({'results': results})

@app.route('/me', methods=['GET'])
@require_auth
def get_current_user_info(current_user):
    user_obj = get_user_by_username(current_user)
    if user_obj:
        return jsonify({
            'username': user_obj['username'],
            'display_name': user_obj['display_name']
        })
    return jsonify({'error': 'User not found'}), 404

if __name__ == '__main__':
    app.run(debug=True, port=5000)
