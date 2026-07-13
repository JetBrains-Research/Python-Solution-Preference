from flask import Flask, request, jsonify
import re
import os
import datetime
import uuid

app = Flask(__name__)

BLOG_DIR = os.path.join(os.path.dirname(__file__), 'assets', 'blogs')

SLUGS = ['ftz-vs-bonded-warehouse', 'cross-dock-near-port', 'how-to-choose-a-3pl']

QUOTES = []  # in-memory storage
ADMIN_PASSWORD = "apex-logistics-3421"

EMAIL_RE = re.compile(r'^[^\s@]+@[^\s@]+\.[^\s@]+$')

INQUIRY_TYPES = {"General Inquiry", "Service Question", "Partnership Opportunity", "Media/Press", "Other"}
SERVICE_INTERESTS_SET = {"Warehousing", "Cross-Docking & Transloading", "Transportation & Drayage", "Foreign Trade Zone (FTZ)", "Value-Added Services"}
INDUSTRIES = {"Food & Beverage", "Wine & Spirits", "Retail/CPG", "Agriculture/Floral", "Other"}
TIMELINES = {"ASAP (0–30 days)", "1–3 months", "3–6 months", "6+ months"}
CONTACT_METHODS = {"Email", "Phone"}


def parse_blog(slug):
    path = os.path.join(BLOG_DIR, slug + '.md')
    if not os.path.exists(path):
        return None
    with open(path, 'r') as f:
        content = f.read()
    lines = content.split('\n')
    title = None
    published = None
    body_start_idx = None
    for i, line in enumerate(lines):
        if title is None and line.startswith('# '):
            title = line[2:].strip()
        m = re.match(r'\*\*Published:\*\*\s*(.+)', line)
        if m:
            published = m.group(1).strip()
        if line.strip() == '---' and body_start_idx is None and i > 0:
            body_start_idx = i + 1
            break
    body = '\n'.join(lines[body_start_idx:]).strip() if body_start_idx else ''
    return {
        'slug': slug,
        'title': title,
        'published': published,
        'body': body,
    }


def make_excerpt(body):
    # normalize whitespace-ish for excerpt: take raw first 50 chars
    if len(body) <= 50:
        return body
    excerpt = body[:50]
    # if next char is not whitespace, we are mid-word: extend to word boundary
    if not body[50].isspace():
        j = 50
        while j < len(body) and not body[j].isspace():
            excerpt += body[j]
            j += 1
        excerpt += '…'
    else:
        # ended at word boundary but there is more content; still append …
        excerpt += '…'
    return excerpt


@app.route('/api/insights', methods=['GET'])
def list_insights():
    posts = []
    for slug in SLUGS:
        p = parse_blog(slug)
        if p:
            posts.append(p)
    # sort newest to oldest
    posts.sort(key=lambda x: x['published'], reverse=True)
    posts = posts[:3]
    result = []
    for p in posts:
        result.append({
            'slug': p['slug'],
            'title': p['title'],
            'published': p['published'],
            'excerpt': make_excerpt(p['body']),
        })
    return jsonify(result)


@app.route('/api/insights/<slug>', methods=['GET'])
def get_insight(slug):
    if slug not in SLUGS:
        return jsonify({'error': 'not found'}), 404
    p = parse_blog(slug)
    if not p:
        return jsonify({'error': 'not found'}), 404
    return jsonify({'slug': p['slug'], 'title': p['title'], 'body': p['body']})


def validate_phone(phone):
    if phone is None:
        return False
    digits = re.sub(r'\D', '', phone)
    return len(digits) == 10


def validate_email(email):
    return isinstance(email, str) and bool(EMAIL_RE.match(email))


# ---- ROI Calculator ----

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


@app.route('/api/roi/defaults', methods=['GET'])
def roi_defaults():
    return jsonify({
        'shipment': {
            'palletsPerContainer': 20,
            'storageMonths': 1.5,
        },
        'costs': {
            'draySE': 420,
            'drayNE': 380,
            'storageSE': 9,
            'storageNE': 11,
            'handling': 6,
            'riskBuffer': 8,
            'ftzSavings': 5,
        },
        'destinations': DEFAULT_DESTINATIONS,
    })


def validate_step1(data):
    errors = []
    try:
        pallets = float(data.get('annualPallets'))
        if pallets <= 0:
            errors.append('annualPallets must be > 0')
    except (TypeError, ValueError):
        errors.append('annualPallets required and numeric')
        pallets = None
    try:
        port = float(data.get('portSplit'))
        if port < 0 or port > 100:
            errors.append('portSplit must be 0-100')
    except (TypeError, ValueError):
        errors.append('portSplit required and numeric')
        port = None
    ppc = data.get('palletsPerContainer', 20)
    try:
        ppc = float(ppc)
        if ppc <= 0:
            errors.append('palletsPerContainer must be > 0')
    except (TypeError, ValueError):
        errors.append('palletsPerContainer must be numeric')
        ppc = None
    months = data.get('storageMonths', 1.5)
    try:
        months = float(months)
        if months < 0:
            errors.append('storageMonths must be >= 0')
    except (TypeError, ValueError):
        errors.append('storageMonths must be numeric')
        months = None
    return errors, {'annualPallets': pallets, 'portSplit': port, 'palletsPerContainer': ppc, 'storageMonths': months}


