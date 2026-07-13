import json
import os
import re
from flask import Flask, request, jsonify

app = Flask(__name__)

# Paths
QUESTIONS_FILE = os.path.join('assets', 'questions.json')
STATE_FILE = 'state.json'

# Default state
DEFAULT_STATE = {
    "lessons": {
        "1": {
            "status": "Not started",
            "current_exercise": 0,
            "completed": False,
            "scores": []
        },
        "2": {
            "status": "Locked",
            "current_exercise": 0,
            "completed": False,
            "scores": []
        }
    },
    "unlocked": {"2": False}
}

def load_questions():
    with open(QUESTIONS_FILE, 'r') as f:
        return json.load(f)

def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, 'r') as f:
            return json.load(f)
    return DEFAULT_STATE

def save_state(state):
    with open(STATE_FILE, 'w') as f:
        json.dump(state, f, indent=2)

def normalize_text(text):
    text = text.strip().lower()
    text = re.sub(r'[^\w\s]', '', text)
    return text

def get_lesson_status(lesson_id, state):
    lesson = state['lessons'][lesson_id]
    if lesson_id == '2' and not state['unlocked'].get('2', False):
        return "Locked"
    if not lesson['completed']:
        if lesson['scores']:
            return "In progress"
        return "Not started"
    # Completed
    scores = lesson['scores']
    if scores:
        last_score = scores[-1]
        correct = last_score['correct']
        total = last_score['total']
        pct = int(round(correct / total * 100))
        return f"Completed - {correct}/{total} correct ({pct}%)"
    return "Completed"

@app.route('/api/lessons', methods=['GET'])
def get_lessons():
    state = load_state()
    result = {}
    for lesson_id in ['1', '2']:
        status = get_lesson_status(lesson_id, state)
        lesson_info = {
            "id": lesson_id,
            "name": f"Lesson {lesson_id}",
            "status": status
        }
        if lesson_id == '2' and not state['unlocked'].get('2', False):
            lesson_info['unlock_message'] = "Complete Lesson 1 with at least 4/5 correct to unlock."
        result[lesson_id] = lesson_info
    return jsonify(result)

@app.route('/api/lesson/<lesson_id>', methods=['GET'])
def get_lesson(lesson_id):
    if lesson_id not in ['1', '2']:
        return jsonify({"error": "Lesson not found"}), 404
    state = load_state()
    questions = load_questions()
    status = get_lesson_status(lesson_id, state)
    lesson = state['lessons'][lesson_id]
    
    result = {
        "id": lesson_id,
        "name": f"Lesson {lesson_id}",
        "status": status,
        "current_exercise": lesson['current_exercise'] + 1 if lesson['current_exercise'] < 5 else 5,
        "total_exercises": 5
    }
    if lesson_id == '2' and not state['unlocked'].get('2', False):
        result['unlock_message'] = "Complete Lesson 1 with at least 4/5 correct to unlock."
    return jsonify(result)

@app.route('/api/lesson/<lesson_id>/start', methods=['POST'])
def start_lesson(lesson_id):
    if lesson_id not in ['1', '2']:
        return jsonify({"error": "Lesson not found"}), 404
    state = load_state()
    questions = load_questions()
    
    if lesson_id == '2' and not state['unlocked'].get('2', False):
        # Check if lesson 1 unlocks it
        lesson1 = state['lessons']['1']
        if lesson1['completed'] and lesson1['scores']:
            last = lesson1['scores'][-1]
            if last['correct'] >= 4:
                state['unlocked']['2'] = True
                save_state(state)
        if not state['unlocked'].get('2', False):
            return jsonify({"error": "Complete Lesson 1 with at least 4/5 correct to unlock."}), 403
    
    # Reset lesson to start from beginning
    lesson = state['lessons'][lesson_id]
    lesson['current_exercise'] = 0
    lesson['scores'] = []  # Start fresh attempt
    lesson['completed'] = False
    state['lessons'][lesson_id] = lesson
    save_state(state)
    
    # Return first exercise
    exercise = questions['lessons'][lesson_id]['exercises'][0]
    return jsonify({
        "message": f"Lesson {lesson_id} started",
        "exercise": exercise,
        "exercise_number": 1,
        "total_exercises": 5
    })

