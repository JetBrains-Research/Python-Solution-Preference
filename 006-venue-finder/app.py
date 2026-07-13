import re
import math
import json
import os
from flask import Flask, request, jsonify

app = Flask(__name__)

DEFAULT_LAT = 40.4406
DEFAULT_LNG = -79.9959
DATA_FILE = "assets/data.md"
PREFS_FILE = "preferences.json"

# --- Data Parsing ---

def parse_data_md():
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        content = f.read()
    venues = []
    lines = content.splitlines()
    i = 0
    current_category_group = None
    current_subcategory = None
    
    while i < len(lines):
        line = lines[i].rstrip()
        stripped = line.strip()
        if stripped.startswith("## ") and not stripped.startswith("###"):
            if "Data Summary" not in stripped:
                current_category_group = stripped[3:].strip()
                current_subcategory = None
        elif stripped.startswith("### "):
            current_subcategory = stripped[4:].strip()
            m = re.match(r'^\d+\.\s+(.*)', current_subcategory)
            if m:
                current_subcategory = m.group(1).strip()
        elif stripped.startswith("#### "):
            name = stripped[5:].strip()
            venue = {"name": name}
            i += 1
            while i < len(lines):
                l = lines[i].rstrip()
                s = l.strip()
                if s.startswith("#### "):
                    i -= 1
                    break
                if s.startswith("## ") or s.startswith("### "):
                    break
                if s.startswith('- **'):
                    close = s.find(':** ')
                    if close != -1:
                        key = s[4:close].strip().lower().replace(" ", "_")
                        val = s[close+4:].strip()
                        venue[key] = val
                elif s.startswith('- "') and s.endswith('"'):
                    if "reviews" not in venue:
                        venue["reviews"] = []
                    venue["reviews"].append(s[2:-1].strip())
                i += 1
            venue["category"] = current_subcategory
            venue["category_group"] = current_category_group
            venues.append(postprocess_venue(venue))
            continue
        i += 1
    return venues

def postprocess_venue(v):
    status = v.get("status", "Closed")
    v["status"] = "Open" if status.lower().strip() == "open" else "Closed"
    
    coords = v.get("coordinates", "")
    if "," in coords:
        parts = coords.split(",")
        try:
            v["lat"] = float(parts[0].strip())
            v["lng"] = float(parts[1].strip())
        except:
            v["lat"] = 0.0
            v["lng"] = 0.0
    else:
        v["lat"] = 0.0
        v["lng"] = 0.0

    rating = v.get("rating", "")
    try:
        v["rating"] = float(rating)
    except:
        v["rating"] = 0.0

    rc = v.get("review_count", "")
    try:
        v["review_count"] = int(rc)
    except:
        v["review_count"] = 0

    for field in ["cuisine_type", "facilities", "dietary_options"]:
        val = v.get(field, "")
        if val:
            v[field] = [x.strip() for x in val.split(",") if x.strip()]
        else:
            v[field] = []

    kw = v.get("keywords", "")
    v["keywords_raw"] = kw
    v["keywords"] = []
    if kw:
        for word in re.findall(r"#([a-zA-Z0-9\-]+)", kw):
            v["keywords"].append(word.lower())

    return v

venues = parse_data_md()

for idx, venue in enumerate(venues):
    venue["id"] = idx + 1

def get_venue_by_id(vid):
    for v in venues:
        if v["id"] == vid:
            return v
    return None

# --- Preferences ---

DEFAULT_PREFERENCES = {
    "cuisine_types": [],
    "dietary_options": [],
    "facilities": [],
    "keywords": []
}

