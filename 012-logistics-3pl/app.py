from flask import Flask, request, jsonify
import re
import os
from datetime import datetime
import string

app = Flask(__name__)

# Storage for quotes (in-memory for MVP)
quotes_data = []

# Admin password
ADMIN_PASSWORD = "apex-logistics-3421"

# Default destinations for ROI calculator
DEFAULT_DESTINATIONS = [
    {"name": "DC1 - Nashville Hub", "region": "SE", "cost": 22},
    {"name": "DC2 - Atlanta Metro", "region": "SE", "cost": 25},
    {"name": "DC3 - Birmingham", "region": "SE", "cost": 32},
    {"name": "DC4 - Charlotte", "region": "SE", "cost": 24},
    {"name": "DC5 - Jacksonville", "region": "SE", "cost": 28},
    {"name": "DC6 - Louisville", "region": "SE", "cost": 26},
    {"name": "DC7 - Little Rock", "region": "SE", "cost": 35},
    {"name": "DC8 - New Orleans", "region": "SE", "cost": 52},
    {"name": "DC9 - Mobile", "region": "SE", "cost": 48},
    {"name": "DC10 - Memphis Hub", "region": "SE", "cost": 18},
]

# Valid inquiry types
VALID_INQUIRY_TYPES = [
    "General Inquiry",
    "Service Question",
    "Partnership Opportunity",
    "Media/Press",
    "Other"
]

# Valid service interests
VALID_SERVICE_INTERESTS = [
    "Warehousing",
    "Cross-Docking & Transloading",
    "Transportation & Drayage",
    "Foreign Trade Zone (FTZ)",
    "Value-Added Services"
]

# Valid industries
VALID_INDUSTRIES = [
    "Food & Beverage",
    "Wine & Spirits",
    "Retail/CPG",
    "Agriculture/Floral",
    "Other"
]

# Valid timelines
VALID_TIMELINES = [
    "ASAP",
    "1-3 months",
    "3-6 months",
    "6+ months"
]

# Valid contact methods
VALID_CONTACT_METHODS = ["Email", "Phone"]


def parse_blog_file(filepath):
    """Parse a blog markdown file and extract metadata and body."""
    with open(filepath, 'r') as f:
        content = f.read()
    
    lines = content.split('\n')
    title = ""
    published = ""
    body_lines = []
    in_body = False
    
    for i, line in enumerate(lines):
        if line.startswith('# ') and not title:
            title = line[2:].strip()
        elif line.startswith('**Published:**'):
            published = line.split('**Published:**')[1].strip().strip('*')
        elif line.strip() == '---':
            in_body = True
            continue
        elif in_body:
            body_lines.append(line)
    
    body = '\n'.join(body_lines).strip()
    return {"title": title, "published": published, "body": body}


def get_all_blogs():
    """Get all blog posts sorted by publish date (newest first)."""
    blog_dir = 'assets/blogs'
    blogs = []
    
    for filename in os.listdir(blog_dir):
        if filename.endswith('.md'):
            filepath = os.path.join(blog_dir, filename)
            slug = filename[:-3]  # Remove .md extension
            data = parse_blog_file(filepath)
            data['slug'] = slug
            blogs.append(data)
    
    # Sort by published date (newest first)
    blogs.sort(key=lambda x: x['published'], reverse=True)
    return blogs


def get_excerpt(body, length=50):
    """Get excerpt of first 50 characters. If mid-word, include partial word and append …"""
    if len(body) <= length:
        return body
    
    excerpt = body[:length]
    
    # Check if we cut mid-word
    if length < len(body) and not body[length].isspace() and body[length] not in string.punctuation:
        # Find end of word or end of string
        for i in range(length, min(length + 20, len(body))):
            if body[i].isspace() or body[i] in string.punctuation:
                excerpt = body[:i]
                break
    
    return excerpt + "…"


def validate_phone(phone):
    """Validate 10-digit US phone format."""
    if not phone:
        return True  # Optional field
    
    # Remove all non-digits
    digits = re.sub(r'\D', '', phone)
    
    # Must be exactly 10 digits
    if len(digits) != 10:
        return False
    
    return True