def validate_step2(data):
    errors = []
    result = {}
    for key, default in [('draySE', 420), ('drayNE', 380), ('storageSE', 9), ('storageNE', 11), ('handling', 6)]:
        val = data.get(key, default)
        try:
            val = float(val)
            if val < 0:
                errors.append(f'{key} must be >= 0')
        except (TypeError, ValueError):
            errors.append(f'{key} must be numeric')
            val = None
        result[key] = val
    for key, default in [('riskBuffer', 8), ('ftzSavings', 5)]:
        val = data.get(key, default)
        try:
            val = float(val)
            if val < 0 or val > 100:
                errors.append(f'{key} must be 0-100')
        except (TypeError, ValueError):
            errors.append(f'{key} must be numeric')
            val = None
        result[key] = val
    return errors, result


def validate_step3(data):
    errors = []
    dests = data.get('destinations')
    if not isinstance(dests, list) or len(dests) < 1 or len(dests) > 10:
        errors.append('destinations must be a list of 1-10 rows')
        return errors, []
    validated = []
    for i, d in enumerate(dests):
        name = d.get('name', '')
        region = d.get('region', '')
        cost = d.get('cost')
        if not isinstance(name, str) or not name.strip():
            errors.append(f'row {i}: name required')
        if region not in ('SE', 'NE'):
            errors.append(f'row {i}: region must be SE or NE')
        try:
            cost = float(cost)
            if cost < 0:
                errors.append(f'row {i}: cost must be >= 0')
        except (TypeError, ValueError):
            errors.append(f'row {i}: cost must be numeric')
            cost = None
        validated.append({'name': name, 'region': region, 'cost': cost})
    return errors, validated


@app.route('/api/roi/step1', methods=['POST'])
def roi_step1():
    data = request.get_json(force=True, silent=True) or {}
    errors, values = validate_step1(data)
    if errors:
        return jsonify({'errors': errors}), 400
    return jsonify({'ok': True, 'values': values})


@app.route('/api/roi/step2', methods=['POST'])
def roi_step2():
    data = request.get_json(force=True, silent=True) or {}
    errors, values = validate_step2(data)
    if errors:
        return jsonify({'errors': errors}), 400
    return jsonify({'ok': True, 'values': values})


@app.route('/api/roi/step3', methods=['POST'])
def roi_step3():
    data = request.get_json(force=True, silent=True) or {}
    errors, values = validate_step3(data)
    if errors:
        return jsonify({'errors': errors}), 400
    return jsonify({'ok': True, 'destinations': values})


@app.route('/api/roi/calculate', methods=['POST'])
def roi_calculate():
    data = request.get_json(force=True, silent=True) or {}
    step1 = data.get('shipment', {})
    step2 = data.get('costs', {})
    step3 = {'destinations': data.get('destinations')}
    all_errors = []
    e1, v1 = validate_step1(step1)
    e2, v2 = validate_step2(step2)
    e3, v3 = validate_step3(step3)
    all_errors.extend(e1)
    all_errors.extend(e2)
    all_errors.extend(e3)
    if all_errors:
        return jsonify({'errors': all_errors}), 400

    pallets = v1['annualPallets']
    port_split = v1['portSplit']
    ppc = v1['palletsPerContainer']
    months = v1['storageMonths']

    draySE = v2['draySE']
    drayNE = v2['drayNE']
    storageSE = v2['storageSE']
    storageNE = v2['storageNE']
    handling = v2['handling']
    risk = v2['riskBuffer']
    ftz = v2['ftzSavings']

    dests = v3
    containers = pallets / ppc
    fracEast = port_split / 100.0
    fracGulf = 1 - fracEast
    destSE = sum(1 for d in dests if d['region'] == 'SE')
    destNE = sum(1 for d in dests if d['region'] == 'NE')
    destTotal = destSE + destNE
    fracDestSE = destSE / destTotal
    fracDestNE = destNE / destTotal
    share = pallets / destTotal

    # Scenario A
    inboundA = containers * (fracEast * draySE + fracGulf * draySE * 1.3)
    storageA = pallets * months * storageSE
    handlingA = pallets * handling
    outboundA = sum((d['cost'] * 1.5 if d['region'] == 'NE' else d['cost']) * share for d in dests)
    totalA = (inboundA + storageA + handlingA + outboundA) * (1 + risk / 100) * (1 - ftz / 100)

    # Scenario B
    inboundB = containers * (fracEast * drayNE * 1.3 + fracGulf * drayNE)
    storageB = pallets * months * storageNE
    handlingB = pallets * handling
    outboundB = sum((d['cost'] * 1.5 if d['region'] == 'SE' else d['cost']) * share for d in dests)
    totalB = (inboundB + storageB + handlingB + outboundB) * (1 + risk / 100) * (1 - ftz / 100)

    # Scenario C
    inboundC = containers * (fracEast * draySE + fracGulf * drayNE)
    storageC = pallets * months * (fracDestSE * storageSE + fracDestNE * storageNE)
    handlingC = pallets * handling
    outboundC = sum(d['cost'] * share for d in dests)
    totalC = (inboundC + storageC + handlingC + outboundC) * (1 + risk / 100) * (1 - ftz / 100)

    roiB = (totalA - totalB) / totalA * 100 if totalA else 0
    roiC = (totalA - totalC) / totalA * 100 if totalA else 0

    return jsonify({
        'scenarioA': {'total': totalA, 'costPerPallet': totalA / pallets, 'roi': 0},
        'scenarioB': {'total': totalB, 'costPerPallet': totalB / pallets, 'roi': roiB},
        'scenarioC': {'total': totalC, 'costPerPallet': totalC / pallets, 'roi': roiC},
    })


