from flask import Blueprint, request, jsonify
from app.models import db, Product, Order, ProductStatus, OrderStatus
from flask_sqlalchemy import SQLAlchemy

status_bp = Blueprint('status', __name__)

@status_bp.route('/api/seller/status/<token>', methods=['GET'])
def seller_status(token):
    """Get seller status for a product"""
    product = Product.query.filter_by(seller_token=token).first()
    if not product:
        return jsonify({'error': 'Invalid seller token'}), 404

    product_data = product.to_dict()
    product_data['token'] = token

    # Add order information if exists
    if product.order:
        product_data['buyer_name'] = product.order.buyer_name
        product_data['buyer_email'] = product.order.buyer_email
        product_data['buyer_phone'] = product.order.buyer_phone
        product_data['order_status'] = product.order.status
        product_data['order_id'] = product.order.id
    else:
        product_data['buyer_name'] = None
        product_data['buyer_email'] = None
        product_data['buyer_phone'] = None
        product_data['order_status'] = None

    return jsonify(product_data), 200

@status_bp.route('/api/seller/status/<token>/confirm_payment', methods=['POST'])
def confirm_payment(token):
    """Confirm payment received and mark product as sold"""
    product = Product.query.filter_by(seller_token=token).first()
    if not product:
        return jsonify({'error': 'Invalid seller token'}), 404

    if not product.order or product.order.status != OrderStatus.PENDING:
        return jsonify({'error': 'No pending order to confirm'}), 400

    # Update order and product status
    product.order.status = OrderStatus.CONFIRMED
    product.status = ProductStatus.SOLD

    db.session.commit()

    return jsonify({
        'message': 'Payment confirmed, product sold',
        'product_status': product.status,
        'order_status': product.order.status
    }), 200

@status_bp.route('/api/seller/status/<token>/cancel', methods=['POST'])
def cancel_order(token):
    """Cancel pending order and make product available again"""
    product = Product.query.filter_by(seller_token=token).first()
    if not product:
        return jsonify({'error': 'Invalid seller token'}), 404

    if not product.order or product.order.status != OrderStatus.PENDING:
        return jsonify({'error': 'No pending order to cancel'}), 400

    # Delete the order and make product available
    db.session.delete(product.order)
    product.status = ProductStatus.AVAILABLE

    db.session.commit()

    return jsonify({
        'message': 'Order cancelled, product available again',
        'product_status': product.status
    }), 200

@status_bp.route('/api/buyer/order/<token>', methods=['GET'])
def buyer_order(token):
    """Get buyer order status"""
    order = Order.query.filter_by(buyer_token=token).first()
    if not order:
        return jsonify({'error': 'Invalid buyer token'}), 404

    product = order.product
    if not product:
        return jsonify({'error': 'Order product not found'}), 404

    order_data = {
        'order_id': order.id,
        'token': token,
        'product': product.to_dict(),
        'seller_name': product.seller_name,
        'seller_email': product.seller_email,
        'seller_location': product.location,
        'order_status': order.status,
        'created_at': order.created_at.isoformat() if order.created_at else None
    }

    return jsonify(order_data), 200
