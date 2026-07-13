from flask import Flask, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import json

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///furniture_delivery.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)


# ========== MODELS ==========

class Settings(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    rural_rate = db.Column(db.Float, default=0.0)
    assembly_rate = db.Column(db.Float, default=0.0)
    rubbish_rate = db.Column(db.Float, default=0.0)

class Location(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    type = db.Column(db.String(50), nullable=False)  # store/warehouse/supplier
    name = db.Column(db.String(200), nullable=False)
    address = db.Column(db.String(300), nullable=True)
    city = db.Column(db.String(100), nullable=False)
    suburb = db.Column(db.String(100), nullable=True, default='')

class RateCard(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    service_type = db.Column(db.String(10), nullable=False)  # B2B or B2C
    from_city = db.Column(db.String(100), nullable=False)
    to_city = db.Column(db.String(100), nullable=False)
    to_suburb = db.Column(db.String(100), nullable=False, default='')
    rate_per_m3 = db.Column(db.Float, nullable=False)

class FurnitureCatalog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    sku = db.Column(db.String(50), unique=True, nullable=False)
    name = db.Column(db.String(200), nullable=False)
    cubic_metres = db.Column(db.Float, nullable=False)
    category = db.Column(db.String(100), nullable=True)

class Quote(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    snapshot = db.Column(db.Text, nullable=False)  # JSON of inputs + result


# ========== HELPERS ==========

def get_settings():
    s = Settings.query.first()
    if not s:
        s = Settings(rural_rate=0.0, assembly_rate=0.0, rubbish_rate=0.0)
        db.session.add(s)
        db.session.commit()
    return s

def serialize_location(loc):
    return {
        'id': loc.id,
        'type': loc.type,
        'name': loc.name,
        'address': loc.address,
        'city': loc.city,
        'suburb': loc.suburb
    }

def serialize_rate_card(rc):
    return {
        'id': rc.id,
        'serviceType': rc.service_type,
        'fromCity': rc.from_city,
        'toCity': rc.to_city,
        'toSuburb': rc.to_suburb,
        'ratePerM3': rc.rate_per_m3
    }

def serialize_catalog(item):
    return {
        'id': item.id,
        'sku': item.sku,
        'name': item.name,
        'cubicMetres': item.cubic_metres,
        'category': item.category
    }

# ========== ADMIN: SETTINGS ==========

@app.route('/api/settings', methods=['GET'])
def get_settings_endpoint():
    s = get_settings()
    return jsonify({
        'ruralRate': s.rural_rate,
        'assemblyRate': s.assembly_rate,
        'rubbishRate': s.rubbish_rate
    })

@app.route('/api/settings', methods=['PUT'])
def update_settings():
    data = request.get_json() or {}
    s = get_settings()
    if 'ruralRate' in data:
        s.rural_rate = float(data['ruralRate'])
    if 'assemblyRate' in data:
        s.assembly_rate = float(data['assemblyRate'])
    if 'rubbishRate' in data:
        s.rubbish_rate = float(data['rubbishRate'])
    db.session.commit()
    return jsonify({
        'ruralRate': s.rural_rate,
        'assemblyRate': s.assembly_rate,
        'rubbishRate': s.rubbish_rate
    })


# ========== ADMIN: LOCATIONS ==========

@app.route('/api/locations', methods=['GET'])
def list_locations():
    locs = Location.query.all()
    return jsonify([serialize_location(l) for l in locs])

@app.route('/api/locations', methods=['POST'])
def create_location():
    data = request.get_json() or {}
    loc = Location(
        type=data.get('type', ''),
        name=data.get('name', ''),
        address=data.get('address', ''),
        city=data.get('city', ''),
        suburb=data.get('suburb', '')
    )
    db.session.add(loc)
    db.session.commit()
    return jsonify(serialize_location(loc)), 201

@app.route('/api/locations/<int:loc_id>', methods=['PUT'])
def update_location(loc_id):
    loc = Location.query.get_or_404(loc_id)
    data = request.get_json() or {}
    loc.type = data.get('type', loc.type)
    loc.name = data.get('name', loc.name)
    loc.address = data.get('address', loc.address)
    loc.city = data.get('city', loc.city)
    loc.suburb = data.get('suburb', loc.suburb)
    db.session.commit()
    return jsonify(serialize_location(loc))

@app.route('/api/locations/<int:loc_id>', methods=['DELETE'])
def delete_location(loc_id):
    loc = Location.query.get_or_404(loc_id)
    db.session.delete(loc)
    db.session.commit()
    return jsonify({'deleted': True})


# ========== ADMIN: RATE CARDS ==========

@app.route('/api/ratecards', methods=['GET'])
def list_ratecards():
    cards = RateCard.query.all()
    return jsonify([serialize_rate_card(c) for c in cards])

@app.route('/api/ratecards', methods=['POST'])
def create_ratecard():
    data = request.get_json() or {}
    rc = RateCard(
        service_type=data.get('serviceType', ''),
        from_city=data.get('fromCity', ''),
        to_city=data.get('toCity', ''),
        to_suburb=data.get('toSuburb', ''),
        rate_per_m3=float(data.get('ratePerM3', 0))
    )
    db.session.add(rc)
    db.session.commit()
    return jsonify(serialize_rate_card(rc)), 201

@app.route('/api/ratecards/<int:rc_id>', methods=['PUT'])
def update_ratecard(rc_id):
    rc = RateCard.query.get_or_404(rc_id)
    data = request.get_json() or {}
    rc.service_type = data.get('serviceType', rc.service_type)
    rc.from_city = data.get('fromCity', rc.from_city)
    rc.to_city = data.get('toCity', rc.to_city)
    rc.to_suburb = data.get('toSuburb', rc.to_suburb)
    rc.rate_per_m3 = float(data.get('ratePerM3', rc.rate_per_m3))
    db.session.commit()
    return jsonify(serialize_rate_card(rc))

@app.route('/api/ratecards/<int:rc_id>', methods=['DELETE'])
def delete_ratecard(rc_id):
    rc = RateCard.query.get_or_404(rc_id)
    db.session.delete(rc)
    db.session.commit()
    return jsonify({'deleted': True})


# ========== ADMIN: FURNITURE CATALOG ==========

@app.route('/api/catalog', methods=['GET'])
def list_catalog():
    items = FurnitureCatalog.query.all()
    return jsonify([serialize_catalog(i) for i in items])

@app.route('/api/catalog', methods=['POST'])
def create_catalog():
    data = request.get_json() or {}
    item = FurnitureCatalog(
        sku=data.get('sku', ''),
        name=data.get('name', ''),
        cubic_metres=float(data.get('cubicMetres', 0)),
        category=data.get('category', '')
    )
    db.session.add(item)
    db.session.commit()
    return jsonify(serialize_catalog(item)), 201

@app.route('/api/catalog/<int:item_id>', methods=['PUT'])
def update_catalog(item_id):
    item = FurnitureCatalog.query.get_or_404(item_id)
    data = request.get_json() or {}
    item.sku = data.get('sku', item.sku)
    item.name = data.get('name', item.name)
    item.cubic_metres = float(data.get('cubicMetres', item.cubic_metres))
    item.category = data.get('category', item.category)
    db.session.commit()
    return jsonify(serialize_catalog(item))

@app.route('/api/catalog/<int:item_id>', methods=['DELETE'])
def delete_catalog(item_id):
    item = FurnitureCatalog.query.get_or_404(item_id)
    db.session.delete(item)
    db.session.commit()
    return jsonify({'deleted': True})


# ========== ADMIN: RESET ==========

@app.route('/api/reset', methods=['POST'])
def reset_data():
    Location.query.delete()
    RateCard.query.delete()
    FurnitureCatalog.query.delete()
    Quote.query.delete()
    s = get_settings()
    s.rural_rate = 0.0
    s.assembly_rate = 0.0
    s.rubbish_rate = 0.0
    db.session.commit()
    return jsonify({'reset': True})


# ========== QUOTES ==========

@app.route('/api/quotes', methods=['POST'])
def calculate_quote():
    data = request.get_json() or {}

    delivery_type = data.get('deliveryType')
    origin_id = data.get('originId')
    destination = data.get('destination', {})
    items = data.get('items', [])
    services = data.get('services', {})

    # Validation
    errors = []
    if not delivery_type:
        errors.append('deliveryType is required')
    if not origin_id:
        errors.append('originId is required')
    if not items:
        errors.append('at least one item is required')
    if not destination:
        errors.append('destination is required')

    origin = Location.query.get(origin_id) if origin_id else None
    if origin_id and not origin:
        errors.append('origin not found')

    if errors:
        return jsonify({'errors': errors}), 400

    # No locations case
    if Location.query.count() == 0:
        return jsonify({'message': 'No locations configured'}), 400

    # Build destination info
    if delivery_type == 'B2B':
        dest_id = destination.get('locationId')
        dest_loc = Location.query.get(dest_id) if dest_id else None
        if not dest_loc:
            return jsonify({'errors': ['destination location not found']}), 400
        dest_city = dest_loc.city
        dest_suburb = dest_loc.suburb or ''
    else:
        dest_city = destination.get('city', '')
        dest_suburb = destination.get('suburb', '')

    # Compute total cubic metres
    total_m3 = 0.0
    item_details = []
    for it in items:
        qty = int(it.get('quantity', 1))
        if qty < 1 or qty > 10:
            return jsonify({'errors': ['quantity must be 1-10']}), 400
        m3 = None
        if 'catalogId' in it:
            cat = FurnitureCatalog.query.get(it['catalogId'])
            if not cat:
                return jsonify({'errors': ['catalog item not found']}), 400
            m3 = it.get('cubicMetresOverride')
            if m3 is None:
                m3 = cat.cubic_metres
            else:
                m3 = float(m3)
            item_details.append({
                'sku': cat.sku,
                'name': cat.name,
                'cubicMetres': m3,
                'quantity': qty,
                'category': cat.category
            })
        else:
            m3 = float(it.get('cubicMetres', 0))
            item_details.append({
                'sku': None,
                'name': it.get('name', 'Custom'),
                'cubicMetres': m3,
                'quantity': qty,
                'category': None
            })
        total_m3 += m3 * qty

    volume_charged = max(1.0, total_m3)

    # Services
    assembly_intervals = int(services.get('assembly', 0))
    rubbish_qty = int(services.get('rubbish', 0))
    rural_km = 0.0
    if delivery_type == 'B2C':
        rural_km = float(services.get('ruralKm', 0))
        if rural_km < 0:
            return jsonify({'errors': ['ruralKm must be >= 0']}), 400
    else:
        if services.get('ruralKm') is not None:
            return jsonify({'errors': ['ruralKm is not accepted for B2B']}), 400

    # Rate matching
    rate_cards = RateCard.query.filter_by(
        service_type=delivery_type,
        from_city=origin.city
    ).all()

    if not rate_cards:
        result = {
            'status': 'Unavailable',
            'message': 'No rate card for selected route and delivery type.',
            'deliveryType': delivery_type,
            'origin': serialize_location(origin),
            'destination': {
                'city': dest_city,
                'suburb': dest_suburb
            },
            'items': item_details,
            'totalCubicMetres': round(total_m3, 2),
            'volumeCharged': round(volume_charged, 2),
            'services': {
                'assemblyIntervals': assembly_intervals,
                'rubbishQuantity': rubbish_qty,
                'ruralKm': rural_km
            },
            'costs': None
        }
        return jsonify(result)

    exact_matches = [
        rc for rc in rate_cards
        if rc.to_city == dest_city and rc.to_suburb == dest_suburb
    ]
    city_matches = [
        rc for rc in rate_cards
        if rc.to_city == dest_city and rc.to_suburb != dest_suburb
    ]

    matched_rate = None
    match_tier = None
    suburb_count = 0

    if exact_matches:
        matched_rate = min(rc.rate_per_m3 for rc in exact_matches)
        match_tier = 'Exact Match'
    elif city_matches:
        matched_rate = max(rc.rate_per_m3 for rc in city_matches)
        match_tier = 'City Match'
        suburb_count = len(set(rc.to_suburb for rc in city_matches if rc.to_suburb))
    else:
        result = {
            'status': 'Unavailable',
            'message': 'No rate card for selected route and delivery type.',
            'deliveryType': delivery_type,
            'origin': serialize_location(origin),
            'destination': {
                'city': dest_city,
                'suburb': dest_suburb
            },
            'items': item_details,
            'totalCubicMetres': round(total_m3, 2),
            'volumeCharged': round(volume_charged, 2),
            'services': {
                'assemblyIntervals': assembly_intervals,
                'rubbishQuantity': rubbish_qty,
                'ruralKm': rural_km
            },
            'costs': None
        }
        return jsonify(result)

    s = get_settings()
    base_delivery = matched_rate * volume_charged
    assembly_cost = s.assembly_rate * assembly_intervals
    rubbish_cost = s.rubbish_rate * rubbish_qty
    rural_cost = s.rural_rate * rural_km
    total = base_delivery + assembly_cost + rubbish_cost + rural_cost

    volume_display = str(round(total_m3, 2)) + ' m³'
    if total_m3 < 1.00:
        volume_display = '%.2f m³ (charged as 1.00 m)' % total_m3

    result = {
        'status': 'Available',
        'deliveryType': delivery_type,
        'origin': serialize_location(origin),
        'destination': {
            'city': dest_city,
            'suburb': dest_suburb
        },
        'items': item_details,
        'totalCubicMetres': round(total_m3, 2),
        'volumeCharged': round(volume_charged, 2),
        'volumeDisplay': volume_display,
        'services': {
            'assemblyIntervals': assembly_intervals,
            'rubbishQuantity': rubbish_qty,
            'ruralKm': rural_km
        },
        'matchTier': match_tier,
        'matchedRatePerM3': matched_rate,
        'suburbCount': suburb_count,
        'costs': {
            'baseDelivery': round(base_delivery, 2),
            'assembly': round(assembly_cost, 2),
            'rubbish': round(rubbish_cost, 2),
            'rural': round(rural_cost, 2),
            'total': round(total, 2)
        }
    }
    return jsonify(result)


@app.route('/api/quotes', methods=['PUT'])
def save_quote():
    data = request.get_json() or {}
    snapshot = json.dumps(data)
    quote = Quote(snapshot=snapshot)
    db.session.add(quote)
    db.session.commit()
    return jsonify({'id': quote.id, 'timestamp': quote.timestamp.isoformat()}), 201

@app.route('/api/quotes', methods=['GET'])
def list_quotes():
    quotes = Quote.query.order_by(Quote.timestamp.desc()).all()
    result = []
    for q in quotes:
        snap = json.loads(q.snapshot)
        delivery_type = snap.get('deliveryType', '')
        origin = snap.get('origin', {})
        origin_city = origin.get('city', '') if isinstance(origin, dict) else ''
        dest = snap.get('destination', {})
        dest_city = dest.get('city', '') if isinstance(dest, dict) else ''
        dest_suburb = dest.get('suburb', '') if isinstance(dest, dict) else ''
        destination_str = dest_city
        if dest_suburb:
            destination_str += ' (%s)' % dest_suburb
        status = snap.get('status', '')
        costs = snap.get('costs')
        total = 'Unavailable'
        if costs and isinstance(costs, dict):
            total = str(round(costs.get('total', 0), 2))
        match_tier = snap.get('matchTier', '')
        result.append({
            'id': q.id,
            'timestamp': q.timestamp.isoformat(),
            'deliveryType': delivery_type,
            'originCity': origin_city,
            'destination': destination_str,
            'matchTier': match_tier,
            'total': total
        })
    return jsonify(result)

@app.route('/api/quotes/<int:quote_id>', methods=['GET'])
def get_quote(quote_id):
    q = Quote.query.get_or_404(quote_id)
    snap = json.loads(q.snapshot)
    snap['id'] = q.id
    snap['timestamp'] = q.timestamp.isoformat()
    return jsonify(snap)

@app.route('/api/quotes/<int:quote_id>', methods=['DELETE'])
def delete_quote(quote_id):
    q = Quote.query.get_or_404(quote_id)
    db.session.delete(q)
    db.session.commit()
    return jsonify({'deleted': True})


# ========== INIT ==========

with app.app_context():
    db.create_all()

if __name__ == '__main__':
    app.run(debug=True, port=5000)
