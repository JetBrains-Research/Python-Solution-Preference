import json
import os
import re
from flask import Flask, request, jsonify

app = Flask(__name__)

STATE_FILE = 'state.json'
QUESTIONS_FILE = 'assets/questions.json'

def load_json(filename):
    if os.path.exists(filename):
        with open(filename, 'r') as f:
            return json.load(f)
    return {}

def save_json(filename, data):
    with open(filename, 'w') as f:
        json.dump(data, f, indent=2)

def get_initial_state():
    return {
        "lessons": {
            "Lesson 1": {
                "status": "Not started",
                "position": 0,
                "score": 0,
                "unlocked": True
            },
            "Lesson 2": {
                "status": "Locked",
                "position": 0,
                "score": 0,
                "unlocked": False
            }
        }
    }

def normalize_text(text):
    if not text:
        return ""
    # Trim whitespace, lowercase, remove punctuation
    text = text.strip().lower()
    text = re.sub(r'[^\w\s]', '', text)
    return text

def get_state():
    state = load_json(STATE_FILE)
    if not state:
        state = get_initial_state()
        save_json(STATE_FILE, state)
    return state

@app.route('/reset', methods=['POST'])
def reset_state():
    state = get_initial_state()
    save_json(STATE_FILE, state)
    return jsonify({"message": "State reset to defaults"}), 200

@app.route('/lessons', methods=['GET'])
def get_lessons():
    state = get_state()
    lessons_info = {}
    for name, data in state["lessons"].items():
        if data["status"] == "Locked":
            lessons_info[name] = "Locked: Complete Lesson 1 with at least 4/5 correct to unlock."
        else:
            lessons_info[name] = data["status"]
    return jsonify(lessons_info), 200

@app.route('/lesson/<lesson_id>/start', methods=['POST'])
def start_lesson(lesson_id):
    name = f"Lesson {lesson_id}"
    state = get_state()
    if name not in state["lessons"]:
        return jsonify({"error": "Lesson not found"}), 404
    
    lesson = state["lessons"][name]
    if not lesson["unlocked"]:
        return jsonify({"error": "Lesson is locked"}), 403
    
    lesson["status"] = "In progress"
    lesson["position"] = 0
    lesson["score"] = 0
    save_json(STATE_FILE, state)
    
    return get_exercise(lesson_id, 0)

@app.route('/lesson/<lesson_id>/exercise/<int:pos>', methods=['GET'])
def get_exercise_by_pos(lesson_id, pos):
    return get_exercise(lesson_id, pos)

def get_exercise(lesson_id, pos):
    state = get_state()
    name = f"Lesson {lesson_id}"
    lesson = state["lessons"][name]
    
    if pos < 0 or pos >= 5:
        return jsonify({"error": "Invalid exercise position"}), 400
    
    if pos > lesson["position"]:
        return jsonify({"error": "Exercise locked. Complete previous exercises first."}), 403

    questions = load_json(QUESTIONS_FILE)
    # Map: Lesson 1 -> mc_1, match_1, etc.
    types = ["mc", "match", "order", "fill", "typed"]
    q_id = f"{types[pos]}_{lesson_id}"
    question_data = questions.get(q_id)
    
    if not question_data:
        return jsonify({"error": "Question data not found"}), 404

    # Handle Matching Pairs English alphabetical order
    if question_data["type"] == "matching_pairs":
        response_data = question_data.copy()
        response_data["english"] = sorted(question_data["english"])
        # Remove correct_pairs from response
        response_data.pop("correct_pairs", None)
        return jsonify({
            "exercise_index": pos + 1,
            "total_exercises": 5,
            "data": response_data
        }), 200

    return jsonify({
        "exercise_index": pos + 1,
        "total_exercises": 5,
        "data": question_data
    }), 200

@app.route('/lesson/<lesson_id>/submit', methods=['POST'])
def submit_answer(lesson_id):
    data = request.json
    pos = data.get("position")
    answer = data.get("answer")
    
    state = get_state()
    name = f"Lesson {lesson_id}"
    lesson = state["lessons"][name]
    
    if pos is None or pos < 0 or pos >= 5:
        return jsonify({"error": "Invalid position"}), 400
    if pos != lesson["position"]:
        return jsonify({"error": "Wrong exercise position"}), 400

    questions = load_json(QUESTIONS_FILE)
    types = ["mc", "match", "order", "fill", "typed"]
    q_id = f"{types[pos]}_{lesson_id}"
    q = questions.get(q_id)
    
    correct = False
    feedback = {}

    if q["type"] == "multiple_choice":
        correct = (answer == q["correct_answer"])
        feedback = {"correct": correct, "explanation": q["explanation"]}
    
    elif q["type"] == "matching_pairs":
        # answer should be a dict {spanish: english}
        correct = True
        pair_feedback = {}
        for s_word in q["spanish"]:
            user_match = answer.get(s_word)
            is_pair_correct = (user_match == q["correct_pairs"].get(s_word))
            if not is_pair_correct:
                correct = False
            pair_feedback[s_word] = "Correct" if is_pair_correct else "Incorrect"
        feedback = {"correct": correct, "pairs": pair_feedback}

    elif q["type"] == "word_ordering":
        correct = (answer == q["correct_order"])
        feedback = {
            "correct": correct,
            "correct_sentence": " ".join(q["correct_order"]),
            "translation": q["translation"],
            "explanation": q["explanation"]
        }

    elif q["type"] == "fill_in_the_blank":
        correct = (answer == q["correct_answer"])
        feedback = {"correct": correct}

    elif q["type"] == "typed_translation":
        norm_answer = normalize_text(answer)
        correct = any(normalize_text(ca) == norm_answer for ca in q["correct_answers"])
        feedback = {"correct": correct}

    if correct:
        lesson["score"] += 1

    # Progress to next
    if pos < 4:
        lesson["position"] += 1
        save_json(STATE_FILE, state)
        return jsonify({"correct": correct, "feedback": feedback, "next": True})
    else:
        # Lesson complete
        score = lesson["score"]
        percent = int((score / 5) * 100)
        status_msg = f"Completed - {score}/5 correct ({percent}%)"
        lesson["status"] = status_msg
        
        # Unlock Lesson 2 if Lesson 1 is finished with >= 4/5
        if lesson_id == "1" and score >= 4:
            state["lessons"]["Lesson 2"]["unlocked"] = True
            state["lessons"]["Lesson 2"]["status"] = "Not started"
            
        save_json(STATE_FILE, state)
        return jsonify({
            "correct": correct, 
            "feedback": feedback, 
            "lesson_complete": True, 
            "final_score": status_msg
        }), 200

@app.route('/lesson/<lesson_id>/exit', methods=['POST'])
def exit_lesson(lesson_id):
    # Position is already saved on every submit
    return jsonify({"message": "Progress saved"}), 200

if __name__ == '__main__':
    app.run(port=5000)
