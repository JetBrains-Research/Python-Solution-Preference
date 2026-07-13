import uuid
from flask import Flask, request, jsonify

app = Flask(__name__)

VALID_COLUMNS = ["Backlog", "In Progress", "Review", "Done"]
VALID_POINTS = [None, 1, 2, 3, 5, 8, 13]

# In-memory storage
board = {col: [] for col in VALID_COLUMNS}
cards = {}  # card_id -> card dict
users = {}  # user_id -> display_name


def find_card_column(card_id):
    for col, card_list in board.items():
        for c in card_list:
            if c["id"] == card_id:
                return col
    return None


def require_user():
    """Check request has a valid user (via header or query/body)."""
    user_id = request.headers.get("X-User-Id")
    if not user_id or user_id not in users:
        return None
    return user_id


def validate_points(points):
    if points is None or points == "":
        return True, None
    try:
        p = int(points)
    except (ValueError, TypeError):
        return False, None
    if p not in [1, 2, 3, 5, 8, 13]:
        return False, None
    return True, p


@app.route("/users", methods=["POST"])
def create_user():
    data = request.get_json(silent=True) or {}
    name = data.get("display_name", "").strip() if isinstance(data.get("display_name", ""), str) else ""
    if not name:
        return jsonify({"error": "display_name is required"}), 400
    user_id = str(uuid.uuid4())
    users[user_id] = name
    return jsonify({"user_id": user_id, "display_name": name}), 201


@app.route("/board", methods=["GET"])
def get_board():
    if require_user() is None:
        return jsonify({"error": "authentication required: provide X-User-Id header for a registered user"}), 401
    result = {"columns": []}
    for col in VALID_COLUMNS:
        result["columns"].append({
            "name": col,
            "cards": list(board[col]),
        })
    return jsonify(result)


@app.route("/cards", methods=["POST"])
def create_card():
    if require_user() is None:
        return jsonify({"error": "authentication required"}), 401
    data = request.get_json(silent=True) or {}
    title = data.get("title", "")
    if not isinstance(title, str) or not title.strip():
        return jsonify({"error": "title is required"}), 400
    description = data.get("description", "") or ""
    status = data.get("status", "Backlog")
    if status not in VALID_COLUMNS:
        return jsonify({"error": f"status must be one of {VALID_COLUMNS}"}), 400
    ok, points = validate_points(data.get("story_points"))
    if not ok:
        return jsonify({"error": "story_points must be blank or one of 1,2,3,5,8,13"}), 400
    card = {
        "id": str(uuid.uuid4()),
        "title": title.strip(),
        "description": description,
        "story_points": points,
        "status": status,
    }
    cards[card["id"]] = card
    board[status].append(card)
    return jsonify(card), 201


@app.route("/cards/<card_id>", methods=["GET"])
def get_card(card_id):
    if require_user() is None:
        return jsonify({"error": "authentication required"}), 401
    if card_id not in cards:
        return jsonify({"error": "card not found"}), 404
    return jsonify(cards[card_id])


@app.route("/cards/<card_id>", methods=["PATCH", "PUT"])
def update_card(card_id):
    if require_user() is None:
        return jsonify({"error": "authentication required"}), 401
    if card_id not in cards:
        return jsonify({"error": "card not found"}), 404
    data = request.get_json(silent=True) or {}
    card = cards[card_id]

    if "title" in data:
        title = data["title"]
        if not isinstance(title, str) or not title.strip():
            return jsonify({"error": "title cannot be empty"}), 400
        card["title"] = title.strip()

    if "description" in data:
        card["description"] = data["description"] or ""

    if "story_points" in data:
        ok, points = validate_points(data["story_points"])
        if not ok:
            return jsonify({"error": "story_points must be blank or one of 1,2,3,5,8,13"}), 400
        card["story_points"] = points

    if "status" in data:
        new_status = data["status"]
        if new_status not in VALID_COLUMNS:
            return jsonify({"error": f"status must be one of {VALID_COLUMNS}"}), 400
        old_col = find_card_column(card_id)
        if old_col != new_status:
            board[old_col] = [c for c in board[old_col] if c["id"] != card_id]
            board[new_status].append(card)
        card["status"] = new_status

    return jsonify(card)


@app.route("/cards/<card_id>", methods=["DELETE"])
def delete_card(card_id):
    if require_user() is None:
        return jsonify({"error": "authentication required"}), 401
    if card_id not in cards:
        return jsonify({"error": "card not found"}), 404
    col = find_card_column(card_id)
    board[col] = [c for c in board[col] if c["id"] != card_id]
    del cards[card_id]
    return "", 204


@app.route("/board/clear-done", methods=["POST"])
def clear_done():
    if require_user() is None:
        return jsonify({"error": "authentication required"}), 401
    done_cards = board["Done"]
    for c in done_cards:
        cards.pop(c["id"], None)
    count = len(done_cards)
    board["Done"] = []
    return jsonify({"cleared": count})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
