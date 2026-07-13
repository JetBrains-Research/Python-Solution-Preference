import os
import uuid
import secrets
import re
import sqlite3
from datetime import datetime
from flask import Flask, request, jsonify, send_from_directory, g
from werkzeug.utils import secure_filename
from PIL import Image

app = Flask(__name__)
UPLOAD_FOLDER = 'uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 10 * 1024 * 1024  # 10 MB
DATABASE = 'marketplace.db'

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
CATEGORIES = ['Electronics', 'Fashion', 'Home & Garden', 'Vehicles', 'Collectibles', 'Sports', 'Books', 'Other']
CONDITIONS = ['new', 'like-new', 'good', 'fair']

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def get_db():
    if 'db' not in g:
        g.db = sqlite3.connect(DATABASE)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA journal_mode=WAL")
        g.db.execute("PRAGMA foreign_keys=ON")
    return g.db

@app.teardown_appcontext
def close_db(exception):
    db = g.pop('db', None)
    if db is not None:
        db.close()

def init_db():
    db = sqlite3.connect(DATABASE)
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA foreign_keys=ON")
    db.executescript('''
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            description TEXT NOT NULL,
            price REAL NOT NULL CHECK(price >= 0.01),
            category TEXT NOT NULL CHECK(category IN ('Electronics','Fashion','Home & Garden','Vehicles','Collectibles','Sports','Books','Other')),
            condition TEXT NOT NULL CHECK(condition IN ('new','like-new','good','fair')),
            location TEXT NOT NULL,
            image_filename TEXT NOT NULL,
            seller_name TEXT NOT NULL,
            seller_email TEXT NOT NULL,
            seller_token TEXT NOT NULL UNIQUE,
            status TEXT NOT NULL DEFAULT 'available' CHECK(status IN ('available','pending','sold')),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id INTEGER NOT NULL UNIQUE,
            buyer_name TEXT NOT NULL,
            buyer_email TEXT NOT NULL,
            buyer_phone TEXT NOT NULL,
            buyer_token TEXT NOT NULL UNIQUE,
            order_status TEXT NOT NULL DEFAULT 'pending' CHECK(order_status IN ('pending','confirmed','cancelled')),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE CASCADE
        );
    ''')
    db.commit()
    db.close()

def generate_token():
    return secrets.token_urlsafe(32)

def is_valid_email(email):
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None

# Initialize DB on startup
init_db()

# Routes
@app.route('/api/listings', methods=['POST'])
def create_listing():
    # Validate required fields
    if 'image' not in request.files:
        return jsonify({'error': 'Product image is required'}), 400
    file = request.files['image']
    if file.filename == '':
        return jsonify({'error': 'Product image is required'}), 400
    if not allowed_file(file.filename):
        return jsonify({'error': 'Invalid image format. Allowed: png, jpg, jpeg, gif, webp'}), 400

    # Get form fields
    title = request.form.get('title', '').strip()
    description = request.form.get('description', '').strip()
    price_str = request.form.get('price', '').strip()
    category = request.form.get('category', '').strip()
    condition = request.form.get('condition', '').strip()
    location = request.form.get('location', '').strip()
    seller_name = request.form.get('seller_name', '').strip()
    seller_email = request.form.get('seller_email', '').strip()

    errors = []
    if not title:
        errors.append('Title is required')
    if not description:
        errors.append('Description is required')
    try:
        price = float(price_str)
        if price < 0.01:
            raise ValueError
    except (ValueError, TypeError):
        errors.append('Price must be a number >= 0.01')
    else:
        price = round(price, 2)
    if category not in CATEGORIES:
        errors.append(f'Category must be one of: {", ".join(CATEGORIES)}')
    if condition not in CONDITIONS:
        errors.append(f'Condition must be one of: {", ".join(CONDITIONS)}')
    if not location:
        errors.append('Location is required')
    if not seller_name:
        errors.append('Seller name is required')
    if not seller_email or not is_valid_email(seller_email):
        errors.append('Valid seller email is required')

    if errors:
        return jsonify({'error': 'Validation failed', 'details': errors}), 400

    # Save image
    ext = file.filename.rsplit('.', 1)[1].lower()
    unique_filename = f"{uuid.uuid4().hex}.{ext}"
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
    file.save(filepath)

    # Verify it's a valid image
    try:
        with Image.open(filepath) as img:
            img.verify()
    except Exception:
        os.remove(filepath)
        return jsonify({'error': 'Uploaded file is not a valid image'}), 400

    # Save re-opened for proper format
    try:
        img = Image.open(filepath)
        img.load()
    except Exception:
        os.remove(filepath)
        return jsonify({'error': 'Uploaded file is not a valid image'}), 400

    seller_token = generate_token()

    db = get_db()
    try:
        db.execute(
            "INSERT INTO products (title, description, price, category, condition, location, image_filename, seller_name, seller_email, seller_token, status) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'available')",
            (title, description, price, category, condition, location, unique_filename, seller_name, seller_email, seller_token)
        )
        db.commit()
    except Exception as e:
        os.remove(filepath)
        return jsonify({'error': 'Database error', 'details': str(e)}), 500

    return jsonify({
        'message': 'Listing created successfully',
        'seller_token': seller_token,
        'status': 'available'
    }), 201

