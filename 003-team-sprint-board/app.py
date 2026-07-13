from flask import Flask, request, jsonify, abort
import uuid

app = Flask(__name__)

# In-memory storage
# board = { "Backlog": [], "In Progress": [], "Review": [], "Done": [] }
# cards = { card_id: { ...card_data... } }
board_columns = ["Backlog", "In Progress", "Review", "Done"]
cards = {}

VALID_STORY_POINTS = {None, 1, 2, 3, 5, 8, 13}

def get_user():
    user = request.headers.get('X-User-Name')
    if not user:
        abort(400, description="Display name is required in X-User-Name header")
    return user

@app.route('/board', methods=['GET'])
def get_board():
    get_user()
    result = {col: [] for col in board_columns}
    for card_id, card in cards.items():
        col = card['status']
        if col in result:
            card_copy = card.copy()
            card_copy['id'] = card_id
            result[col].append(card_copy)
    return jsonify(result)

@app.route('/cards', methods=['POST'])
def create_card():
    get_user()
    data = request.json or {}
    column = data.get('column')
    title = data.get('title')
    description = data.get('description', '')
    story_points = data.get('story_points')

    if column not in board_columns:
        abort(400, description="Invalid column")
    if not title:
        abort(400, description="Title is required")
    
    # Validate story points
    if story_points is not None and story_points not in VALID_STORY_POINTS:
        abort(400, description="Invalid story points. Allowed: 1, 2, 3, 5, 8, 13 or blank")

    card_id = str(uuid.uuid4())
    cards[card_id] = {
        'title': title,
        'description': description,
        'story_points': story_points,
        'status': column
    }
    return jsonify({'id': card_id}), 201

@app.route('/cards/<card_id>', methods=['PUT'])
def update_card(card_id):
    get_user()
    if card_id not in cards:
        abort(404, description="Card not found")
    
    data = request.json or {}
    card = cards[card_id]
    
    title = data.get('title', card['title'])
    if not title:
        abort(400, description="Title is required")
    
    description = data.get('description', card['description'])
    story_points = data.get('story_points', card['story_points'])
    status = data.get('status', card['status'])
    
    if status not in board_columns:
        abort(400, description="Invalid status")
    
    if story_points is not None and story_points not in VALID_STORY_POINTS:
        abort(400, description="Invalid story points. Allowed: 1, 2, 3, 5, 8, 13 or blank")
        
    card.update({
        'title': title,
        'description': description,
        'story_points': story_points,
        'status': status
    })
    
    return jsonify(card)

@app.route('/cards/<card_id>', methods=['DELETE'])
def delete_card(card_id):
    get_user()
    if card_id not in cards:
        abort(404, description="Card not found")
    del cards[card_id]
    return '', 204

@app.route('/board/done', methods=['DELETE'])
def clear_done():
    get_user()
    to_delete = [card_id for card_id, card in cards.items() if card['status'] == 'Done']
    for card_id in to_delete:
        del cards[card_id]
    return '', 204

if __name__ == '__main__':
    app.run(debug=True, port=5000)
