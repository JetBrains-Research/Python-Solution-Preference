from flask import Flask, request, jsonify, abort

app = Flask(__name__)

# Fixed columns
COLUMNS = ["Backlog", "In Progress", "Review", "Done"]
# Allowed story points (as strings for easy JSON handling)
ALLOWED_POINTS = {"", "1", "2", "3", "5", "8", "13"}

# In‑memory store
cards = {}
next_id = 1

def validate_card_data(data, require_title=True):
    title = data.get('title')
    if require_title and (title is None or str(title).strip() == ''):
        abort(400, description="Title is required and cannot be empty.")
    # Story points validation
    sp = data.get('story_points')
    if sp is not None and str(sp) not in ALLOWED_POINTS:
        abort(400, description="Invalid story points.")
    # Column validation
    status = data.get('status')
    if status and status not in COLUMNS:
        abort(400, description="Invalid status/column.")
    return title, data.get('description'), sp, status

@app.route('/cards', methods=['GET'])
def list_cards():
    # Return all cards grouped by column
    result = {col: [] for col in COLUMNS}
    for cid, card in cards.items():
        result[card['status']].append({'id': cid, **card})
    return jsonify(result)

@app.route('/cards', methods=['POST'])
def create_card():
    global next_id
    data = request.get_json(force=True)
    # Expect a 'status' field indicating the column
    status = data.get('status')
    if status not in COLUMNS:
        abort(400, description="Invalid or missing status column.")
    title, description, sp, _ = validate_card_data(data)
    card = {
        'title': title,
        'description': description,
        'story_points': sp,
        'status': status
    }
    cid = str(next_id)
    next_id += 1
    cards[cid] = card
    return jsonify({'id': cid, **card}), 201

@app.route('/cards/<card_id>', methods=['PUT'])
def edit_card(card_id):
    if card_id not in cards:
        abort(404, description="Card not found.")
    data = request.get_json(force=True)
    # Validate but title not required for updates
    title, description, sp, status = validate_card_data(data, require_title=False)
    card = cards[card_id]
    if title is not None:
        if str(title).strip() == '':
            abort(400, description="Title cannot be empty.")
        card['title'] = title
    if 'description' in data:
        card['description'] = description
    if 'story_points' in data:
        card['story_points'] = sp
    if status:
        if status not in COLUMNS:
            abort(400, description="Invalid status.")
        card['status'] = status
    return jsonify({'id': card_id, **card})

@app.route('/cards/<card_id>', methods=['DELETE'])
def delete_card(card_id):
    if card_id not in cards:
        abort(404, description="Card not found.")
    del cards[card_id]
    return '', 204

@app.route('/clear_done', methods=['POST'])
def clear_done():
    to_delete = [cid for cid, c in cards.items() if c['status'] == "Done"]
    for cid in to_delete:
        del cards[cid]
    return '', 204

if __name__ == '__main__':
    # Run on default port 5000
    app.run(host='0.0.0.0', port=5000)