@app.route('/api/listings', methods=['GET'])
def browse_listings():
    category = request.args.get('category', '').strip()
    limit = request.args.get('limit', default=8, type=int)
    if limit < 1 or limit > 50:
        limit = 8

    db = get_db()
    if category and category in CATEGORIES:
        query = "SELECT id, title, price, condition, location, image_filename, seller_name, category, created_at FROM products WHERE status='available' AND category=? ORDER BY created_at DESC LIMIT ?"
        rows = db.execute(query, (category, limit)).fetchall()
    else:
        query = "SELECT id, title, price, condition, location, image_filename, seller_name, category, created_at FROM products WHERE status='available' ORDER BY created_at DESC LIMIT ?"
        rows = db.execute(query, (limit,)).fetchall()

    products = []
    for row in rows:
        products.append({
            'id': row['id'],
            'title': row['title'],
            'price': row['price'],
            'condition': row['condition'],
            'location': row['location'],
            'image_url': f"/uploads/{row['image_filename']}",
            'seller_name': row['seller_name'],
            'category': row['category'],
            'created_at': row['created_at']
        })
    return jsonify({'products': products})

@app.route('/api/featured', methods=['GET'])
def featured():
    db = get_db()
    rows = db.execute(
        "SELECT id, title, price, condition, location, image_filename, seller_name, category, created_at FROM products WHERE status='available' ORDER BY created_at DESC LIMIT 8"
    ).fetchall()
    products = [{
        'id': row['id'],
        'title': row['title'],
        'price': row['price'],
        'condition': row['condition'],
        'location': row['location'],
        'image_url': f"/uploads/{row['image_filename']}",
        'seller_name': row['seller_name'],
        'category': row['category'],
        'created_at': row['created_at']
    } for row in rows]
    return jsonify({'featured': products})

@app.route('/api/listings/<int:product_id>', methods=['GET'])
def product_detail(product_id):
    db = get_db()
    product = db.execute(
        "SELECT * FROM products WHERE id=?", (product_id,)
    ).fetchone()
    if not product:
        return jsonify({'error': 'Product not found'}), 404

    data = {
        'id': product['id'],
        'title': product['title'],
        'description': product['description'],
        'price': product['price'],
        'category': product['category'],
        'condition': product['condition'],
        'location': product['location'],
        'image_url': f"/uploads/{product['image_filename']}",
        'seller_name': product['seller_name'],
        'status': product['status'],
        'created_at': product['created_at']
    }
    # Purchase availability
    if product['status'] == 'available':
        data['can_purchase'] = True
        data['message'] = 'Available for purchase'
    elif product['status'] == 'pending':
        data['can_purchase'] = False
        data['message'] = 'This product has a pending offer; purchase not allowed'
    elif product['status'] == 'sold':
        data['can_purchase'] = False
        data['message'] = 'This product has been sold'
    return jsonify(data)

