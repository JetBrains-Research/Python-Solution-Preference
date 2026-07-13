from flask import Blueprint, request, jsonify
from app.models import db, Product, Order, ProductStatus, OrderStatus, generate_token
import re

checkout_bp = Blueprint('checkout', __name__)

def validate_email(email):
    """Basic email validation"""
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None

def validate_phone(phone):
    """Basic phone validation - at least 7 digits"""
    digits = re.sub(r'[^\d]', '', phone)
    return len(digits) >= 7

@checkout_bp.route('/api/products/<int:product_id>/checkout', methods=['POST'])
def checkout_product(product_id):
    """Handle product checkout"""
    # Get product with lock to prevent concurrent checkout
    product = Product.query.with_for_update().get(product_id)
    if not product:
        return jsonify({'error': 'Product not found'}), 404

    # Check if product is available
    if product.status != ProductStatus.AVAILABLE:
        return jsonify({'error': f'Product is not available. Current status: {product.status}'}), 400

    # Validate buyer information
    if not request.is_json:
        return jsonify({'error': 'Request must be JSON'}), 400

    required_fields = ['buyer_name', 'buyer_email', 'buyer_phone']

    for field in required_fields:
        if field not in request.json:
            return jsonify({'error': f'Missing required field: {field}'}), 400

    buyer_name = request.json.get('buyer_name', '').strip()
    buyer_email = request.json.get('buyer_email', '').strip()
    buyer_phone = request.json.get('buyer_phone', '').strip()

    # Validate buyer fields
    if len(buyer_name) < 2:
        return jsonify({'error': 'Buyer name must be at least 2 characters'}), 400

    if not validate_email(buyer_email):
        return jsonify({'error': 'Invalid buyer email format'}), 400

    if not validate_phone(buyer_phone):
        return jsonify({'error': 'Invalid phone number. Must have at least 7 digits.'}), 400

    # Create order
    buyer_token = generate_token()

    order = Order(
        product_id=product_id,
        buyer_name=buyer_name,
        buyer_email=buyer_email,
        buyer_phone=buyer_phone,
        buyer_token=buyer_token,
        status=OrderStatus.PENDING
    )

    # Update product status
    product.status = ProductStatus.PENDING

    db.session.add(order)
    db.session.commit()

    return jsonify({
        'message': 'Order created successfully',
        'order_id': order.id,
        'buyer_token': buyer_token,
        'product_status': product.status
    }), 201
