import os
import re
from datetime import datetime
from flask import Flask, request, jsonify

app = Flask(__name__)

BLOGS_DIR = "assets/blogs"

# In-memory storage
contact_submissions = []
quote_requests = []


def parse_phone(phone):
    if phone is None:
        return None
    pattern = r'^(?:\d{10}|\d{3}-\d{3}-\d{4}|\(\d{3}\)\s?\d{3}-?\d{4})$'
    if re.match(pattern, str(phone).strip()):
        return str(phone).strip()
    return None


def validate_email(email):
    if not email or not isinstance(email, str):
        return False
    pattern = r'^[^@\s]+@[^@\s]+\.[^@\s]+$'
    return re.match(pattern, email) is not None


def parse_blogs():
    posts = []
    if not os.path.isdir(BLOGS_DIR):
        return posts
    for filename in os.listdir(BLOGS_DIR):
        if not filename.endswith('.md'):
            continue
        slug = filename[:-3]
        filepath = os.path.join(BLOGS_DIR, filename)
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        lines = content.splitlines()
        title = None
        published = None
        for line in lines:
            if line.startswith('# ') and title is None:
                title = line[2:].strip()
            if '**Published:**' in line:
                published = line.split('**Published:**')[1].strip()
            if title and published:
                break
        # Body is everything after the first standalone "---"
        parts = content.split('\n---\n', 1)
        body = parts[1].strip() if len(parts) > 1 else content.strip()
        if title and published:
            try:
                pub_date = datetime.strptime(published, '%Y-%m-%d').date()
            except ValueError:
                pub_date = datetime.min.date()
            posts.append({
                'slug': slug,
                'title': title,
                'publishedDate': published,
                'pub_date': pub_date,
                'body': body
            })
    posts.sort(key=lambda x: x['pub_date'], reverse=True)
    return posts


def make_excerpt(body):
    text = body.strip()
    if len(text) <= 50:
        return text
    truncated = text[:50]
    if len(text) > 50:
        next_char = text[50]
        if next_char not in (' ', '\n', '\t', '\r') and truncated[-1] not in (' ', '\n', '\t', '\r'):
            idx = 50
            while idx < len(text) and text[idx] not in (' ', '\n', '\t', '\r'):
                idx += 1
            return text[:idx] + '…'
    return truncated


blogs = parse_blogs()


@app.route('/api/insights', methods=['GET'])
def list_insights():
    result = []
    for post in blogs[:3]:
        result.append({
            'slug': post['slug'],
            'title': post['title'],
            'excerpt': make_excerpt(post['body']),
            'publishedDate': post['publishedDate']
        })
    return jsonify(result)


@app.route('/api/insights/<slug>', methods=['GET'])
def get_insight(slug):
    for post in blogs:
        if post['slug'] == slug:
            return jsonify({
                'title': post['title'],
                'body': post['body']
            })
    return jsonify({'error': 'Not found'}), 404


