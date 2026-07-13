import re
import math
from typing import List, Optional, Dict, Any
from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel
import os

app = FastAPI()

# In-memory preferences storage
preferences: Dict[str, List[str]] = {
    "cuisine_types": [],
    "dietary_options": [],
    "facilities": [],
    "keywords": []
}

# Default location
DEFAULT_LAT = 40.4406
DEFAULT_LNG = -79.9959

venues = []

# ---------- Data Parsing ----------

def parse_markdown_data(filepath: str) -> List[Dict[str, Any]]:
    with open(filepath, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    parsed = []
    current_venue = None
    current_category = None
    current_key = None
    in_reviews = False
    
    for line in lines:
        stripped = line.strip()
        
        # Category heading: ### X. Category Name
        if stripped.startswith('### ') and not stripped.startswith('#### '):
            match = re.match(r'###\s+\d+\.\s+(.*)', stripped)
            if match:
                current_category = match.group(1).strip()
            continue
        
        # Venue heading: #### Venue Name
        if stripped.startswith('#### '):
            if current_venue:
                finalize_venue(current_venue)
                parsed.append(current_venue)
            current_venue = {
                "name": stripped[5:].strip(),
                "category": current_category or '',
                "Reviews": []
            }
            current_key = None
            in_reviews = False
            continue
        
        if current_venue is not None:
            # Attribute line: - **Key:** Value
            attr_match = re.match(r'-\s+\*\*(.+?):\*\*\s*(.*)', stripped)
            if attr_match:
                key = attr_match.group(1).strip()
                value = attr_match.group(2).strip()
                current_key = key
                in_reviews = (key == 'Reviews')
                if key == 'Reviews':
                    if value:
                        rev = value.strip('"').strip()
                        if rev:
                            current_venue.setdefault('Reviews', []).append(rev)
                else:
                    current_venue[key] = value
            elif stripped.startswith('- "') and in_reviews:
                rev = stripped[3:].strip().strip('"').strip()
                if rev:
                    current_venue.setdefault('Reviews', []).append(rev)
            elif stripped.startswith('- ') and not in_reviews:
                # Continuation lines for list-like values (ignore, as main values are on one line)
                pass
    
    if current_venue:
        finalize_venue(current_venue)
        parsed.append(current_venue)
    
    return parsed

def finalize_venue(venue: Dict[str, Any]):
    # Keywords
    if 'Keywords' in venue:
        tags = re.findall(r'#([\w-]+)', venue['Keywords'])
        venue['Keywords'] = [t.lower() for t in tags]
    else:
        venue['Keywords'] = []
    
    # Facilities
    if 'Facilities' in venue:
        venue['Facilities'] = [f.strip() for f in venue['Facilities'].split(',') if f.strip()]
    else:
        venue['Facilities'] = []
    
    # Dietary Options
    if 'Dietary Options' in venue:
        venue['Dietary Options'] = [d.strip() for d in venue['Dietary Options'].split(',') if d.strip()]
    else:
        venue['Dietary Options'] = []
    
    # Coordinates
    if 'Coordinates' in venue:
        parts = venue['Coordinates'].split(',')
        if len(parts) == 2:
            try:
                venue['lat'] = float(parts[0].strip())
                venue['lng'] = float(parts[1].strip())
            except ValueError:
                venue['lat'] = DEFAULT_LAT
                venue['lng'] = DEFAULT_LNG
        else:
            venue['lat'] = DEFAULT_LAT
            venue['lng'] = DEFAULT_LNG
    else:
        venue['lat'] = DEFAULT_LAT
        venue['lng'] = DEFAULT_LNG
    
    # Rating
    venue['rating'] = float(venue.get('Rating', 0))
    venue['review_count'] = int(venue.get('Review Count', 0))
    venue['price_range'] = venue.get('Price Range', '')
    venue['status'] = 'Open' if venue.get('Status', '').strip() == 'Open' else 'Closed'
    venue['phone'] = venue.get('Phone', '')
    venue['address'] = venue.get('Address', '')
    venue['cuisine_type'] = venue.get('Cuisine Type', '')

# Load venues
DATA_FILE = os.path.join(os.path.dirname(__file__), 'assets', 'data.md')
venues = parse_markdown_data(DATA_FILE)
for idx, v in enumerate(venues):
    v['id'] = idx

# ---------- Helpers ----------

def calculate_distance(lat1, lng1, lat2, lng2):
    dlat = lat1 - lat2
    dlng = lng1 - lng2
    return math.sqrt((dlat * 69) ** 2 + (dlng * 54.6) ** 2)

def format_distance(miles):
    if miles < 0.6:
        feet = miles * 5280
        rounded_feet = round(feet / 50) * 50
        return f"{rounded_feet} ft"
    else:
        return f"{miles:.1f} mi"

def travel_time_minutes(miles, mph):
    if mph == 0:
        return 0
    return math.ceil((miles / mph) * 60)

def normalize(s):
    return s.replace('-', ' ').strip().lower()

def venue_matches_keyword_preference(venue, pref):
    pref_norm = normalize(pref)
    keywords_norm = [normalize(k) for k in venue.get('Keywords', [])]
    facilities_norm = [normalize(f) for f in venue.get('Facilities', [])]
    price = normalize(venue.get('price_range', ''))
    
    if pref_norm == "highly rated":
        return venue.get('rating', 0) >= 4.5
    if pref_norm == "good value":
        return normalize('good value') in keywords_norm or price in [normalize('$'), normalize('$$')]
    if pref_norm == "great atmosphere":
        atm_kw = {normalize(k) for k in ['lively', 'cozy', 'beautiful', 'vibrant', 'welcoming', 'elegant', 'sophisticated', 'fun']}
        return any(k in atm_kw for k in keywords_norm)
    if pref_norm == "romantic":
        return normalize('romantic') in keywords_norm
    if pref_norm == "group friendly":
        return normalize('spacious seating') in facilities_norm or normalize('family gatherings') in keywords_norm
    if pref_norm == "full bar":
        return normalize('full bar') in facilities_norm
    if pref_norm == "scenic view":
        return normalize('scenic view') in facilities_norm
    if pref_norm == "quiet":
        return normalize('quiet') in keywords_norm
    if pref_norm == "clean":
        return normalize('clean') in keywords_norm
    if pref_norm == "upscale":
        return price in [normalize('$$$'), normalize('$$$$')] or normalize('upscale') in keywords_norm or normalize('elegant') in keywords_norm
    if pref_norm == "casual":
        return price in [normalize('$'), normalize('$$')] or normalize('casual') in keywords_norm
    if pref_norm == "family gathering":
        return normalize('family gatherings') in keywords_norm
    if pref_norm in [normalize("child-friendly"), normalize("kids welcome")]:
        child_facs = {normalize(f) for f in ['play area', 'high chairs', 'kids utensils', 'changing station']}
        if any(f in child_facs for f in facilities_norm):
            return True
        return normalize('family friendly') in keywords_norm
    if pref_norm == "entertainment":
        return normalize('entertainment') in facilities_norm or normalize('entertaining') in keywords_norm
    if pref_norm == "activities":
        act_kw = {normalize(k) for k in ['activities', 'interactive', 'hands-on']}
        return normalize('play area') in facilities_norm or any(k in act_kw for k in keywords_norm)
    return False

def venue_matches_preferences(venue, prefs_dict):
    if prefs_dict.get('cuisine_types'):
        ven_cuisine = normalize(venue.get('cuisine_type', ''))
        selected = [normalize(c) for c in prefs_dict['cuisine_types']]
        if ven_cuisine not in selected:
            return False
    if prefs_dict.get('dietary_options'):
        ven_diets = [normalize(d) for d in venue.get('Dietary Options', [])]
        selected = [normalize(d) for d in prefs_dict['dietary_options']]
        if not any(d in ven_diets for d in selected):
            return False
    if prefs_dict.get('facilities'):
        ven_facs = [normalize(f) for f in venue.get('Facilities', [])]
        selected = [normalize(f) for f in prefs_dict['facilities']]
        if not any(f in ven_facs for f in selected):
            return False
    if prefs_dict.get('keywords'):
        if not any(venue_matches_keyword_preference(venue, kw) for kw in prefs_dict['keywords']):
            return False
    return True

# ---------- API Models ----------

class PreferenceUpdate(BaseModel):
    cuisine_types: Optional[List[str]] = None
    dietary_options: Optional[List[str]] = None
    facilities: Optional[List[str]] = None
    keywords: Optional[List[str]] = None

# ---------- Endpoints ----------

@app.get("/search")
def search_venues(
    category: Optional[str] = Query(None),
    lat: Optional[float] = Query(None),
    lng: Optional[float] = Query(None)
):
    user_lat = lat if lat is not None else DEFAULT_LAT
    user_lng = lng if lng is not None else DEFAULT_LNG
    using_default = (lat is None and lng is None)
    
    results = []
    for v in venues:
        if category and v.get('category', '') != category:
            continue
        if not venue_matches_preferences(v, preferences):
            continue
        results.append(v)
    
    for v in results:
        dist = calculate_distance(user_lat, user_lng, v['lat'], v['lng'])
        v['distance_miles'] = dist
        v['distance_display'] = format_distance(dist)
        v['driving_time'] = travel_time_minutes(dist, 22)
        v['walking_time'] = travel_time_minutes(dist, 3)
    
    results.sort(key=lambda x: (x['distance_miles'], x['name'].lower()))
    
    resp = []
    for v in results:
        resp.append({
            "name": v['name'],
            "category": v['category'],
            "address": v['address'],
            "distance": v['distance_display'],
            "rating": v['rating'],
            "review_count": v['review_count'],
            "price_range": v['price_range'],
            "driving_time": v['driving_time'],
            "walking_time": v['walking_time'],
            "phone": v['phone'],
            "status": v['status']
        })
    return {"default_location_used": using_default, "results": resp}

@app.get("/venues/{venue_id}")
def venue_detail(venue_id: int):
    if venue_id < 0 or venue_id >= len(venues):
        raise HTTPException(status_code=404, detail="Venue not found")
    v = venues[venue_id]
    keywords_badges = [f"#{kw}" for kw in v.get('Keywords', [])[:8]]
    return {
        "id": v['id'],
        "name": v['name'],
        "category": v['category'],
        "address": v['address'],
        "coordinates": {"lat": v['lat'], "lng": v['lng']},
        "phone": v['phone'],
        "hours": v.get('Hours', ''),
        "status": v['status'],
        "price_range": v['price_range'],
        "rating": v['rating'],
        "review_count": v['review_count'],
        "cuisine_type": v.get('cuisine_type', ''),
        "facilities": v.get('Facilities', []),
        "dietary_options": v.get('Dietary Options', []),
        "reviews": v.get('Reviews', []),
        "keywords": keywords_badges,
    }

@app.get("/preferences")
def get_preferences():
    return preferences

@app.put("/preferences")
def update_preferences(update: PreferenceUpdate):
    if update.cuisine_types is not None:
        preferences["cuisine_types"] = update.cuisine_types
    if update.dietary_options is not None:
        preferences["dietary_options"] = update.dietary_options
    if update.facilities is not None:
        preferences["facilities"] = update.facilities
    if update.keywords is not None:
        preferences["keywords"] = update.keywords
    return {"message": "Preferences updated", "preferences": preferences}

@app.delete("/preferences")
def clear_preferences():
    for key in preferences:
        preferences[key] = []
    return {"message": "Preferences cleared", "preferences": preferences}