def validate_email(email):
    """Validate email format."""
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return bool(re.match(pattern, email))


def calculate_roi(data):
    """Calculate ROI for all three scenarios."""
    # Step 1 - Shipment inputs
    pallets = data.get('annual_pallets', 0)
    port_split = data.get('port_split', 0)
    pallets_per_container = data.get('pallets_per_container', 20)
    storage_months = data.get('storage_months', 1.5)
    
    # Step 2 - Costs
    dray_se = data.get('dray_se', 420)
    dray_ne = data.get('dray_ne', 380)
    storage_se = data.get('storage_se', 9)
    storage_ne = data.get('storage_ne', 11)
    handling = data.get('handling', 6)
    risk_buffer = data.get('risk_buffer', 8)
    ftz_savings = data.get('ftz_savings', 5)
    
    # Step 3 - Destinations
    destinations = data.get('destinations', DEFAULT_DESTINATIONS)
    
    # Calculate derived values
    containers = pallets / pallets_per_container
    frac_east = port_split / 100
    frac_gulf = 1 - frac_east
    
    dest_se = sum(1 for d in destinations if d['region'] == 'SE')
    dest_ne = sum(1 for d in destinations if d['region'] == 'NE')
    dest_total = dest_se + dest_ne
    
    if dest_total == 0:
        frac_dest_se = 0
        frac_dest_ne = 0
    else:
        frac_dest_se = dest_se / dest_total
        frac_dest_ne = dest_ne / dest_total
    
    share = pallets / dest_total if dest_total > 0 else 0
    
    # Scenario A (SE-only)
    inbound_a = containers * (frac_east * dray_se + frac_gulf * dray_se * 1.3)
    storage_a = pallets * storage_months * storage_se
    handling_a = pallets * handling
    outbound_a = sum((d['cost'] * 1.5 if d['region'] == 'NE' else d['cost']) * share for d in destinations)
    total_a = (inbound_a + storage_a + handling_a + outbound_a) * (1 + risk_buffer / 100) * (1 - ftz_savings / 100)
    
    # Scenario B (NE-only)
    inbound_b = containers * (frac_east * dray_ne * 1.3 + frac_gulf * dray_ne)
    storage_b = pallets * storage_months * storage_ne
    handling_b = pallets * handling
    outbound_b = sum((d['cost'] * 1.5 if d['region'] == 'SE' else d['cost']) * share for d in destinations)
    total_b = (inbound_b + storage_b + handling_b + outbound_b) * (1 + risk_buffer / 100) * (1 - ftz_savings / 100)
    
    # Scenario C (Hybrid)
    inbound_c = containers * (frac_east * dray_se + frac_gulf * dray_ne)
    storage_c = pallets * storage_months * (frac_dest_se * storage_se + frac_dest_ne * storage_ne)
    handling_c = pallets * handling
    outbound_c = sum(d['cost'] * share for d in destinations)
    total_c = (inbound_c + storage_c + handling_c + outbound_c) * (1 + risk_buffer / 100) * (1 - ftz_savings / 100)
    
    # ROI calculations
    roi_b = (total_a - total_b) / total_a * 100 if total_a > 0 else 0
    roi_c = (total_a - total_c) / total_a * 100 if total_a > 0 else 0
    
    # Cost per pallet
    cost_per_pallet_a = total_a / pallets if pallets > 0 else 0
    cost_per_pallet_b = total_b / pallets if pallets > 0 else 0
    cost_per_pallet_c = total_c / pallets if pallets > 0 else 0
    
    return {
        "scenario_a": {
            "name": "SE-only",
            "total_cost": round(total_a, 2),
            "cost_per_pallet": round(cost_per_pallet_a, 2)
        },
        "scenario_b": {
            "name": "NE-only",
            "total_cost": round(total_b, 2),
            "cost_per_pallet": round(cost_per_pallet_b, 2),
            "roi": round(roi_b, 2)
        },
        "scenario_c": {
            "name": "Hybrid",
            "total_cost": round(total_c, 2),
            "cost_per_pallet": round(cost_per_pallet_c, 2),
            "roi": round(roi_c, 2)
        }
    }