@app.route('/api/checkout/<int:product_id>', methods=['POST'])
def checkout(product_id):
    data = request.get_json(silent=True)
    if not data:
        return jsonify({'error': 'Request body must be JSON'}), 400
    buyer_name = data.get('buyer_name', '').strip()
    buyer_email = data.get('buyer_email', '').strip()
    buyer_phone = data.get('phone', '').strip()

    errors = []
    if not buyer_name or len(buyer_name) < 2:
        errors.append('Buyer name must be at least 2 characters')
    if not buyer_email or not is_valid_email(buyer_email):
        errors.append('Valid email is required')
    if not buyer_phone:
        errors.append('Phone number is required')
    if errors:
        return jsonify({'error': 'Validation failed', 'details': errors}), 400

    db = get_db()
    try:
        # Atomicity: use BEGIN IMMEDIATE to prevent concurrent writes
        db.execute("BEGIN IMMEDIATE")
        # Lock the row and check availability
        product = db.execute(
            "SELECT id, status, title, description, price, category, condition, location, image_filename, seller_name, seller_email FROM products WHERE id=?",
            (product_id,)
        ).fetchone()
        if not product:
            db.rollback()
            return jsonify({'error': 'Product not found'}), 404
        if product['status'] != 'available':
            db.rollback()
            return jsonify({'error': 'Product is no longer available', 'status': product['status']}), 409

        # Update product status to pending
        db.execute("UPDATE products SET status='pending' WHERE id=?", (product_id,))
        buyer_token = generate_token()
        db.execute(
            "INSERT INTO orders (product_id, buyer_name, buyer_email, buyer_phone, buyer_token, order_status) VALUES (?, ?, ?, ?, ?, 'pending')",
            (product_id, buyer_name, buyer_email, buyer_phone, buyer_token)
        )
        db.commit()
    except Exception as e:
        db.rollback()
        return jsonify({'error': 'Transaction failed', 'details': str(e)}), 500

    return jsonify({
        'message': 'Order created successfully',
        'buyer_token': buyer_token,
        'order_status': 'pending'
    }), 201

@app.route('/api/seller/status', methods=['GET'])
def seller_status():
    token = request.headers.get('Authorization', '').strip()
    if not token.startswith('Bearer '):
        return jsonify({'error': 'Authorization header must be Bearer token'}), 401
    token = token[7:]

    db = get_db()
    product = db.execute("SELECT * FROM products WHERE seller_token=?", (token,)).fetchone()
    if not product:
        return jsonify({'error': 'Invalid seller token'}), 404

    order = db.execute("SELECT * FROM orders WHERE product_id=?", (product['id'],)).fetchone()
    response = {
        'product_id': product['id'],
        'title': product['title'],
        'description': product['description'],
        'price': product['price'],
        'category': product['category'],
        'condition': product['condition'],
        'location': product['location'],
        'image_url': f"/uploads/{product['image_filename']}",
        'seller_name': product['seller_name'],
        'seller_email': product['seller_email'],
        'status': product['status'],
        'seller_token': product['seller_token'],
        'created_at': product['created_at']
    }

    if product['status'] == 'available':
        response['message'] = 'Waiting for buyer'
    elif product['status'] == 'pending':
        if order:
            response['buyer_info'] = {
                'name': order['buyer_name'],
                'email': order['buyer_email'],
                'phone': order['buyer_phone']
            }
        response['message'] = 'Order pending. You can confirm payment or cancel.'
        response['actions'] = ['confirm_payment', 'cancel']
    elif product['status'] == 'sold':
        if order:
            response['buyer_info'] = {
                'name': order['buyer_name'],
                'email': order['buyer_email'],
                'phone': order['buyer_phone']
            }
        response['message'] = 'Transaction complete'
    return jsonify(response)