@app.route('/api/lesson/<lesson_id>/exercise', methods=['POST'])
def submit_exercise(lesson_id):
    if lesson_id not in ['1', '2']:
        return jsonify({"error": "Lesson not found"}), 404
    state = load_state()
    questions = load_questions()
    
    if lesson_id == '2' and not state['unlocked'].get('2', False):
        return jsonify({"error": "Lesson is locked"}), 403
    
    lesson = state['lessons'][lesson_id]
    current_idx = lesson['current_exercise']
    if current_idx >= 5:
        return jsonify({"error": "Lesson already completed. Start a new attempt."}), 400
    
    exercise = questions['lessons'][lesson_id]['exercises'][current_idx]
    data = request.get_json()
    
    result = None
    is_correct = False
    
    ex_type = exercise['type']
    if ex_type == 'multiple_choice':
        answer = data.get('answer')
        is_correct = (answer == exercise['correct_answer'])
        result = {
            "correct": is_correct,
            "correct_answer": exercise['correct_answer'],
            "explanation": exercise['explanation']
        }
    elif ex_type == 'matching_pairs':
        pairs = data.get('pairs', {})
        correct_pairs = exercise['correct_pairs']
        all_correct = True
        pair_feedback = {}
        for sw, ew in correct_pairs.items():
            user_ew = pairs.get(sw, '')
            is_pair_correct = (user_ew == ew)
            if not is_pair_correct:
                all_correct = False
            pair_feedback[sw] = {
                "your_answer": user_ew,
                "correct_answer": ew,
                "correct": is_pair_correct
            }
        is_correct = all_correct
        result = {
            "correct": is_correct,
            "pair_feedback": pair_feedback
        }
    elif ex_type == 'word_ordering':
        order = data.get('order', [])
        is_correct = (order == exercise['correct_order'])
        result = {
            "correct": is_correct,
            "correct_order": exercise['correct_order'],
            "translation": exercise['translation'],
            "explanation": exercise['explanation']
        }
    elif ex_type == 'fill_in_the_blank':
        answer = data.get('answer')
        is_correct = (answer == exercise['correct_answer'])
        result = {
            "correct": is_correct,
            "correct_answer": exercise['correct_answer']
        }
    elif ex_type == 'typed_translation':
        answer = data.get('answer', '')
        normalized = normalize_text(answer)
        is_correct = any(normalized == normalize_text(ca) for ca in exercise['correct_answers'])
        result = {
            "correct": is_correct,
            "acceptable_answers": exercise['correct_answers']
        }
    
    # Record score
    lesson['scores'].append({
        "exercise": current_idx + 1,
        "correct": is_correct
    })
    
    # Move to next exercise
    current_idx += 1
    lesson['current_exercise'] = current_idx
    if current_idx >= 5:
        lesson['completed'] = True
        # Calculate score
        correct_count = sum(1 for s in lesson['scores'] if s['correct'])
        total = len(lesson['scores'])
        pct = int(round(correct_count / total * 100))
        lesson['scores'] = [{"correct": correct_count, "total": total}]
        
        # Check if Lesson 1 completion unlocks Lesson 2
        if lesson_id == '1' and correct_count >= 4:
            state['unlocked']['2'] = True
        
        state['lessons'][lesson_id] = lesson
        save_state(state)
        
        result['lesson_complete'] = True
        result['summary'] = {
            "lesson": f"Lesson {lesson_id}",
            "correct": correct_count,
            "total": total,
            "percentage": pct,
            "message": f"Lesson {lesson_id}: {correct_count}/{total} correct ({pct}%)"
        }
        return jsonify(result)
    
    # Return next exercise
    state['lessons'][lesson_id] = lesson
    save_state(state)
    
    next_exercise = questions['lessons'][lesson_id]['exercises'][current_idx]
    result['next_exercise'] = next_exercise
    result['exercise_number'] = current_idx + 1
    result['total_exercises'] = 5
    
    return jsonify(result)

@app.route('/api/lesson/<lesson_id>/exit', methods=['POST'])
def exit_lesson(lesson_id):
    if lesson_id not in ['1', '2']:
        return jsonify({"error": "Lesson not found"}), 404
    state = load_state()
    
    lesson = state['lessons'][lesson_id]
    # Save current position
    state['lessons'][lesson_id] = lesson
    save_state(state)
    
    return jsonify({
        "message": f"Exited Lesson {lesson_id}. Progress saved at Exercise {lesson['current_exercise'] + 1} of 5.",
        "current_exercise": lesson['current_exercise'] + 1 if lesson['current_exercise'] < 5 else 5
    })

@app.route('/api/lesson/<lesson_id>/current', methods=['GET'])
def get_current_exercise(lesson_id):
    if lesson_id not in ['1', '2']:
        return jsonify({"error": "Lesson not found"}), 404
    state = load_state()
    questions = load_questions()
    
    if lesson_id == '2' and not state['unlocked'].get('2', False):
        return jsonify({"error": "Lesson is locked"}), 403
    
    lesson = state['lessons'][lesson_id]
    current_idx = lesson['current_exercise']
    if current_idx >= 5:
        return jsonify({"message": "Lesson completed", "completed": True})
    
    exercise = questions['lessons'][lesson_id]['exercises'][current_idx]
    return jsonify({
        "exercise": exercise,
        "exercise_number": current_idx + 1,
        "total_exercises": 5
    })

@app.route('/api/reset', methods=['POST'])
def reset_state():
    state = DEFAULT_STATE.copy()
    state['lessons'] = {
        "1": DEFAULT_STATE['lessons']['1'].copy(),
        "2": DEFAULT_STATE['lessons']['2'].copy()
    }
    state['unlocked'] = DEFAULT_STATE['unlocked'].copy()
    save_state(state)
    return jsonify({"message": "State reset to defaults"})

if __name__ == '__main__':
    app.run(debug=True, port=5000)
