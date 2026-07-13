from flask import Flask, request, jsonify
import csv
from datetime import datetime
import hashlib

app = Flask(__name__)

# Load users from CSV
users = {}
def load_users():
    global users
    with open('assets/users.csv', 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            users[row['username']] = {
                'username': row['username'],
                'display_name': row['display_name'],
                'password': row['password']
            }
load_users()

# In-memory storage
messages = {
    '#general': []  # List of message dicts
}
# DMs stored with key format: "dm:{user1}:{user2}" (alphabetically sorted usernames)
dm_conversations = {}

# Session storage (simple in-memory)
sessions = {}

def generate_session_token():
    import secrets
    return secrets.token_hex(32)

def get_dm_key(user1, user2):
    """Generate consistent key for DM conversation between two users"""
    return f"dm:{':'.join(sorted([user1, user2]))}"

def validate_message(text):
    """Validate message text - not whitespace-only and max 2000 chars"""
    if not text or text.isspace():
        return False, "Message cannot be whitespace-only"
    if len(text) > 2000:
        return False, "Message exceeds 2000 characters"
    return True, None

@app.route('/login', methods=['POST'])
def login():
    """Authenticate user with username and password"""
    data = request.get_json()
    if not data:
        return jsonify({'error': 'Invalid request'}), 400
    
    username = data.get('username')
    password = data.get('password')
    
    if not username or not password:
        return jsonify({'error': 'Username and password required'}), 400
    
    user = users.get(username)
    if not user or user['password'] != password:
        return jsonify({'error': 'Invalid credentials'}), 401
    
    # Create session
    token = generate_session_token()
    sessions[token] = username
    return jsonify({'token': token, 'user': {
        'username': user['username'],
        'display_name': user['display_name']
    }})

@app.route('/me', methods=['GET'])
def get_current_user():
    """Get current logged-in user info"""
    token = request.headers.get('Authorization', '').replace('Bearer ', '')
    if not token or token not in sessions:
        return jsonify({'error': 'Not authenticated'}), 401
    
    username = sessions[token]
    user = users[username]
    return jsonify({
        'username': user['username'],
        'display_name': user['display_name']
    })

@app.route('/users', methods=['GET'])
def list_users():
    """List all users (for DM search)"""
    token = request.headers.get('Authorization', '').replace('Bearer ', '')
    if not token or token not in sessions:
        return jsonify({'error': 'Not authenticated'}), 401
    
    current_username = sessions[token]
    user_list = []
    for username, user in users.items():
        if username != current_username:  # Exclude self
            user_list.append({
                'username': user['username'],
                'display_name': user['display_name']
            })
    return jsonify({'users': user_list})

@app.route('/users/search', methods=['POST'])
def search_users():
    """Search for users by username or display_name (case-insensitive partial match)"""
    token = request.headers.get('Authorization', '').replace('Bearer ', '')
    if not token or token not in sessions:
        return jsonify({'error': 'Not authenticated'}), 401
    
    data = request.get_json()
    if not data:
        return jsonify({'error': 'Invalid request'}), 400
    
    query = data.get('query', '').lower()
    if not query:
        return jsonify({'users': []})
    
    current_username = sessions[token]
    results = []
    for username, user in users.items():
        if username == current_username:  # Exclude self
            continue
        if query in username.lower() or query in user['display_name'].lower():
            results.append({
                'username': user['username'],
                'display_name': user['display_name']
            })
    return jsonify({'users': results})

@app.route('/conversations', methods=['GET'])
def list_conversations():
    """List all conversations for current user (#general + their DMs)"""
    token = request.headers.get('Authorization', '').replace('Bearer ', '')
    if not token or token not in sessions:
        return jsonify({'error': 'Not authenticated'}), 401
    
    current_username = sessions[token]
    conversations = []
    
    # Add #general channel
    general_msgs = messages.get('#general', [])
    last_message = general_msgs[-1] if general_msgs else None
    conversations.append({
        'id': '#general',
        'type': 'channel',
        'name': '#general',
        'last_message': last_message
    })
    
    # Add DM conversations
    for dm_key, dm_msgs in dm_conversations.items():
        if dm_key.startswith('dm:'):
            parts = dm_key.split(':')
            user1, user2 = parts[1], parts[2]
            if current_username in [user1, user2]:
                other_user = user2 if user1 == current_username else user1
                last_message = dm_msgs[-1] if dm_msgs else None
                conversations.append({
                    'id': dm_key,
                    'type': 'dm',
                    'with': {
                        'username': other_user,
                        'display_name': users[other_user]['display_name']
                    },
                    'last_message': last_message
                })
    
    return jsonify({'conversations': conversations})

@app.route('/messages/<conversation_id>', methods=['GET'])
def get_messages(conversation_id):
    """Get messages from a conversation (chronologically, oldest first)"""
    token = request.headers.get('Authorization', '').replace('Bearer ', '')
    if not token or token not in sessions:
        return jsonify({'error': 'Not authenticated'}), 401
    
    current_username = sessions[token]
    
    if conversation_id == '#general':
        msgs = messages.get('#general', [])
        return jsonify({'messages': msgs})
    
    # Check if it's a DM
    if conversation_id.startswith('dm:'):
        # Verify user is part of this DM
        parts = conversation_id.split(':')
        user1, user2 = parts[1], parts[2]
        if current_username not in [user1, user2]:
            return jsonify({'error': 'Access denied'}), 403
        
        msgs = dm_conversations.get(conversation_id, [])
        return jsonify({'messages': msgs})
    
    return jsonify({'error': 'Conversation not found'}), 404

@app.route('/messages/<conversation_id>', methods=['POST'])
def send_message(conversation_id):
    """Send a message to a conversation"""
    token = request.headers.get('Authorization', '').replace('Bearer ', '')
    if not token or token not in sessions:
        return jsonify({'error': 'Not authenticated'}), 401
    
    current_username = sessions[token]
    data = request.get_json()
    if not data:
        return jsonify({'error': 'Invalid request'}), 400
    
    text = data.get('text', '')
    
    # Validate message
    valid, error = validate_message(text)
    if not valid:
        return jsonify({'error': error}), 400
    
    message = {
        'id': hashlib.md5(f"{datetime.now().isoformat()}:{current_username}".encode()).hexdigest()[:16],
        'text': text,
        'author': current_username,
        'author_display_name': users[current_username]['display_name'],
        'timestamp': datetime.now().isoformat()
    }
    
    if conversation_id == '#general':
        messages['#general'].append(message)
        return jsonify({'message': message}), 201
    
    # Handle DM
    if conversation_id.startswith('dm:'):
        parts = conversation_id.split(':')
        user1, user2 = parts[1], parts[2]
        if current_username not in [user1, user2]:
            return jsonify({'error': 'Access denied'}), 403
        
        if conversation_id not in dm_conversations:
            dm_conversations[conversation_id] = []
        dm_conversations[conversation_id].append(message)
        return jsonify({'message': message}), 201
    
    return jsonify({'error': 'Conversation not found'}), 404

@app.route('/search', methods=['GET'])
def global_search():
    """Global search across #general and user's DMs (case-insensitive, newest first)"""
    token = request.headers.get('Authorization', '').replace('Bearer ', '')
    if not token or token not in sessions:
        return jsonify({'error': 'Not authenticated'}), 401
    
    current_username = sessions[token]
    query = request.args.get('q', '').lower()
    if not query:
        return jsonify({'results': []})
    
    results = []
    
    # Search #general
    for msg in messages.get('#general', []):
        if query in msg['text'].lower():
            results.append({
                'message': msg,
                'conversation': {
                    'id': '#general',
                    'type': 'channel',
                    'name': '#general'
                }
            })
    
    # Search user's DMs
    for dm_key, dm_msgs in dm_conversations.items():
        if dm_key.startswith('dm:'):
            parts = dm_key.split(':')
            user1, user2 = parts[1], parts[2]
            if current_username in [user1, user2]:
                other_user = user2 if user1 == current_username else user1
                for msg in dm_msgs:
                    if query in msg['text'].lower():
                        results.append({
                            'message': msg,
                            'conversation': {
                                'id': dm_key,
                                'type': 'dm',
                                'with': {
                                    'username': other_user,
                                    'display_name': users[other_user]['display_name']
                                }
                            }
                        })
    
    # Sort by timestamp newest first
    results.sort(key=lambda x: x['message']['timestamp'], reverse=True)
    
    return jsonify({'results': results})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000, debug=True)
