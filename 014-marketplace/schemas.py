import re

CATEGORIES = {'Electronics', 'Fashion', 'Home & Garden', 'Vehicles', 'Collectibles', 'Sports', 'Books', 'Other'}
CONDITIONS = {'new', 'like-new', 'good', 'fair'}

def validate_product_data(data):
    errors = []
    required_fields = ['title', 'description', 'price', 'category', 'condition', 'location', 'seller_name', 'seller_email']
    for field in required_fields:
        if field not in data or not str(data[field]).strip():
            errors.append(f'{field} is required')
    
    if 'price' in data:
        try:
            price = float(data['price'])
            if price < 0.01:
                errors.append('Price must be at least 0.01')
        except (ValueError, TypeError):
            errors.append('Invalid price format')
            
    if 'category' in data and data['category'] not in CATEGORIES:
        errors.append(f'Category must be one of {", ".join(CATEGORIES)}')
        
    if 'condition' in data and data['condition'] not in CONDITIONS:
        errors.append(f'Condition must be one of {", ".join(CONDITIONS)}')
    
    if 'seller_email' in data and not re.match(r'^[^@]+@[^@]+\.[^@]+$', str(data['seller_email'])):
        errors.append('Invalid seller email format')
        
    return errors

def validate_buyer_data(data):
    errors = []
    required_fields = ['name', 'email', 'phone']
    for field in required_fields:
        if field not in data or not str(data[field]).strip():
            errors.append(f'{field} is required')
            
    if 'name' in data and len(str(data['name']).strip()) < 2:
        errors.append('Buyer name must be at least 2 characters')
        
    if 'email' in data and not re.match(r'^[^@]+@[^@]+\.[^@]+$', str(data['email'])):
        errors.append('Invalid email format')
        
    return errors