# ==================== API ROUTES ====================

# Insights (Blog) Routes

@app.route('/api/insights', methods=['GET'])
def get_insights():
    """Get list of 3 blog posts (newest to oldest)."""
    blogs = get_all_blogs()[:3]
    
    result = []
    for blog in blogs:
        excerpt = get_excerpt(blog['body'])
        result.append({
            "slug": blog['slug'],
            "title": blog['title'],
            "published": blog['published'],
            "excerpt": excerpt
        })
    
    return jsonify(result)


@app.route('/api/insights/<slug>', methods=['GET'])
def get_insight(slug):
    """Get individual blog post by slug."""
    blogs = get_all_blogs()
    
    for blog in blogs:
        if blog['slug'] == slug:
            return jsonify({
                "slug": blog['slug'],
                "title": blog['title'],
                "published": blog['published'],
                "body": blog['body']
            })
    
    return jsonify({"error": "Post not found"}), 404


# Warehouse ROI Calculator Routes

@app.route('/api/roi/validate/step1', methods=['POST'])
def validate_step1():
    """Validate Step 1 - Shipment inputs."""
    data = request.get_json()
    
    errors = []
    
    # Annual pallets - required, > 0
    if 'annual_pallets' not in data:
        errors.append("annual_pallets is required")
    elif data['annual_pallets'] <= 0:
        errors.append("annual_pallets must be greater than 0")
    
    # Port split - required, 0-100
    if 'port_split' not in data:
        errors.append("port_split is required")
    elif not (0 <= data['port_split'] <= 100):
        errors.append("port_split must be between 0 and 100")
    
    # Pallets per container - default 20, > 0
    pallets_per_container = data.get('pallets_per_container', 20)
    if pallets_per_container <= 0:
        errors.append("pallets_per_container must be greater than 0")
    
    # Storage months - default 1.5, >= 0
    storage_months = data.get('storage_months', 1.5)
    if storage_months < 0:
        errors.append("storage_months must be >= 0")
    
    if errors:
        return jsonify({"valid": False, "errors": errors}), 400
    
    return jsonify({"valid": True})


@app.route('/api/roi/validate/step2', methods=['POST'])
def validate_step2():
    """Validate Step 2 - Costs inputs."""
    data = request.get_json()
    
    errors = []
    
    # Dray costs - required, >= 0
    if 'dray_se' not in data:
        errors.append("dray_se is required")
    elif data['dray_se'] < 0:
        errors.append("dray_se must be >= 0")
    
    if 'dray_ne' not in data:
        errors.append("dray_ne is required")
    elif data['dray_ne'] < 0:
        errors.append("dray_ne must be >= 0")
    
    # Storage rates - required, >= 0
    if 'storage_se' not in data:
        errors.append("storage_se is required")
    elif data['storage_se'] < 0:
        errors.append("storage_se must be >= 0")
    
    if 'storage_ne' not in data:
        errors.append("storage_ne is required")
    elif data['storage_ne'] < 0:
        errors.append("storage_ne must be >= 0")
    
    # Handling - required, >= 0
    if 'handling' not in data:
        errors.append("handling is required")
    elif data['handling'] < 0:
        errors.append("handling must be >= 0")
    
    # Risk buffer - required, 0-100
    if 'risk_buffer' not in data:
        errors.append("risk_buffer is required")
    elif not (0 <= data['risk_buffer'] <= 100):
        errors.append("risk_buffer must be between 0 and 100")
    
    # FTZ savings - required, 0-100
    if 'ftz_savings' not in data:
        errors.append("ftz_savings is required")
    elif not (0 <= data['ftz_savings'] <= 100):
        errors.append("ftz_savings must be between 0 and 100")
    
    if errors:
        return jsonify({"valid": False, "errors": errors}), 400
    
    return jsonify({"valid": True})


