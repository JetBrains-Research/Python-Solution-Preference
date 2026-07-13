from flask import Blueprint, request, jsonify
from app.models import Product, ProductStatus, VALID_CATEGORIES
from sqlalchemy import desc

browse_bp = Blueprint('browse', __name__)

@browse_bp.route('/api/products/featured', methods=['GET'])
def get_featured_products():
    """Get up to 8 most recent available products"""
    products = Product.query.filter_by(status=ProductStatus.AVAILABLE)\
        .order_by(desc(Product.created_at))\
        .limit(8)\
        .all()

    products_data = [product.to_browse_dict() for product in products]

    return jsonify(products_data), 200

@browse_bp.route('/api/products/browse', methods=['GET'])
def browse_products():
    """Browse available products with optional category filter"""
    category = request.args.get('category', None)

    query = Product.query.filter_by(status=ProductStatus.AVAILABLE)\
        .order_by(desc(Product.created_at))

    if category and category != 'all':
        if category not in VALID_CATEGORIES:
            return jsonify({'error': f'Invalid category. Must be one of: {", ".join(VALID_CATEGORIES)}'}), 400
        query = query.filter_by(category=category)

    products = query.all()
    products_data = [product.to_browse_dict() for product in products]

    return jsonify(products_data), 200
