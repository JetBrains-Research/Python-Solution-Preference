import csv
import random
import time
import uuid
from flask import Flask, request, jsonify

app = Flask(__name__)

# Store session data in memory
sessions = {}

def load_questions():
    questions = []
    with open('assets/questions.csv', mode='r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            questions.append(row)
    return questions

def get_all_categories():
    questions = load_questions()
    return sorted(list(set(q['category'] for q in questions)))

@app.route('/categories', methods=['GET'])
def list_categories():
    categories = get_all_categories()
    return jsonify({"categories": categories + ["Surprise Me!"]})

@app.route('/start', methods=['POST'])
def start_game():
    data = request.json
    category = data.get('category')
    
    all_questions = load_questions()
    available_categories = get_all_categories()
    
    if category == "Surprise Me!":
        category = random.choice(available_categories)
    
    if category not in available_categories:
        return jsonify({"error": "Invalid category"}), 400
    
    category_questions = [q for q in all_questions if q['category'] == category]
    
    warning = None
    if len(category_questions) < 10:
        warning = "Not enough questions in this category for all accomplishments"
    
    # Sample up to 10 questions
    num_to_sample = min(10, len(category_questions))
    selected_questions = random.sample(category_questions, num_to_sample)
    
    session_id = str(uuid.uuid4())
    sessions[session_id] = {
        "category": category,
        "questions": selected_questions,
        "current_index": 0,
        "score": 0,
        "max_consecutive": 0,
        "current_consecutive": 0,
        "start_time": time.time(),
        "finished": False
    }
    
    return jsonify({
        "session_id": session_id,
        "category": category,
        "warning": warning,
        "total_questions": num_to_sample,
        "first_question": get_question_data(session_id)
    })

def get_question_data(session_id):
    session = sessions[session_id]
    idx = session['current_index']
    if idx >= len(session['questions']):
        return None
    
    q = session['questions'][idx]
    return {
        "question": q['question'],
        "options": {
            "A": q['option_a'],
            "B": q['option_b'],
            "C": q['option_c'],
            "D": q['option_d']
        },
        "progress": f"Question {idx + 1} of {len(session['questions'])}"
    }

@app.route('/answer', methods=['POST'])
def submit_answer():
    data = request.json
    session_id = data.get('session_id')
    answer = data.get('answer') # A, B, C, or D
    
    if session_id not in sessions:
        return jsonify({"error": "Session not found"}), 404
    
    session = sessions[session_id]
    if session['finished']:
        return jsonify({"error": "Game already finished"}), 400
    
    idx = session['current_index']
    question = session['questions'][idx]
    correct_option = question['correct_option']
    
    is_correct = (answer == correct_option)
    
    if is_correct:
        session['score'] += 1
        session['current_consecutive'] += 1
        session['max_consecutive'] = max(session['max_consecutive'], session['current_consecutive'])
    else:
        session['current_consecutive'] = 0
        
    feedback = "Correct!" if is_correct else "Incorrect"
    explanation = question['explanation']
    
    session['current_index'] += 1
    
    if session['current_index'] >= len(session['questions']):
        session['finished'] = True
        return jsonify({
            "feedback": feedback,
            "correct_answer": correct_option,
            "explanation": explanation,
            "game_over": True,
            "results": get_results(session_id)
        })
    else:
        return jsonify({
            "feedback": feedback,
            "correct_answer": correct_option,
            "explanation": explanation,
            "game_over": False,
            "next_question": get_question_data(session_id)
        })

def get_results(session_id):
    session = sessions[session_id]
    total = len(session['questions'])
    score = session['score']
    percentage = (score / total * 100) if total > 0 else 0
    elapsed_time = int(time.time() - session['start_time'])
    
    achievements = []
    # Perfect Round: All correct (only possible with 10 questions)
    if total == 10 and score == 10:
        achievements.append("Perfect Round")
    # Hot Streak: Max consecutive >= 5
    if session['max_consecutive'] >= 5:
        achievements.append("Hot Streak")
    # Triple Win: Max consecutive >= 3
    if session['max_consecutive'] >= 3:
        achievements.append("Triple Win")
        
    return {
        "score": f"{score}/{total} Correct ({percentage:.1f}%)",
        "time_elapsed": f"{elapsed_time} seconds",
        "achievements": achievements if achievements else "No achievements this round"
    }

@app.route('/results', methods=['GET'])
def view_results():
    session_id = request.args.get('session_id')
    if session_id not in sessions or not sessions[session_id]['finished']:
        return jsonify({"error": "Session not found or game not finished"}), 404
    
    return jsonify(get_results(session_id))

if __name__ == '__main__':
    app.run(port=5001)
