import csv
import os
import random
import time
import uuid
from flask import Flask, jsonify, request

app = Flask(__name__)

CSV_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "questions.csv")

# In-memory session storage
GAMES = {}

REQUIRED_COLUMNS = ["question", "option_a", "option_b", "option_c", "option_d",
                    "correct_option", "explanation", "category"]


def load_questions():
    questions = []
    with open(CSV_PATH, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            q = {col: row.get(col, "").strip() for col in REQUIRED_COLUMNS}
            if q["question"] and q["category"]:
                questions.append(q)
    return questions


def get_categories():
    qs = load_questions()
    cats = sorted({q["category"] for q in qs})
    return cats


def sample_questions(category, n=10):
    qs = [q for q in load_questions() if q["category"] == category]
    random.shuffle(qs)
    return qs[:n]


def build_question_payload(game):
    idx = game["current_index"]
    total = len(game["questions"])
    if idx >= total:
        return None
    q = game["questions"][idx]
    return {
        "question": q["question"],
        "options": {
            "A": q["option_a"],
            "B": q["option_b"],
            "C": q["option_c"],
            "D": q["option_d"],
        },
        "progress": f"Question {idx + 1} of {total}",
        "question_number": idx + 1,
        "total_questions": total,
    }


def new_game(category):
    questions = sample_questions(category, 10)
    game_id = str(uuid.uuid4())
    GAMES[game_id] = {
        "id": game_id,
        "category": category,
        "questions": questions,
        "current_index": 0,
        "correct_count": 0,
        "consecutive_correct": 0,
        "max_consecutive_correct": 0,
        "start_time": time.time(),
        "end_time": None,
        "finished": False,
        "answers": [],
    }
    return GAMES[game_id]


def compute_achievements(game):
    achievements = []
    total = len(game["questions"])
    if total == 10 and game["correct_count"] == 10:
        achievements.append("Perfect Round")
    if game["max_consecutive_correct"] >= 5:
        achievements.append("Hot Streak")
    if game["max_consecutive_correct"] >= 3:
        achievements.append("Triple Win")
    return achievements


def results_payload(game):
    total = len(game["questions"])
    correct = game["correct_count"]
    pct = int(round((correct / total) * 100)) if total > 0 else 0
    elapsed = (game["end_time"] or time.time()) - game["start_time"]
    achievements = compute_achievements(game)
    return {
        "score": f"{correct}/{total} Correct ({pct}%)",
        "correct": correct,
        "total": total,
        "percentage": pct,
        "elapsed_seconds": round(elapsed, 2),
        "max_consecutive_correct": game["max_consecutive_correct"],
        "achievements": achievements if achievements else [],
        "achievements_message": None if achievements else "No achievements this round",
        "category": game["category"],
    }


@app.route("/categories", methods=["GET"])
def categories_endpoint():
    cats = get_categories()
    return jsonify({
        "categories": cats + ["Surprise Me!"],
    })


@app.route("/game/start", methods=["POST"])
def start_game():
    data = request.get_json(force=True, silent=True) or {}
    category = data.get("category")
    proceed_anyway = bool(data.get("proceed_anyway", False))

    if not category:
        return jsonify({"error": "category is required"}), 400

    all_categories = get_categories()

    surprise_selected = None
    if category == "Surprise Me!":
        category = random.choice(all_categories)
        surprise_selected = category
    elif category not in all_categories:
        return jsonify({"error": f"Unknown category: {category}"}), 400

    available = [q for q in load_questions() if q["category"] == category]
    warning = None
    if len(available) < 10:
        warning = "Not enough questions in this category for all accomplishments"
        if not proceed_anyway:
            resp = {
                "warning": warning,
                "category": category,
                "available_questions": len(available),
                "message": "Set proceed_anyway=true to start the game anyway",
            }
            if surprise_selected:
                resp["surprise_selected_category"] = surprise_selected
            return jsonify(resp), 200

    game = new_game(category)
    payload = {
        "game_id": game["id"],
        "category": category,
        "total_questions": len(game["questions"]),
        "question": build_question_payload(game),
    }
    if surprise_selected:
        payload["surprise_selected_category"] = surprise_selected
    if warning:
        payload["warning"] = warning
    return jsonify(payload)


@app.route("/game/<game_id>/question", methods=["GET"])
def get_question(game_id):
    game = GAMES.get(game_id)
    if not game:
        return jsonify({"error": "Game not found"}), 404
    if game["finished"]:
        return jsonify({"error": "Game already finished", "results": results_payload(game)}), 400
    q = build_question_payload(game)
    if q is None:
        return jsonify({"error": "No more questions"}), 400
    return jsonify(q)


@app.route("/game/<game_id>/answer", methods=["POST"])
def submit_answer(game_id):
    game = GAMES.get(game_id)
    if not game:
        return jsonify({"error": "Game not found"}), 404
    if game["finished"]:
        return jsonify({"error": "Game already finished"}), 400

    data = request.get_json(force=True, silent=True) or {}
    answer = str(data.get("answer", "")).strip().upper()
    if answer not in {"A", "B", "C", "D"}:
        return jsonify({"error": "answer must be A, B, C, or D"}), 400

    idx = game["current_index"]
    q = game["questions"][idx]
    correct_option = q["correct_option"].strip().upper()
    is_correct = answer == correct_option

    if is_correct:
        game["correct_count"] += 1
        game["consecutive_correct"] += 1
        game["max_consecutive_correct"] = max(
            game["max_consecutive_correct"], game["consecutive_correct"]
        )
    else:
        game["consecutive_correct"] = 0

    game["answers"].append({
        "question": q["question"],
        "submitted": answer,
        "correct": correct_option,
        "is_correct": is_correct,
    })

    feedback = "Correct!" if is_correct else "Incorrect"

    game["current_index"] += 1
    finished = game["current_index"] >= len(game["questions"])

    response = {
        "feedback": feedback,
        "is_correct": is_correct,
        "correct_answer": correct_option,
        "correct_answer_text": q[f"option_{correct_option.lower()}"],
        "explanation": q["explanation"],
        "consecutive_correct": game["consecutive_correct"],
        "max_consecutive_correct": game["max_consecutive_correct"],
    }

    if finished:
        game["finished"] = True
        game["end_time"] = time.time()
        response["game_over"] = True
        response["results"] = results_payload(game)
    else:
        response["game_over"] = False
        response["next_question"] = build_question_payload(game)

    return jsonify(response)


@app.route("/game/<game_id>/results", methods=["GET"])
def get_results(game_id):
    game = GAMES.get(game_id)
    if not game:
        return jsonify({"error": "Game not found"}), 404
    if not game["finished"]:
        return jsonify({"error": "Game not finished yet"}), 400
    return jsonify(results_payload(game))


@app.route("/game/<game_id>/play_again", methods=["POST"])
def play_again(game_id):
    game = GAMES.get(game_id)
    if not game:
        return jsonify({"error": "Game not found"}), 404
    category = game["category"]
    new = new_game(category)
    return jsonify({
        "game_id": new["id"],
        "category": category,
        "total_questions": len(new["questions"]),
        "question": build_question_payload(new),
    })


@app.route("/game/new_category", methods=["POST"])
def new_category():
    return start_game()


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=False)
