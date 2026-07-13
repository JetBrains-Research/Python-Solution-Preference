import os
import secrets
from flask import Flask, request, jsonify, abort
from flask_sqlalchemy import SQLAlchemy
from email_validator import validate_email, EmailNotValidError
from models import db, Product, Order, CategoryEnum, ConditionEnum, ProductStatus, OrderStatus
from sqlalchemy.exc import IntegrityError
from sqlalchemy import and_

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///marketplace.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db.init_app(app)

# Helper
def generate_token():
    return secrets.token_urlsafe(32)

def validate_product_payload(data):
    required = ['title','description','price','category','condition','location','image_url','seller_name','seller_email']
    for f in required:
        if f not in data:
            abort(400, f\"Missing field {f}\")
    if not isinstance(data['price'], (int,float)) or data['price'] < 0.01:
        abort(400, 'Price must be at least $0.01')
    if data['category'] not in CategoryEnum.__members__:
        abort(400, 'Invalid category')
    if data['condition'] not in ConditionEnum.__members__:
        abort(400, 'Invalid condition')
    try:
        validate_email(data['seller_email'])
    except EmailNotValidError as e:
        abort(400, str(e))

def validate_buyer_payload(data):
    if 'buyer_name' not in data or len(data['buyer_name'].strip()) < 2:
        abort(400, 'Buyer name must be at least 2 characters')
    if 'buyer_email' not in data:
        abort(400, 'Buyer email required')
    try:
        validate_email(data['buyer_email'])
    except EmailNotValidError as e:
        abort(400, str(e))
    if 'buyer_phone' not in data or not data['buyer_phone'].strip():
        abort(400, 'Buyer phone required')

@app.before_first_request
def create_tables():
    db.create_all()

# Product creation
@app.route('/products', methods=['POST'])
def create_product():
    data = request.json
    validate_product_payload(data)
    product = Product(
        title=data['title'],
        description=data['description'],
        price=float(data['price']),
        category=CategoryEnum[data['category']],
        condition=ConditionEnum[data['condition']],
        location=data['location'],
        image_url=data['image_url'],
        seller_name=data['seller_name'],
        seller_email=data['seller_email']
    )
    db.session.add(product)
    db.session.commit()
    return jsonify({
        'product_id': product.id,
        'seller_token': product.seller_token
    }), 201

# Browse
@app.route('/products', methods=['GET'])
def browse_products():
    category = request.args.get('category')
    query = Product.query.filter_by(status=ProductStatus.available)
    if category:
        if category not in CategoryEnum.__members__:
            abort(400, 'Invalid category filter')
        query = query.filter_by(category=CategoryEnum[category])
    products = query.order_by(Product.created_at.desc()).limit(8).all()
    result = []
    for p in products:
        result.append({
            'id': p.id,
            'image_url': p.image_url,
            'condition': p.condition.value,
            'title': p.title,
            'price': p.price,
            'location': p.location,
            'seller_name': p.seller_name
        })
    return jsonify(result), 200

# Product detail
@app.route('/products/<int:pid>', methods=['GET'])
def product_detail(pid):
    product = Product.query.get_or_404(pid)
    return jsonify({
        'id': product.id,
        'title': product.title,
        'description': product.description,
        'price': product.price,
        'category': product.category.value,
        'condition': product.condition.value,
        'location': product.location,
        'image_url': product.image_url,
        'seller_name': product.seller_name,
        'seller_email': product.seller_email,
        'status': product.status.value
    }), 200

# Checkout
@app.route('/products/<int:pid>/checkout', methods=['POST'])
def checkout(pid):
    product = Product.query.get_or_404(pid)
    if product.status != ProductStatus.available:
        abort(400, 'Product not available for purchase')
    data = request.json
    validate_buyer_payload(data)

    # Atomic transaction
    try:
        with db.session.begin_nested():
            # Re-fetch with lock intention
            prod = Product.query.filter_by(id=pid).with_for_update().first()
            if not prod or prod.status != ProductStatus.available:
                abort(400, 'Product became unavailable')
            order = Order(
                product_id=pid,
                buyer_name=data['buyer_name'],
                buyer_email=data['buyer_email'],
                buyer_phone=data['buyer_phone']
            )
            prod.status = ProductStatus.pending
            db.session.add(order)
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        abort(400, 'Could not complete order')
    return jsonify({
        'order_id': order.id,
        'buyer_token': order.buyer_token
    }), 201

# Seller status
@app.route('/seller/<string:token>', methods=['GET'])
def seller_status(token):
    product = Product.query.filter_by(seller_token=token).first_or_404()
    response = {
        'product_id': product.id,
        'status': product.status.value,
        'seller_token': product.seller_token
    }
    if product.status != ProductStatus.available and product.order:
        response.update({
            'buyer_name': product.order.buyer_name,
            'buyer_email': product.order.buyer_email,
            'buyer_phone': product.order.buyer_phone,
            'order_status': product.order.status.value,
            'buyer_token': product.order.buyer_token
        })
    return jsonify(response), 200

@app.route('/seller/<string:token>/confirm', methods=['POST'])
def seller_confirm(token):
    product = Product.query.filter_by(seller_token=token).first_or_404()
    if product.status != ProductStatus.pending or not product.order:
        abort(400, 'No pending order to confirm')
    product.status = ProductStatus.sold
    product.order.status = OrderStatus.confirmed
    db.session.commit()
    return jsonify({'message': 'Payment confirmed, product sold'}), 200

@app.route('/seller/<string:token>/cancel', methods=['POST'])
def seller_cancel(token):
    product = Product.query.filter_by(seller_token=token).first_or_404()
    if product.status != ProductStatus.pending or not product.order:
        abort(400, 'No pending order to cancel')
    product.status = ProductStatus.available
    product.order.status = OrderStatus.cancelled
    db.session.commit()
    return jsonify({'message': 'Order cancelled, product available again'}), 200

# Buyer order view
@app.route('/buyer/<string:token>', methods=['GET'])
def buyer_view(token):
    order = Order.query.filter_by(buyer_token=token).first_or_404()
    product = order.product
    return jsonify({
        'order_id': order.id,
        'order_status': order.status.value,
        'buyer_token': order.buyer_token,
        'product': {
            'id': product.id,
            'title': product.title,
            'price': product.price,
            'seller_name': product.seller_name,
            'seller_email': product.seller_email,
            'seller_location': product.location
        }
    }), 200

if __name__ == '__main__':
    # Use 0.0.0.0 for container testing
    app.run(host='0.0.0.0', port=5000, debug=True)
