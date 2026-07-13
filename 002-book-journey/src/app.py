import json
import os
import re
from flask import Flask, request, jsonify

app = Flask(__name__)

# Load books from assets
BOOKS_FILE = os.path.join(os.path.dirname(__file__), '../assets/books.json')

def load_books():
    with open(BOOKS_FILE, 'r') as f:
        return json.load(f)

# In-memory data stores
books = load_books()
users = {}  # username -> user info
checkpoints = {}  # book_id -> list of checkpoints

# Valid moods
VALID_MOODS = {'Curious', 'Confused', 'Excited', 'Calm', 'Sad', 'Delighted'}

@app.route('/login', methods=['POST'])
def login():
    data = request.get_json()
    if not data or 'username' not in data:
        return jsonify({'error': 'Username is required'}), 400

    username = data['username']

    # Validate username
    if not re.match(r'^[a-zA-Z0-9_]{3,20}$', username):
        return jsonify({'error': 'Username must be 3-20 characters, letters, numbers, or underscores only'}), 400

    # Check if user exists, if not create
    if username not in users:
        users[username] = {'username': username}

    return jsonify({'username': username, 'message': 'Logged in successfully'}), 200

@app.route('/books', methods=['GET'])
def get_books():
    search = request.args.get('search', '').lower()

    filtered_books = []
    for book in books:
        if search:
            if (search in book['title'].lower() or
                search in book['author'].lower()):
                filtered_books.append(book)
        else:
            filtered_books.append(book)

    # Create synopsis preview (first 100 chars + ...)
    result = []
    for book in filtered_books:
        synopsis = book['synopsis']
        preview = synopsis[:100] + '...' if len(synopsis) > 100 else synopsis
        result.append({
            'id': book['id'],
            'title': book['title'],
            'author': book['author'],
            'year_published': book['year_published'],
            'genre': book['genre'],
            'synopsis_preview': preview
        })

    return jsonify(result), 200

@app.route('/my-journey', methods=['GET'])
def my_journey():
    username = request.args.get('username')
    if not username or username not in users:
        return jsonify({'error': 'User not logged in'}), 401

    user_books = set()

    # Find all books where this user has checkpoints
    for book_id, book_checkpoints in checkpoints.items():
        for cp in book_checkpoints:
            if cp['username'] == username:
                user_books.add(book_id)
                break

    result = []
    for book in books:
        if book['id'] in user_books:
            result.append({
                'id': book['id'],
                'title': book['title'],
                'author': book['author'],
                'year_published': book['year_published']
            })

    return jsonify(result), 200

@app.route('/books/<book_id>', methods=['GET'])
def get_book_details(book_id):
    username = request.args.get('username')
    if not username or username not in users:
        return jsonify({'error': 'User not logged in'}), 401

    # Find the book
    book = None
    for b in books:
        if b['id'] == book_id:
            book = b
            break

    if not book:
        return jsonify({'error': 'Book not found'}), 404

    # Count user's checkpoints for this book
    user_checkpoint_count = 0
    if book_id in checkpoints:
        for cp in checkpoints[book_id]:
            if cp['username'] == username:
                user_checkpoint_count += 1

    # Get all checkpoints for this book
    all_checkpoints = []
    if book_id in checkpoints:
        all_checkpoints = sorted(checkpoints[book_id], key=lambda x: x['chapter'])

    # Add is_own flag
    for cp in all_checkpoints:
        cp['is_own'] = (cp['username'] == username)

    response = {
        'id': book['id'],
        'title': book['title'],
        'author': book['author'],
        'year_published': book['year_published'],
        'genre': book['genre'],
        'synopsis': book['synopsis'],
        'total_chapters': book['total_chapters'],
        'your_journey': {
            'has_checkpoints': user_checkpoint_count > 0,
            'checkpoint_count': user_checkpoint_count
        },
        'reader_checkpoints': all_checkpoints
    }

    return jsonify(response), 200

@app.route('/books/<book_id>/checkpoints', methods=['POST'])
def add_checkpoint(book_id):
    username = request.args.get('username')
    if not username or username not in users:
        return jsonify({'error': 'User not logged in'}), 401

    data = request.get_json()
    if not data:
        return jsonify({'error': 'Request body is required'}), 400

    # Validate required fields
    if 'chapter' not in data:
        return jsonify({'error': 'Chapter is required'}), 400
    if 'note' not in data:
        return jsonify({'error': 'Note is required'}), 400

    # Validate chapter
    chapter = data['chapter']
    if not isinstance(chapter, int):
        return jsonify({'error': 'Chapter must be an integer'}), 400

    # Find book to get total_chapters
    book = None
    for b in books:
        if b['id'] == book_id:
            book = b
            break

    if not book:
        return jsonify({'error': 'Book not found'}), 404

    total_chapters = book['total_chapters']
    if chapter < 1 or chapter > total_chapters:
        return jsonify({'error': f'Chapter must be between 1 and {total_chapters}'}), 400

    # Validate note
    note = data['note'].strip()
    if len(note) < 1 or len(note) > 280:
        return jsonify({'error': 'Note must be 1-280 characters'}), 400

    # Validate mood
    mood = None
    if 'mood' in data and data['mood']:
        mood = data['mood']
        if mood not in VALID_MOODS:
            valid_moods_list = sorted(VALID_MOODS)
            return jsonify({'error': f'Mood must be one of: {valid_moods_list}'}), 400

    # Create checkpoint
    checkpoint = {
        'username': username,
        'chapter': chapter,
        'note': note,
        'mood': mood
    }

    # Add to checkpoints
    if book_id not in checkpoints:
        checkpoints[book_id] = []
    checkpoints[book_id].append(checkpoint)

    return jsonify({'message': 'Checkpoint added successfully', 'checkpoint': checkpoint}), 201

if __name__ == '__main__':
    app.run(debug=True)