@app.route('/api/roi/validate/step3', methods=['POST'])
def validate_step3():
    """Validate Step 3 - Destinations inputs."""
    data = request.get_json()
    
    errors = []
    
    if 'destinations' not in data:
        errors.append("destinations is required")
    else:
        destinations = data['destinations']
        
        # Must have 1-10 rows
        if len(destinations) < 1:
            errors.append("Must have at least 1 destination")
        elif len(destinations) > 10:
            errors.append("Cannot have more than 10 destinations")
        else:
            for i, dest in enumerate(destinations):
                # Name - required, non-empty
                if 'name' not in dest or not dest['name']:
                    errors.append(f"Destination {i+1}: name is required")
                
                # Region - required, SE or NE
                if 'region' not in dest:
                    errors.append(f"Destination {i+1}: region is required")
                elif dest['region'] not in ['SE', 'NE']:
                    errors.append(f"Destination {i+1}: region must be SE or NE")
                
                # Cost/pallet - required, >= 0
                if 'cost' not in dest:
                    errors.append(f"Destination {i+1}: cost is required")
                elif dest['cost'] < 0:
                    errors.append(f"Destination {i+1}: cost must be >= 0")
    
    if errors:
        return jsonify({"valid": False, "errors": errors}), 400
    
    return jsonify({"valid": True})


@app.route('/api/roi/calculate', methods=['POST'])
def calculate_roi_endpoint():
    """Calculate ROI for all scenarios."""
    data = request.get_json()
    
    # Validate all steps
    step1_data = {
        'annual_pallets': data.get('annual_pallets'),
        'port_split': data.get('port_split'),
        'pallets_per_container': data.get('pallets_per_container', 20),
        'storage_months': data.get('storage_months', 1.5)
    }
    
    step2_data = {
        'dray_se': data.get('dray_se'),
        'dray_ne': data.get('dray_ne'),
        'storage_se': data.get('storage_se'),
        'storage_ne': data.get('storage_ne'),
        'handling': data.get('handling'),
        'risk_buffer': data.get('risk_buffer'),
        'ftz_savings': data.get('ftz_savings')
    }
    
    step3_data = {'destinations': data.get('destinations', DEFAULT_DESTINATIONS)}
    
    # Validate each step
    step1_response = validate_step1()
    if isinstance(step1_response, tuple):
        return step1_response
    
    step2_response = validate_step2()
    if isinstance(step2_response, tuple):
        return step2_response
    
    step3_response = validate_step3()
    if isinstance(step3_response, tuple):
        return step3_response
    
    # Calculate ROI
    result = calculate_roi(data)
    return jsonify(result)


# Contact Form Route

@app.route('/api/contact', methods=['POST'])
def contact_form():
    """Handle contact form submission."""
    data = request.get_json()
    
    errors = []
    
    # Name - required, non-empty
    if 'name' not in data or not data['name']:
        errors.append("Name is required")
    
    # Email - required, valid
    if 'email' not in data or not data['email']:
        errors.append("Email is required")
    elif not validate_email(data['email']):
        errors.append("Invalid email format")
    
    # Phone - optional, valid if provided
    if 'phone' in data and data['phone']:
        if not validate_phone(data['phone']):
            errors.append("Invalid phone format (10-digit US format required)")
    
    # Inquiry Type - required, must be valid
    if 'inquiry_type' not in data or not data['inquiry_type']:
        errors.append("Inquiry Type is required")
    elif data['inquiry_type'] not in VALID_INQUIRY_TYPES:
        errors.append("Invalid inquiry type")
    
    # Message - required, min 10 chars
    if 'message' not in data or not data['message']:
        errors.append("Message is required")
    elif len(data['message']) < 10:
        errors.append("Message must be at least 10 characters")
    
    if errors:
        return jsonify({"error": "Validation failed", "errors": errors}), 400
    
    return jsonify({
        "success": True,
        "message": "Message sent successfully! We'll respond within 24 hours."
    })


