import os
from flask import Flask, request, jsonify, send_from_directory
from werkzeug.utils import secure_filename
from models import (
    create_product, get_featured_products, get_products, 
    get_product, create_order, get_seller_status, 
    update_product_status, get_buyer_order
)
from schemas import validate_product_data, validate_buyer_data
from utils import generate_token

app = Flask(__name__)
UPLOAD_FOLDER = 'uploads'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

@app.route('/products', methods=['POST'])
def list_product():
    # Handle multipart/form-data
    data = request.form.to_dict()
    file = request.files.get('image')
    
    if not file:
        return jsonify({'error': 'Product image is required'}), 400
    
    errors = validate_product_data(data)
    if errors:
        return jsonify({'errors': errors}), 400
    
    filename = secure_filename(file.filename)
    image_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    file.save(image_path)
    
    data['image_path'] = image_path
    token = generate_token()
    product_id = create_product(data, token)
    
    return jsonify({'seller_token': token, 'product_id': product_id}), 201

@app.route('/products', methods=['GET'])
def browse_products():
    category = request.args.get('category')
    if request.args.get('featured') == 'true':
        products = get_featured_products()
    else:
        products = get_products(category)
    
    result = []
    for p in products:
        result.append({
            'id': p['id'],
            'image': p['image_path'],
            'condition': p['condition'],
            'title': p['title'],
            'price': p['price'],
            'location': p['location'],
            'seller_name': p['seller_name']
        })
    return jsonify(result)

@app.route('/products/<int:product_id>', methods=['GET'])
def product_detail(product_id):
    p = get_product(product_id)
    if not p:
        return jsonify({'error': 'Product not found'}), 404
    
    return jsonify(dict(p))

@app.route('/products/<int:product_id>/checkout', methods=['POST'])
def checkout(product_id):
    data = request.json
    if not data:
        return jsonify({'error': 'Request body is required'}), 400
        
    errors = validate_buyer_data(data)
    if errors:
        return jsonify({'errors': errors}), 400
    
    buyer_token = generate_token()
    order_id = create_order(product_id, data, buyer_token)
    
    if not order_id:
        return jsonify({'error': 'Product is no longer available'}), 409
    
    return jsonify({'buyer_token': buyer_token, 'order_id': order_id}), 201

@app.route('/seller/status', methods=['GET'])
def seller_status():
    token = request.headers.get('Authorization')
    if not token:
        return jsonify({'error': 'Authorization token required'}), 401
    
    result = get_seller_status(token)
    if not result:
        return jsonify({'error': 'Invalid token'}), 403
    
    product, order = result
    response = {
        'product': dict(product),
        'status': product['status'],
        'seller_token': token
    }
    
    if product['status'] == 'Pending':
        response['buyer_info'] = {
            'name': order['buyer_name'],
            'email': order['buyer_email'],
            'phone': order['buyer_phone']
        }
    elif product['status'] == 'Sold':
        response['buyer_info'] = {
            'name': order['buyer_name'],
            'email': order['buyer_email'],
            'phone': order['buyer_phone']
        }
        
    return jsonify(response)

@app.route('/seller/status/confirm', methods=['POST'])
def confirm_payment():
    token = request.headers.get('Authorization')
    if not token:
        return jsonify({'error': 'Authorization token required'}), 401
    
    result = get_seller_status(token)
    if not result:
        return jsonify({'error': 'Invalid token'}), 403
    
    product, order = result
    if product['status'] != 'Pending':
        return jsonify({'error': 'Only pending orders can be confirmed'}), 400
    
    update_product_status(product['id'], 'Sold')
    return jsonify({'message': 'Payment confirmed, product sold'})

@app.route('/seller/status/cancel', methods=['POST'])
def cancel_order():
    token = request.headers.get('Authorization')
    if not token:
        return jsonify({'error': 'Authorization token required'}), 401
    
    result = get_seller_status(token)
    if not result:
        return jsonify({'error': 'Invalid token'}), 403
    
    product, order = result
    if product['status'] != 'Pending':
        return jsonify({'error': 'Only pending orders can be cancelled'}), 400
    
    update_product_status(product['id'], 'Available')
    return jsonify({'message': 'Order cancelled, product available again'})

@app.route('/buyer/order', methods=['GET'])
def buyer_order():
    token = request.headers.get('Authorization')
    if not token:
        return jsonify({'error': 'Authorization token required'}), 401
    
    result = get_buyer_order(token)
    if not result:
        return jsonify({'error': 'Invalid token'}), 403
    
    order, product = result
    return jsonify({
        'product': {
            'title': product['title'],
            'description': product['description']
        },
        'seller': {
            'name': product['seller_name'],
            'email': product['seller_email'],
            'location': product['location']
        },
        'status': order['status'],
        'buyer_token': token
    })

@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

if __name__ == '__main__':
    app.run(debug=True, port=5000)
