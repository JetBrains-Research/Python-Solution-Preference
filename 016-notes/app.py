import json
import os
import uuid
from datetime import datetime, timezone
from flask import Flask, request, jsonify

app = Flask(__name__)

PASSWORD = "my-notes-are-mine"
STORAGE_FILE = "notes.json"

def load_notes():
    if os.path.exists(STORAGE_FILE):
        with open(STORAGE_FILE, "r", encoding="utf-8") as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                return {}
    return {}

def save_notes(notes):
    with open(STORAGE_FILE, "w", encoding="utf-8") as f:
        json.dump(notes, f, indent=2)

def get_current_timestamp():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")

def check_password():
    pw = request.headers.get("X-Password") or request.args.get("password")
    if pw is None:
        return jsonify({"error": "Password is required"}), 401
    if pw != PASSWORD:
        return jsonify({"error": "Incorrect password"}), 403
    return None

def extract_title(body):
    if body is None:
        return "New Note"
    for line in body.splitlines():
        stripped = line.strip()
        if stripped:
            return stripped
    return "New Note"

def extract_preview(body):
    if body is None:
        return ""
    lines = body.splitlines()
    title_found = False
    for line in lines:
        if not title_found:
            if line.strip():
                title_found = True
            continue
        stripped = line.strip()
        if stripped:
            preview = stripped
            if len(preview) > 80:
                preview = preview[:80] + "..."
            return preview
    return ""

def sort_notes_desc(notes_list):
    return sorted(notes_list, key=lambda x: x["timestamp"], reverse=True)

@app.before_request
def require_password():
    if request.endpoint in ("health", "static"):
        return None
    return check_password()

@app.route("/")
def health():
    return jsonify({"status": "ok"})

@app.route("/notes", methods=["GET"])
def list_notes():
    notes = load_notes()
    query = request.args.get("q", "").strip()
    result = []
    for nid, data in notes.items():
        body = data.get("body", "")
        title = extract_title(body)
        if query:
            if query.lower() not in title.lower() and query.lower() not in body.lower():
                continue
        result.append({
            "id": nid,
            "title": title,
            "preview": extract_preview(body),
            "timestamp": data.get("timestamp", "")
        })
    result = sort_notes_desc(result)
    return jsonify({"notes": result})

@app.route("/notes", methods=["POST"])
def create_note():
    notes = load_notes()
    nid = str(uuid.uuid4())
    now = get_current_timestamp()
    notes[nid] = {"body": "", "timestamp": now}
    save_notes(notes)
    return jsonify({"id": nid, "body": "", "timestamp": now}), 201

@app.route("/notes/<nid>", methods=["GET"])
def get_note(nid):
    notes = load_notes()
    if nid not in notes:
        return jsonify({"error": "Note not found"}), 404
    data = notes[nid]
    return jsonify({
        "id": nid,
        "body": data.get("body", ""),
        "timestamp": data.get("timestamp", "")
    })

@app.route("/notes/<nid>", methods=["PUT"])
def update_note(nid):
    notes = load_notes()
    if nid not in notes:
        return jsonify({"error": "Note not found"}), 404
    payload = request.get_json(force=True)
    body = payload.get("body")
    if body is None:
        return jsonify({"error": "Body is required"}), 400
    notes[nid] = {"body": body, "timestamp": get_current_timestamp()}
    save_notes(notes)
    return jsonify({
        "id": nid,
        "body": notes[nid]["body"],
        "timestamp": notes[nid]["timestamp"]
    })

@app.route("/notes/<nid>", methods=["DELETE"])
def delete_note(nid):
    notes = load_notes()
    if nid not in notes:
        return jsonify({"error": "Note not found"}), 404
    del notes[nid]
    save_notes(notes)
    return jsonify({"message": "Note deleted"}), 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080, debug=False)
