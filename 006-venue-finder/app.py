import re
import math
import json
from flask import Flask, request, jsonify

app = Flask(__name__)

# ----- Data Loading ---------------------------------------------------------

def parse_markdown(filepath):
    venues = []
    current = None
    with open(filepath, encoding='utf-8') as f:
        for line in f:
            line = line.rstrip()
            # Start of a venue
            m = re.match(r'^####\\s+(.*)$', line)
            if m:
                if current:
                    venues.append(current)
                current = {
                    'name': m.group(1).strip(),
                    'facilities': [],
                    'dietary_options': [],
                    'keywords_raw': [],
                }
                continue
            if not current:
                continue
            # Key‑value lines
            kv = re.match(r'^- \\*\\*([^:]+):\\*\\*\\s*(.*)$', line)
            if kv:
                key = kv.group(1).strip().lower().replace(' ', '_')
                val = kv.group(2).strip()
                if key == 'coordinates':
                    lat, lng = map(str.strip, val.split(','))
                    current['lat'] = float(lat)
                    current['lng'] = float(lng)
                elif key == 'price_range':
                    current['price_range'] = val
                elif key == 'rating':
                    current['rating'] = float(val)
                elif key == 'review_count':
                    current['review_count'] = int(val)
                elif key == 'cuisine_type':
                    current['cuisine_type'] = val
                elif key == 'facilities':
                    current['facilities'] = [x.strip() for x in val.split(',')]
                elif key == 'dietary_options':
                    current['dietary_options'] = [x.strip() for x in val.split(',')]
                elif key == 'keywords':
                    # extract hashtags without #
                    tags = re.findall(r'#([\\w-]+)', val)
                    current['keywords_raw'] = [t.lower() for t in tags]
                else:
                    # store generic fields
                    current[key] = val
    if current:
        venues.append(current)
    return venues

VENUES = parse_markdown('assets/data.md')

# ----- Preference Storage ----------------------------------------------------

PREFERENCES = {
    'cuisine': [],
    'dietary': [],
    'facilities': [],
    'keywords': []   # these are the high‑level keyword preferences like "Highly rated"
}

# ----- Helper Functions -----------------------------------------------------

def distance_miles(lat1, lng1, lat2, lng2):
    dlat = (lat1 - lat2) * 69.0
    dlng = (lng1 - lng2) * 54.6
    return math.sqrt(dlat**2 + dlng**2)

def format_distance(dist):
    if dist < 0.6:
        ft = round(dist * 5280 / 50) * 50
        return f\"{ft} ft\"
    else:
        return f\"{dist:.1f} mi\"

def travel_time(dist, speed_mph):
    minutes = math.ceil(dist / speed_mph * 60)
    return f\"{minutes} min\"

# Keyword matching based on spec
def venue_matches_keyword_pref(venue, pref):
    pref = pref.lower().replace(' ', '-')
    # rating
    if pref == 'highly rated':
        return venue.get('rating', 0) >= 4.5
    # good value
    if pref == 'good value':
        return ('good-value' in venue['keywords_raw'] or
                venue.get('price_range', '').strip() in ('$','$ $'))
    # great atmosphere
    if pref == 'great atmosphere':
        keywords = {'lively','cozy','beautiful','vibrant','welcoming','elegant','sophisticated','fun'}
        return any(k in venue['keywords_raw'] for k in keywords)
    if pref == 'romantic':
        return 'romantic' in venue['keywords_raw']
    if pref == 'group friendly':
        return ('spacious seating' in [f.lower() for f in venue['facilities']] or
                'family-gatherings' in venue['keywords_raw'])
    if pref == 'full bar':
        return 'full bar' in [f.lower() for f in venue['facilities']]
    if pref == 'scenic view':
        return 'scenic view' in [f.lower() for f in venue['facilities']]
    if pref == 'quiet':
        return 'quiet' in venue['keywords_raw']
    if pref == 'clean':
        return 'clean' in venue['keywords_raw']
    if pref == 'upscale':
        return (venue.get('price_range','').strip() in ('$$$','$$$$') or
                'upscale' in venue['keywords_raw'] or
                'elegant' in venue['keywords_raw'])
    if pref == 'casual':
        return (venue.get('price_range','').strip() in ('$','$ $') or
                'casual' in venue['keywords_raw'])
    if pref == 'family gathering':
        return 'family-gatherings' in venue['keywords_raw']
    if pref in ('child-friendly','kids welcome'):
        return ('family-friendly' in venue['keywords_raw'] or
                any(f.lower() in ('play area','high chairs','kids utensils','changing station')
                    for f in venue['facilities']))
    if pref == 'entertainment':
        return ('entertainment' in [f.lower() for f in venue['facilities']] or
                'entertaining' in venue['keywords_raw'])
    if pref == 'activities':
        return ('play area' in [f.lower() for f in venue['facilities']] or
                any(k in venue['keywords_raw'] for k in ('activities','interactive','hands-on')))
    return False