# ---- Contact form ----

@app.route('/api/contact', methods=['POST'])
def contact():
    data = request.get_json(force=True, silent=True) or {}
    errors = []
    name = data.get('name', '')
    email = data.get('email', '')
    phone = data.get('phone')
    inquiry = data.get('inquiryType', '')
    message = data.get('message', '')
    if not isinstance(name, str) or not name.strip():
        errors.append('name required')
    if not validate_email(email):
        errors.append('valid email required')
    if phone is not None and phone != '':
        if not validate_phone(phone):
            errors.append('valid phone required if provided')
    if inquiry not in INQUIRY_TYPES:
        errors.append('inquiryType required and must be one of allowed values')
    if not isinstance(message, str) or len(message.strip()) < 10:
        errors.append('message required, min 10 chars')
    if errors:
        return jsonify({'errors': errors}), 400
    return jsonify({'message': "Message sent successfully! We'll respond within 24 hours."})


# ---- Quote request ----

@app.route('/api/quote', methods=['POST'])
def submit_quote():
    data = request.get_json(force=True, silent=True) or {}
    errors = []
    name = data.get('name', '')
    email = data.get('email', '')
    phone = data.get('phone')
    company = data.get('company', '')
    service_interests = data.get('serviceInterests', [])
    industry = data.get('industry', '')
    volume = data.get('estimatedVolume')
    timeline = data.get('timeline', '')
    contact_method = data.get('contactMethod', '')
    message = data.get('message', '')

    if not isinstance(name, str) or not name.strip():
        errors.append('name required')
    if not validate_email(email):
        errors.append('valid email required')
    if not isinstance(company, str) or not company.strip():
        errors.append('company required')
    if not isinstance(service_interests, list) or len(service_interests) < 1:
        errors.append('at least one service interest required')
    else:
        for s in service_interests:
            if s not in SERVICE_INTERESTS_SET:
                errors.append(f'invalid service interest: {s}')
    if industry not in INDUSTRIES:
        errors.append('industry required and must be one of allowed values')
    try:
        volume_v = float(volume)
        if volume_v < 0:
            errors.append('estimatedVolume must be >= 0')
    except (TypeError, ValueError):
        errors.append('estimatedVolume required and numeric')
    if timeline not in TIMELINES:
        errors.append('timeline required and must be one of allowed values')
    if contact_method not in CONTACT_METHODS:
        errors.append('contactMethod required (Email or Phone)')
    if contact_method == 'Phone':
        if not phone or not validate_phone(phone):
            errors.append('valid phone required when contact method is Phone')
    elif phone:
        if not validate_phone(phone):
            errors.append('valid phone required if provided')
    if errors:
        return jsonify({'errors': errors}), 400

    quote = {
        'id': str(uuid.uuid4()),
        'timestamp': datetime.datetime.utcnow().isoformat() + 'Z',
        'name': name,
        'email': email,
        'phone': phone or '',
        'company': company,
        'serviceInterests': service_interests,
        'industry': industry,
        'estimatedVolume': volume_v,
        'timeline': timeline,
        'contactMethod': contact_method,
        'message': message or '',
    }
    QUOTES.append(quote)
    return jsonify({'message': "Request sent successfully! We'll respond within 4 business hours.", 'id': quote['id']})


# ---- Quotes Admin ----

@app.route('/api/admin/quotes', methods=['GET', 'POST'])
def admin_quotes():
    if request.method == 'POST':
        data = request.get_json(force=True, silent=True) or {}
        password = data.get('password', '')
    else:
        password = request.headers.get('X-Admin-Password', '') or request.args.get('password', '')
    if password != ADMIN_PASSWORD:
        return jsonify({'error': 'unauthorized'}), 401
    sorted_quotes = sorted(QUOTES, key=lambda q: q['timestamp'], reverse=True)
    return jsonify(sorted_quotes)


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5070, debug=False)