@app.route('/api/calculator/warehouse-roi', methods=['POST'])
def warehouse_roi():
    data = request.get_json(silent=True) or {}
    errors = []

    # Step 1
    try:
        annual_pallets = data.get('annualPallets')
        if annual_pallets is None:
            raise ValueError('annualPallets is required')
        annual_pallets = float(annual_pallets)
        if annual_pallets <= 0:
            raise ValueError('annualPallets must be > 0')
    except (ValueError, TypeError) as e:
        errors.append({'field': 'annualPallets', 'message': str(e)})

    try:
        port_split = data.get('portSplit')
        if port_split is None:
            raise ValueError('portSplit is required')
        port_split = float(port_split)
        if not (0 <= port_split <= 100):
            raise ValueError('portSplit must be between 0 and 100')
    except (ValueError, TypeError) as e:
        errors.append({'field': 'portSplit', 'message': str(e)})

    try:
        pallets_per_container = data.get('palletsPerContainer', 20)
        pallets_per_container = float(pallets_per_container)
        if pallets_per_container <= 0:
            raise ValueError('palletsPerContainer must be > 0')
    except (ValueError, TypeError) as e:
        errors.append({'field': 'palletsPerContainer', 'message': str(e)})

    try:
        storage_months = data.get('storageMonths', 1.5)
        storage_months = float(storage_months)
        if storage_months < 0:
            raise ValueError('storageMonths must be >= 0')
    except (ValueError, TypeError) as e:
        errors.append({'field': 'storageMonths', 'message': str(e)})

    # Step 2
    try:
        dray_se = data.get('drayCostSE', 420)
        dray_se = float(dray_se)
        if dray_se < 0:
            raise ValueError('drayCostSE must be >= 0')
    except (ValueError, TypeError) as e:
        errors.append({'field': 'drayCostSE', 'message': str(e)})

    try:
        dray_ne = data.get('drayCostNE', 380)
        dray_ne = float(dray_ne)
        if dray_ne < 0:
            raise ValueError('drayCostNE must be >= 0')
    except (ValueError, TypeError) as e:
        errors.append({'field': 'drayCostNE', 'message': str(e)})

    try:
        storage_se = data.get('storageRateSE', 9)
        storage_se = float(storage_se)
        if storage_se < 0:
            raise ValueError('storageRateSE must be >= 0')
    except (ValueError, TypeError) as e:
        errors.append({'field': 'storageRateSE', 'message': str(e)})

    try:
        storage_ne = data.get('storageRateNE', 11)
        storage_ne = float(storage_ne)
        if storage_ne < 0:
            raise ValueError('storageRateNE must be >= 0')
    except (ValueError, TypeError) as e:
        errors.append({'field': 'storageRateNE', 'message': str(e)})

    try:
        handling = data.get('handlingCostPerPallet', 6)
        handling = float(handling)
        if handling < 0:
            raise ValueError('handlingCostPerPallet must be >= 0')
    except (ValueError, TypeError) as e:
        errors.append({'field': 'handlingCostPerPallet', 'message': str(e)})

    try:
        risk = data.get('riskBufferPercent', 8)
        risk = float(risk)
        if not (0 <= risk <= 100):
            raise ValueError('riskBufferPercent must be between 0 and 100')
    except (ValueError, TypeError) as e:
        errors.append({'field': 'riskBufferPercent', 'message': str(e)})

    try:
        ftz = data.get('ftzSavingsPercent', 5)
        ftz = float(ftz)
        if not (0 <= ftz <= 100):
            raise ValueError('ftzSavingsPercent must be between 0 and 100')
    except (ValueError, TypeError) as e:
        errors.append({'field': 'ftzSavingsPercent', 'message': str(e)})

    # Step 3
    destinations = data.get('destinations')
    if not isinstance(destinations, list) or not (1 <= len(destinations) <= 10):
        errors.append({'field': 'destinations', 'message': 'destinations must be a list of 1 to 10 rows'})
    else:
        for idx, dest in enumerate(destinations):
            if not isinstance(dest, dict):
                errors.append({'field': f'destinations[{idx}]', 'message': 'must be an object'})
                continue
            name = dest.get('name')
            region = dest.get('region')
            cost = dest.get('costPerPallet')
            if not name or not str(name).strip():
                errors.append({'field': f'destinations[{idx}].name', 'message': 'name must be non-empty'})
            if region not in ('SE', 'NE'):
                errors.append({'field': f'destinations[{idx}].region', 'message': 'region must be SE or NE'})
            try:
                cost = float(cost)
                if cost < 0:
                    raise ValueError
            except (ValueError, TypeError):
                errors.append({'field': f'destinations[{idx}].costPerPallet', 'message': 'costPerPallet must be >= 0'})

    if errors:
        return jsonify({'errors': errors}), 400

    # Calculations
    pallets = annual_pallets
    containers = pallets / pallets_per_container
    frac_east = port_split / 100.0
    frac_gulf = 1.0 - frac_east

    dest_se_count = sum(1 for d in destinations if d.get('region') == 'SE')
    dest_ne_count = sum(1 for d in destinations if d.get('region') == 'NE')
    dest_total = dest_se_count + dest_ne_count
    frac_dest_se = dest_se_count / dest_total if dest_total > 0 else 0
    frac_dest_ne = dest_ne_count / dest_total if dest_total > 0 else 0
    share = pallets / dest_total if dest_total > 0 else 0

    # Scenario A (SE-only)
    inbound_a = containers * (frac_east * dray_se + frac_gulf * dray_se * 1.3)
    storage_a = pallets * storage_months * storage_se
    handling_a = pallets * handling
    outbound_a = 0.0
    for d in destinations:
        cost = float(d['costPerPallet'])
        if d['region'] == 'NE':
            outbound_a += cost * 1.5 * share
        else:
            outbound_a += cost * share
    total_a = (inbound_a + storage_a + handling_a + outbound_a) * (1 + risk / 100.0) * (1 - ftz / 100.0)

    # Scenario B (NE-only)
    inbound_b = containers * (frac_east * dray_ne * 1.3 + frac_gulf * dray_ne)
    storage_b = pallets * storage_months * storage_ne
    handling_b = pallets * handling
    outbound_b = 0.0
    for d in destinations:
        cost = float(d['costPerPallet'])
        if d['region'] == 'SE':
            outbound_b += cost * 1.5 * share
        else:
            outbound_b += cost * share
    total_b = (inbound_b + storage_b + handling_b + outbound_b) * (1 + risk / 100.0) * (1 - ftz / 100.0)

    # Scenario C (Hybrid)
    inbound_c = containers * (frac_east * dray_se + frac_gulf * dray_ne)
    storage_c = pallets * storage_months * (frac_dest_se * storage_se + frac_dest_ne * storage_ne)
    handling_c = pallets * handling
    outbound_c = sum(float(d['costPerPallet']) * share for d in destinations)
    total_c = (inbound_c + storage_c + handling_c + outbound_c) * (1 + risk / 100.0) * (1 - ftz / 100.0)

    def scenario_result(total):
        return {
            'totalCost': round(total, 2),
            'costPerPallet': round(total / pallets, 2) if pallets != 0 else 0
        }

    result_a = scenario_result(total_a)
    result_b = scenario_result(total_b)
    result_c = scenario_result(total_c)

    roi_b = (total_a - total_b) / total_a * 100.0 if total_a != 0 else 0.0
    roi_c = (total_a - total_c) / total_a * 100.0 if total_a != 0 else 0.0

    return jsonify({
        'scenarioA': {**result_a, 'roi': 0.0},
        'scenarioB': {**result_b, 'roi': round(roi_b, 2)},
        'scenarioC': {**result_c, 'roi': round(roi_c, 2)}
    })


