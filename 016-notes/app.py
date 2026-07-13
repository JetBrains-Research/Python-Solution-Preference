from flask import Flask, request, jsonify
import json
import os
from datetime import datetime, timezone
import uuid

app = Flask(__name__)

PASSWORD = "my-notes-are-mine"
NOTES_FILE = "notes.json"

def load_notes():
    if not os.path.exists(NOTES_FILE):
        return {}
    with open(NOTES_FILE, 'r') as f:
        try:
            return json.load(f)
        except:
            return {}

def save_notes(notes):
    with open(NOTES_FILE, 'w') as f:
        json.dump(notes, f, indent=2)

def get_title(body):
    lines = body.strip().split('\n')
    for line in lines:
        if line.strip():
            return line.strip()
    return "New Note"

def get_preview(body):
    lines = body.strip().split('\n')
    if len(lines) <= 1:
        return ""
    for line in lines[1:]:
        if line.strip():
            preview = line.strip()
            if len(preview) > 50:
                return preview[:47] + "..."
            return preview
    return ""

def format_timestamp(ts):
    return ts.strftime("%Y-%m-%d %H:%M")

def check_password():
    password = request.headers.get('X-Password') or request.args.get('password')
    if not password:
        return False, "Password is required", 401
    if password != PASSWORD:
        return False, "Incorrect password", 403
    return True, None, None

@app.route('/notes', methods=['GET'])
def list_notes():
    valid, error, code = check_password()
    if not valid:
        return jsonify({"error": error}), code

    notes = load_notes()
    search_query = request.args.get('q', '').lower()

    notes_list = []
    for note_id, note in notes.items():
        body = note.get('body', '')
        timestamp = datetime.fromisoformat(note['timestamp']).replace(tzinfo=timezone.utc)
        title = get_title(body)
        preview = get_preview(body)

        if search_query:
            if search_query not in title.lower() and search_query not in body.lower():
                continue

        notes_list.append({
            'id': note_id,
            'title': title,
            'preview': preview,
            'timestamp': format_timestamp(timestamp)
        })

    notes_list.sort(key=lambda x: x['timestamp'], reverse=True)
    return jsonify(notes_list)

@app.route('/notes', methods=['POST'])
def create_note():
    valid, error, code = check_password()
    if not valid:
        return jsonify({"error": error}), code

    notes = load_notes()
    note_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    notes[note_id] = {
        'body': '',
        'timestamp': now.isoformat()
    }
    save_notes(notes)
    return jsonify({'id': note_id, 'message': 'Note created'}), 201

@app.route('/notes/<note_id>', methods=['GET'])
def get_note(note_id):
    valid, error, code = check_password()
    if not valid:
        return jsonify({"error": error}), code

    notes = load_notes()
    if note_id not in notes:
        return jsonify({"error": "Note not found"}), 404

    note = notes[note_id]
    body = note.get('body', '')
    timestamp = datetime.fromisoformat(note['timestamp']).replace(tzinfo=timezone.utc)
    title = get_title(body)

    return jsonify({
        'id': note_id,
        'title': title,
        'body': body,
        'timestamp': format_timestamp(timestamp)
    })

@app.route('/notes/<note_id>', methods=['PUT'])
def update_note(note_id):
    valid, error, code = check_password()
    if not valid:
        return jsonify({"error": error}), code

    notes = load_notes()
    if note_id not in notes:
        return jsonify({"error": "Note not found"}), 404

    data = request.get_json(force=True)
    body = data.get('body', '')
    now = datetime.now(timezone.utc)

    notes[note_id] = {
        'body': body,
        'timestamp': now.isoformat()
    }
    save_notes(notes)
    return jsonify({'message': 'Note updated'})

@app.route('/notes/<note_id>', methods=['DELETE'])
def delete_note(note_id):
    valid, error, code = check_password()
    if not valid:
        return jsonify({"error": error}), code

    notes = load_notes()
    if note_id not in notes:
        return jsonify({"error": "Note not found"}), 404

    del notes[note_id]
    save_notes(notes)
    return jsonify({'message': 'Note deleted'})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