def venue_matches_preferences(venue):
    # Cuisine
    if PREFERENCES['cuisine']:
        if venue.get('cuisine_type','').lower() not in [c.lower() for c in PREFERENCES['cuisine']]:
            return False
    # Dietary
    if PREFERENCES['dietary']:
        if not any(opt.lower() in [d.lower() for d in venue.get('dietary_options',[])]
                   for opt in PREFERENCES['dietary']):
            return False
    # Facilities
    if PREFERENCES['facilities']:
        if not any(fac.lower() in [f.lower() for f in venue.get('facilities',[])]
                   for fac in PREFERENCES['facilities']):
            return False
    # Keyword preferences
    if PREFERENCES['keywords']:
        if not any(venue_matches_keyword_pref(venue, kw) for kw in PREFERENCES['keywords']):
            return False
    return True

# ----- API Endpoints --------------------------------------------------------

@app.route('/preferences', methods=['GET'])
def get_preferences():
    return jsonify(PREFERENCES)

@app.route('/preferences', methods=['POST'])
def set_preferences():
    data = request.get_json()
    for key in PREFERENCES.keys():
        if key in data:
            PREFERENCES[key] = data[key]
    return jsonify({'status':'ok', 'preferences': PREFERENCES})

@app.route('/preferences/clear', methods=['POST'])
def clear_preferences():
    for key in PREFERENCES:
        PREFERENCES[key] = []
    return jsonify({'status':'cleared'})

@app.route('/search', methods=['GET'])
def search():
    category = request.args.get('category')
    if not category:
        return jsonify({'error':'category required'}), 400
    lat = request.args.get('lat')
    lng = request.args.get('lng')
    default_used = False
    if lat is None or lng is None:
        lat, lng = 40.4406, -79.9959
        default_used = True
    else:
        lat, lng = float(lat), float(lng)

    results = []
    for v in VENUES:
        if v.get('category','').lower() != category.lower():
            continue
        if not venue_matches_preferences(v):
            continue
        dist = distance_miles(lat, lng, v['lat'], v['lng'])
        result = {
            'name': v['name'],
            'category': v['category'],
            'address': v.get('address',''),
            'distance': format_distance(dist),
            'rating': v.get('rating',0),
            'review_count': v.get('review_count',0),
            'price_range': v.get('price_range',''),
            'driving_time': travel_time(dist, 22),
            'walking_time': travel_time(dist, 3),
            'phone': v.get('phone',''),
            'status': v.get('status','Closed')
        }
        results.append((dist, result))

    # sort by distance then name
    results.sort(key=lambda x: (x[0], x[1]['name'].lower()))
    response = [r[1] for r in results]
    if default_used:
        return jsonify({'using_default_location':True, 'results':response})
    else:
        return jsonify({'results':response})

@app.route('/venue/<string:name>', methods=['GET'])
def venue_detail(name):
    # simple name lookup (case‑insensitive)
    venue = next((v for v in VENUES if v['name'].lower() == name.lower()), None)
    if not venue:
        return jsonify({'error':'venue not found'}), 404
    # prepare hashtag badges (max 8)
    hashtags = [f\"#{kw}\" for kw in venue.get('keywords_raw', [])][:8]
    detail = venue.copy()
    if hashtags:
        detail['hashtags'] = hashtags
    return jsonify(detail)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
