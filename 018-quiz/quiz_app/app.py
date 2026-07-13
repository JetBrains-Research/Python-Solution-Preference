import csv
import random
import time
from flask import Flask, request, jsonify, session

app = Flask(__name__)
app.secret_key = 'dev-secret-key-for-quiz-app'

def load_questions():
    questions = []
    with open('assets/questions.csv', 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            questions.append(row)
    return questions

def get_categories(questions):
    cats = set()
    for q in questions:
        cats.add(q['category'])
    return sorted(list(cats))

@app.route('/categories', methods=['GET'])
def categories():
    questions = load_questions()
    cats = get_categories(questions)
    return jsonify({
        'categories': cats,
        'surprise_me': True
    })

@app.route('/game/start', methods=['POST'])
def start_game():
    data = request.get_json()
    if not data or 'category' not in data:
        return jsonify({'error': 'Category is required'}), 400
    
    category = data['category']
    questions = load_questions()
    cats = get_categories(questions)
    
    # Handle "Surprise Me!"
    actual_category = category
    if category == 'Surprise Me!':
        actual_category = random.choice(cats)
    
    # Filter questions by category
    cat_questions = [q for q in questions if q['category'] == actual_category]
    
    # Check for warning
    warning = None
    if len(cat_questions) < 10:
        warning = 'Not enough questions in this category for all accomplishments'
    
    # Sample up to 10 questions (without replacement)
    num_questions = min(10, len(cat_questions))
    sampled = random.sample(cat_questions, num_questions)
    
    # Store game state in session
    session['category'] = actual_category
    session['questions'] = sampled
    session['current_index'] = 0
    session['score'] = 0
    session['total'] = num_questions
    session['consecutive_correct'] = 0
    session['max_consecutive_correct'] = 0
    session['start_time'] = time.time()
    session['answers'] = []
    session['surprise_category'] = (category == 'Surprise Me!')
    
    # Return first question
    q = sampled[0]
    return jsonify({
        'question': q['question'],
        'options': {
            'A': q['option_a'],
            'B': q['option_b'],
            'C': q['option_c'],
            'D': q['option_d']
        },
        'progress': f"Question 1 of {num_questions}",
        'category': actual_category,
        'warning': warning
    })

@app.route('/game/answer', methods=['POST'])
def answer():
    if 'questions' not in session:
        return jsonify({'error': 'No active game'}), 400
    
    data = request.get_json()
    if not data or 'answer' not in data:
        return jsonify({'error': 'Answer is required'}), 400
    
    user_answer = data['answer'].upper()
    idx = session['current_index']
    questions = session['questions']
    q = questions[idx]
    correct_option = q['correct_option']
    
    is_correct = (user_answer == correct_option)
    
    # Update score and streaks
    if is_correct:
        session['score'] += 1
        session['consecutive_correct'] += 1
        if session['consecutive_correct'] > session['max_consecutive_correct']:
            session['max_consecutive_correct'] = session['consecutive_correct']
    else:
        if session['consecutive_correct'] > session['max_consecutive_correct']:
            session['max_consecutive_correct'] = session['consecutive_correct']
        session['consecutive_correct'] = 0
    
    # Store answer
    session['answers'].append({
        'question': q['question'],
        'user_answer': user_answer,
        'correct_answer': correct_option,
        'is_correct': is_correct
    })
    
    # Advance index
    session['current_index'] += 1
    
    # Check if game over
    is_finished = session['current_index'] >= session['total']
    
    response_data = {
        'feedback': 'Correct!' if is_correct else 'Incorrect',
        'correct_answer': correct_option,
        'explanation': q['explanation'],
        'is_finished': is_finished
    }
    
    if not is_finished:
        # Provide next question
        next_q = questions[session['current_index']]
        response_data['next_question'] = {
            'question': next_q['question'],
            'options': {
                'A': next_q['option_a'],
                'B': next_q['option_b'],
                'C': next_q['option_c'],
                'D': next_q['option_d']
            },
            'progress': f"Question {session['current_index'] + 1} of {session['total']}"
        }
    
    return jsonify(response_data)

@app.route('/game/results', methods=['GET'])
def results():
    if 'questions' not in session:
        return jsonify({'error': 'No active game'}), 400
    
    score = session['score']
    total = session['total']
    percentage = round((score / total) * 100) if total > 0 else 0
    elapsed = round(time.time() - session['start_time'], 1)
    max_streak = session['max_consecutive_correct']
    
    achievements = []
    if total == 10 and score == 10:
        achievements.append('Perfect Round')
    if max_streak >= 5:
        achievements.append('Hot Streak')
    if max_streak >= 3:
        achievements.append('Triple Win')
    
    if not achievements:
        achievements_msg = 'No achievements this round'
    else:
        achievements_msg = achievements
    
    return jsonify({
        'score': f"{score}/{total} Correct ({percentage}%)",
        'elapsed_time_seconds': elapsed,
        'achievements': achievements_msg,
        'category': session['category']
    })

@app.route('/game/play-again', methods=['POST'])
def play_again():
    if 'questions' not in session:
        return jsonify({'error': 'No previous game'}), 400
    
    category = session['category']
    # Reset and start new game
    session.clear()
    # Re-start with same category
    return jsonify({
        'message': 'Starting new game',
        'category': category,
        'action': 'start_new'
    })

@app.route('/game/new-category', methods=['POST'])
def new_category():
    session.clear()
    return jsonify({
        'message': 'Session cleared',
        'action': 'select_category'
    })

if __name__ == '__main__':
    app.run(debug=True, port=5001)