def load_preferences():
    if os.path.exists(PREFS_FILE):
        try:
            with open(PREFS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            pass
    return DEFAULT_PREFERENCES.copy()

def save_preferences(prefs):
    with open(PREFS_FILE, "w", encoding="utf-8") as f:
        json.dump(prefs, f, indent=2)

# --- Distance & Time ---

def calc_distance(lat1, lng1, lat2, lng2):
    dlat = lat2 - lat1
    dlng = lng2 - lng1
    return math.sqrt((dlat * 69) ** 2 + (dlng * 54.6) ** 2)

def format_distance(miles):
    if miles < 0.6:
        feet = round(miles * 5280 / 50) * 50
        return f"{feet} ft"
    else:
        return f"{miles:.1f} mi"

def travel_time(miles, speed_mph):
    if speed_mph <= 0:
        return 0
    minutes = miles / speed_mph * 60
    return math.ceil(minutes)

# --- Keyword Matching ---

def matches_keyword_selection(venue, keyword):
    k = keyword.lower().strip().replace(" ", "-")
    kw_set = set(venue.get("keywords", []))
    facilities = venue.get("facilities", [])
    facilities_set = set([f.lower().replace(" ", "-") for f in facilities])
    price = venue.get("price_range", "")
    if not price:
        price = ""

    matchers = {
        "highly-rated": venue.get("rating", 0) >= 4.5,
        "good-value": "good-value" in kw_set or price in ("$", "$$"),
        "great-atmosphere": any(w in kw_set for w in {"lively", "cozy", "beautiful", "vibrant", "welcoming", "elegant", "sophisticated", "fun"}),
        "romantic": "romantic" in kw_set,
        "group-friendly": "spacious-seating" in facilities_set or "family-gatherings" in kw_set,
        "full-bar": "full-bar" in facilities_set,
        "scenic-view": "scenic-view" in facilities_set,
        "quiet": "quiet" in kw_set,
        "clean": "clean" in kw_set,
        "upscale": price in ("$$$", "$$$$") or "upscale" in kw_set or "elegant" in kw_set,
        "casual": price in ("$", "$$") or "casual" in kw_set,
        "family-gathering": "family-gatherings" in kw_set,
        "child-friendly": "family-friendly" in kw_set or any(f in facilities_set for f in {"play-area", "high-chairs", "kids-utensils", "changing-station"}),
        "kids-welcome": "family-friendly" in kw_set or any(f in facilities_set for f in {"play-area", "high-chairs", "kids-utensils", "changing-station"}),
        "entertainment": "entertainment" in facilities_set or "entertaining" in kw_set,
        "activities": "play-area" in facilities_set or any(w in kw_set for w in {"activities", "interactive", "hands-on"}),
    }
    return matchers.get(k, False)

# --- Filtering ---

CATEGORY_GROUPS = {
    "Food & Dining": ["General Restaurants", "Western Restaurants", "Cafes", "Kids Cafes"],
    "Places to Visit": ["Playgrounds & Parks", "Museums & Experience Centers", "Festivals & Events", "Indoor Playgrounds"]
}

def filter_venues(category, prefs, user_lat, user_lng, using_default):
    selected_cats = []
    if category == "Food & Dining":
        selected_cats = CATEGORY_GROUPS["Food & Dining"]
    elif category == "Places to Visit":
        selected_cats = CATEGORY_GROUPS["Places to Visit"]
    elif category:
        selected_cats = [category]
    else:
        selected_cats = None
    
    results = []
    for v in venues:
        cat = v.get("category", "").strip()
        if selected_cats is not None and cat not in selected_cats:
            continue
        
        # Cuisine types filter
        cuisine_sel = prefs.get("cuisine_types", [])
        if cuisine_sel:
            venue_cuisines = [c.lower() for c in v.get("cuisine_type", [])]
            if not any(c.lower() in venue_cuisines for c in cuisine_sel):
                continue
        
        # Dietary options filter
        diet_sel = prefs.get("dietary_options", [])
        if diet_sel:
            venue_diets = [d.lower() for d in v.get("dietary_options", [])]
            if not any(d.lower() in venue_diets for d in diet_sel):
                continue
        
        # Facilities filter
        fac_sel = prefs.get("facilities", [])
        if fac_sel:
            venue_facs = [f.lower() for f in v.get("facilities", [])]
            if not any(f.lower() in venue_facs for f in fac_sel):
                continue
        
        # Keywords filter
        kw_sel = prefs.get("keywords", [])
        if kw_sel:
            matched_any = False
            for sel_kw in kw_sel:
                if matches_keyword_selection(v, sel_kw):
                    matched_any = True
                    break
            if not matched_any:
                continue
        
        distance = calc_distance(user_lat, user_lng, v["lat"], v["lng"])
        v_copy = dict(v)
        v_copy["distance_miles"] = distance
        v_copy["distance_display"] = format_distance(distance)
        v_copy["driving_time"] = travel_time(distance, 22)
        v_copy["walking_time"] = travel_time(distance, 3)
        v_copy["using_default_location"] = using_default
        results.append(v_copy)
    
    results.sort(key=lambda x: (x["distance_miles"], x["name"].lower()))
    return results

# --- API Endpoints ---

@app.route("/categories", methods=["GET"])
def get_categories():
    return jsonify({
        "groups": {
            "Food & Dining": ["General Restaurants", "Western Restaurants", "Cafes", "Kids Cafes"],
            "Places to Visit": ["Playgrounds & Parks", "Museums & Experience Centers", "Festivals & Events", "Indoor Playgrounds"]
        }
    })

@app.route("/preferences", methods=["GET"])
def get_preferences():
    return jsonify(load_preferences())

@app.route("/preferences", methods=["POST"])
def set_preferences():
    body = request.get_json(force=True, silent=True) or {}
    prefs = {
        "cuisine_types": body.get("cuisine_types", []),
        "dietary_options": body.get("dietary_options", []),
        "facilities": body.get("facilities", []),
        "keywords": body.get("keywords", [])
    }
    save_preferences(prefs)
    return jsonify(prefs)

@app.route("/preferences", methods=["DELETE"])
def clear_preferences():
    save_preferences(DEFAULT_PREFERENCES.copy())
    return jsonify(DEFAULT_PREFERENCES.copy())

@app.route("/venues/search", methods=["GET"])
def search_venues():
    category = request.args.get("category", "")
    user_lat = request.args.get("lat", type=float)
    user_lng = request.args.get("lng", type=float)
    using_default = False
    
    if user_lat is None or user_lng is None:
        user_lat = DEFAULT_LAT
        user_lng = DEFAULT_LNG
        using_default = True
    
    prefs = load_preferences()
    
    results = filter_venues(category, prefs, user_lat, user_lng, using_default)
    
    output = []
    for r in results:
        output.append({
            "id": r["id"],
            "name": r["name"],
            "category": r["category"],
            "address": r.get("address", ""),
            "distance": r["distance_display"],
            "rating": r.get("rating", 0),
            "review_count": r.get("review_count", 0),
            "price_range": r.get("price_range", ""),
            "driving_time": r["driving_time"],
            "walking_time": r["walking_time"],
            "phone": r.get("phone", ""),
            "status": r["status"],
            "using_default_location": r["using_default_location"]
        })
    
    return jsonify({"venues": output, "using_default_location": using_default})

@app.route("/venues/<int:venue_id>", methods=["GET"])
def get_venue_detail(venue_id):
    v = get_venue_by_id(venue_id)
    if not v:
        return jsonify({"error": "Venue not found"}), 404
    
    user_lat = request.args.get("lat", type=float)
    user_lng = request.args.get("lng", type=float)
    using_default = False
    
    if user_lat is None or user_lng is None:
        user_lat = DEFAULT_LAT
        user_lng = DEFAULT_LNG
        using_default = True
    
    distance = calc_distance(user_lat, user_lng, v["lat"], v["lng"])
    
    badges = []
    for kw in v.get("keywords", []):
        badges.append(f"#{kw.lower()}")
    if len(badges) > 8:
        badges = badges[:8]
    
    result = {
        "id": v["id"],
        "name": v["name"],
        "category": v.get("category", ""),
        "address": v.get("address", ""),
        "phone": v.get("phone", ""),
        "hours": v.get("hours", ""),
        "status": v["status"],
        "price_range": v.get("price_range", ""),
        "rating": v.get("rating", 0),
        "review_count": v.get("review_count", 0),
        "coordinates": {"lat": v["lat"], "lng": v["lng"]},
        "distance": format_distance(distance),
        "distance_miles": distance,
        "driving_time": travel_time(distance, 22),
        "walking_time": travel_time(distance, 3),
        "cuisine_type": v.get("cuisine_type", []),
        "facilities": v.get("facilities", []),
        "dietary_options": v.get("dietary_options", []),
        "keywords_badges": badges,
        "using_default_location": using_default
    }
    
    return jsonify(result)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080, debug=True)