@app.route('/api/seller/confirm', methods=['POST'])
def seller_confirm():
    token = request.headers.get('Authorization', '').strip()
    if not token.startswith('Bearer '):
        return jsonify({'error': 'Authorization header must be Bearer token'}), 401
    token = token[7:]

    db = get_db()
    product = db.execute("SELECT * FROM products WHERE seller_token=?", (token,)).fetchone()
    if not product:
        return jsonify({'error': 'Invalid seller token'}), 404
    if product['status'] != 'pending':
        return jsonify({'error': 'Product is not in pending state'}), 400

    try:
        db.execute("UPDATE products SET status='sold' WHERE id=? AND status='pending'", (product['id'],))
        db.execute("UPDATE orders SET order_status='confirmed' WHERE product_id=? AND order_status='pending'", (product['id'],))
        db.commit()
    except Exception as e:
        db.rollback()
        return jsonify({'error': str(e)}), 500

    return jsonify({'message': 'Payment confirmed, product sold', 'status': 'sold'})

@app.route('/api/seller/cancel', methods=['POST'])
def seller_cancel():
    token = request.headers.get('Authorization', '').strip()
    if not token.startswith('Bearer '):
        return jsonify({'error': 'Authorization header must be Bearer token'}), 401
    token = token[7:]

    db = get_db()
    product = db.execute("SELECT * FROM products WHERE seller_token=?", (token,)).fetchone()
    if not product:
        return jsonify({'error': 'Invalid seller token'}), 404
    if product['status'] != 'pending':
        return jsonify({'error': 'Product is not in pending state'}), 400

    try:
        db.execute("UPDATE products SET status='available' WHERE id=? AND status='pending'", (product['id'],))
        db.execute("UPDATE orders SET order_status='cancelled' WHERE product_id=? AND order_status='pending'", (product['id'],))
        db.commit()
    except Exception as e:
        db.rollback()
        return jsonify({'error': str(e)}), 500

    return jsonify({'message': 'Order cancelled, product is available again', 'status': 'available'})

@app.route('/api/buyer/order', methods=['GET'])
def buyer_order():
    token = request.headers.get('Authorization', '').strip()
    if not token.startswith('Bearer '):
        return jsonify({'error': 'Authorization header must be Bearer token'}), 401
    token = token[7:]

    db = get_db()
    order = db.execute("SELECT * FROM orders WHERE buyer_token=?", (token,)).fetchone()
    if not order:
        return jsonify({'error': 'Invalid buyer token'}), 404

    product = db.execute("SELECT * FROM products WHERE id=?", (order['product_id'],)).fetchone()
    if not product:
        return jsonify({'error': 'Product not found'}), 404

    response = {
        'order_id': order['id'],
        'product': {
            'id': product['id'],
            'title': product['title'],
            'description': product['description'],
            'price': product['price'],
            'category': product['category'],
            'condition': product['condition'],
            'location': product['location'],
            'image_url': f"/uploads/{product['image_filename']}",
        },
        'seller_info': {
            'name': product['seller_name'],
            'email': product['seller_email'],
            'location': product['location']
        },
        'order_status': order['order_status'],
        'buyer_token': order['buyer_token'],
        'buyer_info': {
            'name': order['buyer_name'],
            'email': order['buyer_email'],
            'phone': order['buyer_phone']
        }
    }

    if order['order_status'] == 'pending':
        response['message'] = 'Awaiting payment confirmation'
    elif order['order_status'] == 'confirmed':
        response['message'] = 'Transaction complete'
    elif order['order_status'] == 'cancelled':
        response['message'] = 'Order cancelled. You can check if the product is available again.'
        # Optionally include product status
        response['product_status'] = product['status']

    return jsonify(response)

@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

if __name__ == '__main__':
    app.run(debug=True, port=5000)