# Quote Request Route

@app.route('/api/quote', methods=['POST'])
def quote_request():
    """Handle quote request submission."""
    data = request.get_json()
    
    errors = []
    
    # Name - required, non-empty
    if 'name' not in data or not data['name']:
        errors.append("Name is required")
    
    # Email - required, valid
    if 'email' not in data or not data['email']:
        errors.append("Email is required")
    elif not validate_email(data['email']):
        errors.append("Invalid email format")
    
    # Phone - required if Contact Method = Phone
    contact_method = data.get('contact_method')
    if contact_method == 'Phone':
        if 'phone' not in data or not data['phone']:
            errors.append("Phone is required for Phone contact method")
        elif not validate_phone(data['phone']):
            errors.append("Invalid phone format (10-digit US format required)")
    
    # Company - required, non-empty
    if 'company' not in data or not data['company']:
        errors.append("Company is required")
    
    # Service Interests - required, at least 1
    if 'service_interests' not in data or not data['service_interests']:
        errors.append("At least one service interest is required")
    else:
        service_interests = data['service_interests']
        if not isinstance(service_interests, list) or len(service_interests) < 1:
            errors.append("At least one service interest is required")
        else:
            for interest in service_interests:
                if interest not in VALID_SERVICE_INTERESTS:
                    errors.append(f"Invalid service interest: {interest}")
                    break
    
    # Industry - required, must be valid
    if 'industry' not in data or not data['industry']:
        errors.append("Industry is required")
    elif data['industry'] not in VALID_INDUSTRIES:
        errors.append("Invalid industry")
    
    # Estimated Volume - required, >= 0
    if 'estimated_volume' not in data:
        errors.append("Estimated Volume is required")
    elif data['estimated_volume'] < 0:
        errors.append("Estimated Volume must be >= 0")
    
    # Timeline - required, must be valid
    if 'timeline' not in data or not data['timeline']:
        errors.append("Timeline is required")
    elif data['timeline'] not in VALID_TIMELINES:
        errors.append("Invalid timeline")
    
    # Contact Method - required, must be valid
    if 'contact_method' not in data or not data['contact_method']:
        errors.append("Contact Method is required")
    elif data['contact_method'] not in VALID_CONTACT_METHODS:
        errors.append("Invalid contact method")
    
    if errors:
        return jsonify({"error": "Validation failed", "errors": errors}), 400
    
    # Store quote
    quote = {
        "timestamp": datetime.now().isoformat(),
        "name": data['name'],
        "email": data['email'],
        "phone": data.get('phone', ''),
        "company": data['company'],
        "service_interests": data['service_interests'],
        "industry": data['industry'],
        "estimated_volume": data['estimated_volume'],
        "timeline": data['timeline'],
        "contact_method": data['contact_method'],
        "message": data.get('message', '')
    }
    quotes_data.insert(0, quote)  # Add to beginning for newest first
    
    return jsonify({
        "success": True,
        "message": "Request sent successfully! We'll respond within 4 business hours."
    })


# Quotes Admin Routes

@app.route('/api/admin/quotes', methods=['GET'])
def admin_quotes():
    """Get quotes list (password protected)."""
    password = request.headers.get('Authorization', '').replace('Bearer ', '')
    
    if password != ADMIN_PASSWORD:
        return jsonify({"error": "Unauthorized"}), 401
    
    # Return quotes newest to oldest
    result = []
    for quote in quotes_data:
        result.append({
            "timestamp": quote['timestamp'],
            "name": quote['name'],
            "company": quote['company'],
            "email": quote['email'],
            "phone": quote['phone'],
            "service_interests": quote['service_interests'],
            "industry": quote['industry'],
            "estimated_volume": quote['estimated_volume'],
            "timeline": quote['timeline'],
            "contact_method": quote['contact_method'],
            "message": quote['message']
        })
    
    return jsonify(result)


if __name__ == '__main__':
    app.run(debug=False, host='0.0.0.0', port=8080)