@app.route('/api/contact', methods=['POST'])
def contact_form():
    data = request.get_json(silent=True) or {}
    errors = []

    name = data.get('name')
    if not name or not str(name).strip():
        errors.append({'field': 'name', 'message': 'Name is required'})

    email = data.get('email')
    if not email or not validate_email(email):
        errors.append({'field': 'email', 'message': 'Valid email is required'})

    phone = data.get('phone')
    if phone and not parse_phone(phone):
        errors.append({'field': 'phone', 'message': 'Invalid phone format'})

    inquiry_type = data.get('inquiryType')
    valid_types = {'General Inquiry', 'Service Question', 'Partnership Opportunity', 'Media/Press', 'Other'}
    if not inquiry_type or inquiry_type not in valid_types:
        errors.append({'field': 'inquiryType', 'message': 'Invalid inquiry type'})

    message = data.get('message')
    if not message or len(str(message).strip()) < 10:
        errors.append({'field': 'message', 'message': 'Message must be at least 10 characters'})

    if errors:
        return jsonify({'errors': errors}), 400

    contact_submissions.append({
        'name': str(name).strip(),
        'email': str(email).strip(),
        'phone': phone,
        'company': data.get('company'),
        'inquiryType': inquiry_type,
        'subject': data.get('subject'),
        'message': str(message).strip()
    })

    return jsonify({'message': "Message sent successfully! We'll respond within 24 hours."})


