import csv
import random
import time
from datetime import datetime
from flask import Flask, jsonify, request, session
import os

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'quiz_app_secret_key')

# Load questions from CSV
def load_questions():
    questions = []
    with open('assets/questions.csv') as f:
        reader = csv.DictReader(f)
        for row in reader:
            questions.append({
                'id': row['id'],
                'question': row['question'],
                'option_a': row['option_a'],
                'option_b': row['option_b'],
                'option_c': row['option_c'],
                'option_d': row['option_d'],
                'correct_option': row['correct_option'],
                'explanation': row['explanation'],
                'category': row['category']
            })
    return questions

# Global questions list
QUESTIONS = load_questions()

# Get all unique categories
def get_categories():
    categories = set(q['category'] for q in QUESTIONS)
    return sorted(categories)

@app.route('/categories', methods=['GET'])
def get_all_categories():
    categories = get_categories()
    categories.append('Surprise Me!')
    return jsonify({'categories': categories})

@app.route('/start-game', methods=['POST'])
def start_game():
    data = request.get_json()
    category = data.get('category')

    if not category:
        return jsonify({'error': 'Category is required'}), 400

    # Handle Surprise Me!
    selected_category = category
    if category == 'Surprise Me!':
        possible_categories = get_categories()
        selected_category = random.choice(possible_categories)

    # Get questions for category
    category_questions = [q for q in QUESTIONS if q['category'] == selected_category]
    question_count = len(category_questions)

    warning = None
    if question_count < 10:
        warning = 'Not enough questions in this category for all accomplishments'

    # Sample up to 10 questions
    sampled_questions = random.sample(category_questions, min(10, question_count))

    # Start the game session
    session['category'] = selected_category
    session['original_category'] = category  # Keep track if it was Surprise Me!
    session['questions'] = sampled_questions
    session['current_question_index'] = 0
    session['score'] = 0
    session['consecutive_correct'] = 0
    session['max_consecutive'] = 0
    session['start_time'] = datetime.now().isoformat()
    session['total_questions'] = len(sampled_questions)

    response = {
        'message': 'Game started',
        'category': selected_category,
        'total_questions': len(sampled_questions),
        'current_question_index': 1
    }

    if category == 'Surprise Me!':
        response['selected_category'] = selected_category
    if warning:
        response['warning'] = warning

    return jsonify(response)

@app.route('/question', methods=['GET'])
def get_question():
    if 'questions' not in session or session['current_question_index'] >= session['total_questions']:
        return jsonify({'error': 'No questions available or game completed'}), 400

    current_index = session['current_question_index']
    question = session['questions'][current_index]

    return jsonify({
        'question': question['question'],
        'options': {
            'A': question['option_a'],
            'B': question['option_b'],
            'C': question['option_c'],
            'D': question['option_d']
        },
        'progress': f"Question {current_index + 1} of {len(session['questions'])}"
    })

@app.route('/answer', methods=['POST'])
def submit_answer():
    if 'questions' not in session or session['current_question_index'] >= session['total_questions']:
        return jsonify({'error': 'No game in progress or game completed'}), 400

    data = request.get_json()
    user_answer = data.get('answer', '').upper()

    current_index = session['current_question_index']
    question = session['questions'][current_index]

    is_correct = user_answer == question['correct_option']

    if is_correct:
        session['score'] += 1
        session['consecutive_correct'] += 1
        if session['consecutive_correct'] > session['max_consecutive']:
            session['max_consecutive'] = session['consecutive_correct']
    else:
        session['consecutive_correct'] = 0

    # Prepare response
    response = {
        'correct': is_correct,
        'feedback': 'Correct!' if is_correct else 'Incorrect',
        'correct_answer': question['correct_option'],
        'correct_answer_text': question[f'option_{question["correct_option"].lower()}'],
        'explanation': question['explanation']
    }

    # Move to next question
    session['current_question_index'] += 1

    return jsonify(response)

@app.route('/results', methods=['GET'])
def get_results():
    if 'questions' not in session or 'score' not in session:
        return jsonify({'error': 'No game in progress'}), 400

    total_questions = len(session['questions'])
    score = session['score']
    start_time_str = session['start_time']
    start_time = datetime.fromisoformat(start_time_str)
    elapsed_time = (datetime.now() - start_time).total_seconds()

    percentage = (score / total_questions) * 100

    # Determine achievements
    achievements = []
    if total_questions == 10 and score == 10:
        achievements.append('Perfect Round')
    if session['max_consecutive'] >= 5:
        achievements.append('Hot Streak')
    if session['max_consecutive'] >= 3:
        achievements.append('Triple Win')

    return jsonify({
        'score': f"{score}/{total_questions} Correct ({percentage:.0f}%)",
        'elapsed_time_seconds': round(elapsed_time, 2),
        'achievements': achievements if achievements else ['No achievements this round'],
        'max_consecutive': session['max_consecutive'],
        'consecutive_correct': session['consecutive_correct']
    })

@app.route('/play-again', methods=['POST'])
def play_again():
    if 'original_category' not in session:
        return jsonify({'error': 'No game in progress'}), 400

    category = session['original_category']

    if category == 'Surprise Me!':
        # For Surprise Me!, pick a new random category
        possible_categories = get_categories()
        selected_category = random.choice(possible_categories)
        message = 'New game started with new random category'
    else:
        selected_category = category
        message = 'New game started with same category'

    category_questions = [q for q in QUESTIONS if q['category'] == selected_category]
    sampled_questions = random.sample(category_questions, min(10, len(category_questions)))

    session['category'] = selected_category
    session['questions'] = sampled_questions
    session['current_question_index'] = 0
    session['score'] = 0
    session['consecutive_correct'] = 0
    session['max_consecutive'] = 0
    session['start_time'] = datetime.now().isoformat()
    session['total_questions'] = len(sampled_questions)

    response = {
        'message': message,
        'category': selected_category,
        'total_questions': len(sampled_questions)
    }

    # Add warning for small categories
    if len(category_questions) < 10:
        response['warning'] = 'Not enough questions in this category for all accomplishments'

    return jsonify(response)

@app.route('/new-category', methods=['POST'])
def new_category():
    # Clear current game
    session.clear()
    return jsonify({'message': 'Ready for new category selection'})

if __name__ == '__main__':
    app.run(debug=True)
