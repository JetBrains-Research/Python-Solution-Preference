from flask import Blueprint, request, jsonify, current_app
from app.models import db, Product, ProductStatus, generate_token, VALID_CATEGORIES, VALID_CONDITIONS
from app.utils.file_utils import save_image_file
import re
from datetime import datetime

product_bp = Blueprint('product', __name__)

def validate_email(email):
    """Basic email validation"""
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None

def validate_price(price_str):
    """Validate that price is at least 0.01"""
    try:
        price = float(price_str)
        return price >= 0.01
    except (ValueError, TypeError):
        return False

@product_bp.route('/api/products/create', methods=['POST'])
def create_product():
    """Create a new product listing"""
    # Check if all required fields are present
    required_fields = [
        'title', 'description', 'price', 'category', 'condition',
        'location', 'seller_name', 'seller_email'
    ]

    for field in required_fields:
        if field not in request.form:
            return jsonify({'error': f'Missing required field: {field}'}), 400

    # Validate image file
    if 'image' not in request.files:
        return jsonify({'error': 'No image file provided'}), 400

    image_file = request.files['image']
    if image_file.filename == '':
        return jsonify({'error': 'No image file selected'}), 400

    # Validate field values
    title = request.form.get('title', '').strip()
    description = request.form.get('description', '').strip()
    price_str = request.form.get('price', '')
    category = request.form.get('category', '')
    condition = request.form.get('condition', '')
    location = request.form.get('location', '').strip()
    seller_name = request.form.get('seller_name', '').strip()
    seller_email = request.form.get('seller_email', '').strip()

    # Validate string fields
    if len(title) < 1 or len(title) > 100:
        return jsonify({'error': 'Title must be between 1-100 characters'}), 400

    if len(description) < 1:
        return jsonify({'error': 'Description cannot be empty'}), 400

    if not validate_price(price_str):
        return jsonify({'error': 'Price must be at least 0.01 USD'}), 400

    price = float(price_str)

    if category not in VALID_CATEGORIES:
        return jsonify({'error': f'Invalid category. Must be one of: {", ".join(VALID_CATEGORIES)}'}), 400

    if condition not in VALID_CONDITIONS:
        return jsonify({'error': f'Invalid condition. Must be one of: {", ".join(VALID_CONDITIONS)}'}), 400

    if len(location) < 1 or len(location) > 100:
        return jsonify({'error': 'Location must be between 1-100 characters'}), 400

    if len(seller_name) < 2:
        return jsonify({'error': 'Seller name must be at least 2 characters'}), 400

    if not validate_email(seller_email):
        return jsonify({'error': 'Invalid seller email format'}), 400

    # Save image file
    try:
        image_path = save_image_file(image_file)
    except Exception as e:
        return jsonify({'error': f'Failed to save image: {str(e)}'}), 400

    # Create product
    seller_token = generate_token()

    product = Product(
        title=title,
        description=description,
        price=price,
        category=category,
        condition=condition,
        location=location,
        image_path=image_path,
        seller_name=seller_name,
        seller_email=seller_email,
        seller_token=seller_token,
        status=ProductStatus.AVAILABLE
    )

    db.session.add(product)
    db.session.commit()

    return jsonify({
        'message': 'Product created successfully',
        'product_id': product.id,
        'seller_token': seller_token,
        'image_path': image_path
    }), 201

@product_bp.route('/api/products/<int:product_id>', methods=['GET'])
def get_product_detail(product_id):
    """Get detailed information about a product"""
    product = Product.query.get(product_id)
    if not product:
        return jsonify({'error': 'Product not found'}), 404

    product_data = product.to_dict()

    # Add order status info
    if product.order:
        product_data['order_status'] = product.order.status

    return jsonify(product_data), 200
