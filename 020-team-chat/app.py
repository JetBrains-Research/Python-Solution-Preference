from flask import Flask, request, jsonify, session
import csv
import uuid
from datetime import datetime

app = Flask(__name__)
app.secret_key = 'secret_key_for_session'

# Data structures
users = {} # username -> {display_name, password}
messages = [] # List of {id, channel_id, sender, text, timestamp}
# channels: 'general' is fixed. DMs are identified by sorted pair of usernames.
channels = {'general': {'name': '#general', 'type': 'public'}}

# Load users from CSV
def load_users():
    with open('assets/users.csv', mode='r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            users[row['username']] = {
                'display_name': row['display_name'],
                'password': row['password']
            }

load_users()

def get_dm_id(u1, u2):
    return 'dm_' + '_'.join(sorted([u1, u2]))

@app.route('/login', methods=['POST'])
def login():
    data = request.json
    username = data.get('username')
    password = data.get('password')
    
    user = users.get(username)
    if user and user['password'] == password:
        session['username'] = username
        return jsonify({'message': 'Login successful'}), 200
    return jsonify({'error': 'Invalid credentials'}), 401

@app.route('/logout', methods=['POST'])
def logout():
    session.pop('username', None)
    return jsonify({'message': 'Logged out'}), 200

def get_current_user():
    return session.get('username')

@app.route('/channels', methods=['GET'])
def list_channels():
    user = get_current_user()
    if not user: return jsonify({'error': 'Unauthorized'}), 401
    
    user_channels = [{'id': 'general', 'name': '#general'}]
    
    # Find all DMs this user is part of by scanning messages
    dm_ids = set()
    for msg in messages:
        if msg['channel_id'].startswith('dm_') and user in msg['channel_id']:
            dm_ids.add(msg['channel_id'])
            
    for dm_id in dm_ids:
        parts = dm_id.split('_')[1:]
        other = parts[1] if parts[0] == user else parts[0]
        user_channels.append({'id': dm_id, 'name': f'DM with {users[other]["display_name"]}'})
        
    return jsonify(user_channels), 200

@app.route('/users/search', methods=['GET'])
def search_users():
    user = get_current_user()
    if not user: return jsonify({'error': 'Unauthorized'}), 401
    
    query = request.args.get('q', '').lower()
    results = []
    for username, info in users.items():
        if username == user: continue
        if query in username.lower() or query in info['display_name'].lower():
            results.append({'username': username, 'display_name': info['display_name']})
            
    return jsonify(results), 200

@app.route('/messages/<channel_id>', methods=['GET'])
def get_messages(channel_id):
    user = get_current_user()
    if not user: return jsonify({'error': 'Unauthorized'}), 401
    
    if channel_id.startswith('dm_'):
        if user not in channel_id:
            return jsonify({'error': 'Unauthorized access to this DM'}), 403
            
    channel_msgs = [m for m in messages if m['channel_id'] == channel_id]
    # Return chronologically (oldest first)
    return jsonify(sorted(channel_msgs, key=lambda x: x['timestamp'])), 200

@app.route('/messages', methods=['POST'])
def send_message():
    user = get_current_user()
    if not user: return jsonify({'error': 'Unauthorized'}), 401
    
    data = request.json
    channel_id = data.get('channel_id')
    text = data.get('text', '').strip()
    
    if not text or len(text) > 2000:
        return jsonify({'error': 'Invalid message text'}), 400
        
    if channel_id.startswith('dm_'):
        if user not in channel_id:
            return jsonify({'error': 'Unauthorized access to this DM'}), 403
    elif channel_id != 'general':
        return jsonify({'error': 'Invalid channel'}), 400
        
    msg = {
        'id': str(uuid.uuid4()),
        'channel_id': channel_id,
        'sender': user,
        'text': text,
        'timestamp': datetime.utcnow().isoformat()
    }
    messages.append(msg)
    return jsonify(msg), 201

@app.route('/search', methods=['GET'])
def global_search():
    user = get_current_user()
    if not user: return jsonify({'error': 'Unauthorized'}), 401
    
    query = request.args.get('q', '').lower()
    results = []
    
    for m in messages:
        # Check if user has access to the channel
        if m['channel_id'] == 'general' or (m['channel_id'].startswith('dm_') and user in m['channel_id']):
            if query in m['text'].lower():
                results.append(m)
                
    # Newest first
    return jsonify(sorted(results, key=lambda x: x['timestamp'], reverse=True)), 200

if __name__ == '__main__':
    app.run(port=8080)