@app.route('/api/quote', methods=['POST'])
def quote_request():
    data = request.get_json(silent=True) or {}
    errors = []

    name = data.get('name')
    if not name or not str(name).strip():
        errors.append({'field': 'name', 'message': 'Name is required'})

    email = data.get('email')
    if not email or not validate_email(email):
        errors.append({'field': 'email', 'message': 'Valid email is required'})

    company = data.get('company')
    if not company or not str(company).strip():
        errors.append({'field': 'company', 'message': 'Company is required'})

    service_interests = data.get('serviceInterests')
    valid_services = {
        'Warehousing', 'Cross-Docking & Transloading', 'Transportation & Drayage',
        'Foreign Trade Zone (FTZ)', 'Value-Added Services'
    }
    if not isinstance(service_interests, list) or len(service_interests) == 0:
        errors.append({'field': 'serviceInterests', 'message': 'At least one service interest is required'})
    else:
        for s in service_interests:
            if s not in valid_services:
                errors.append({'field': 'serviceInterests', 'message': f'Invalid service interest: {s}'})
                break

    industry = data.get('industry')
    valid_industries = {'Food & Beverage', 'Wine & Spirits', 'Retail/CPG', 'Agriculture/Floral', 'Other'}
    if not industry or industry not in valid_industries:
        errors.append({'field': 'industry', 'message': 'Invalid industry'})

    try:
        volume = data.get('estimatedVolume')
        if volume is None:
            raise ValueError('estimatedVolume is required')
        volume = float(volume)
        if volume < 0:
            raise ValueError('estimatedVolume must be >= 0')
    except (ValueError, TypeError):
        errors.append({'field': 'estimatedVolume', 'message': 'Estimated Volume must be >= 0'})

    timeline = data.get('timeline')
    valid_timelines = {'ASAP (0–30 days)', '1–3 months', '3–6 months', '6+ months'}
    if not timeline or timeline not in valid_timelines:
        errors.append({'field': 'timeline', 'message': 'Invalid timeline'})

    contact_method = data.get('contactMethod')
    valid_methods = {'Email', 'Phone'}
    if not contact_method or contact_method not in valid_methods:
        errors.append({'field': 'contactMethod', 'message': 'Invalid contact method'})

    phone = data.get('phone')
    if contact_method == 'Phone':
        if not phone or not parse_phone(phone):
            errors.append({'field': 'phone', 'message': 'Valid phone is required when contact method is Phone'})
    else:
        if phone and not parse_phone(phone):
            errors.append({'field': 'phone', 'message': 'Invalid phone format'})

    if errors:
        return jsonify({'errors': errors}), 400

    quote = {
        'timestamp': datetime.utcnow().isoformat() + 'Z',
        'name': str(name).strip(),
        'company': str(company).strip(),
        'email': str(email).strip(),
        'phone': phone,
        'serviceInterests': service_interests,
        'industry': industry,
        'estimatedVolume': volume,
        'timeline': timeline,
        'contactMethod': contact_method,
        'message': data.get('message')
    }
    quote_requests.append(quote)

    return jsonify({'message': "Request sent successfully! We'll respond within 4 business hours."})


@app.route('/api/admin/quotes', methods=['GET'])
def quotes_admin():
    password = request.args.get('password')
    if password != 'apex-logistics-3421':
        return jsonify({'error': 'Unauthorized'}), 401
    result = sorted(quote_requests, key=lambda x: x['timestamp'], reverse=True)
    return jsonify(result)


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 5000)))
