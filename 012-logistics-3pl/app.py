import re
import json
from datetime import datetime
from flask import Flask, request, jsonify, abort, Response

app = Flask(__name__)

# ---------- Utility Validators ----------
PHONE_REGEX = re.compile(r'''
    ^\s*(?:\+1\s*)?                # optional country code
    (?:\(?(\d{3})\)?[-.\s]?|(\d{3})[-.\s]?)   # area code with optional parentheses
    (\d{3})[-.\s]?(\d{4})\s*$      # rest of number
''', re.VERBOSE)

EMAIL_REGEX = re.compile(r'^[^@\\s]+@[^@\\s]+\\.[^@\\s]+$')

def validate_phone(phone):
    return bool(PHONE_REGEX.match(phone))

def validate_email(email):
    return bool(EMAIL_REGEX.match(email))

# ---------- Blog Data ----------
BLOG_POSTS = {
    "ftz-vs-bonded-warehouse": {
        "title": "FTZ vs Bonded Warehouse",
        "body": "Understanding the differences between FTZ and bonded warehouses is essential for importers. FTZs provide..."
    },
    "cross-dock-near-port": {
        "title": "Cross‑Dock Near Port",
        "body": "Cross‑docking near a port reduces dwell time and improves supply chain efficiency. By..."
    },
    "how-to-choose-a-3pl": {
        "title": "How to Choose a 3PL",
        "body": "Selecting the right third‑party logistics provider involves evaluating service breadth, technology, and pricing..."
    }
}
# Helper to create excerpt of first 50 characters (including partial word)
def excerpt(text, length=50):
    if len(text) <= length:
        return text
    return text[:length] + "…"

# ---------- Insights Endpoints ----------
@app.route('/insights', methods=['GET'])
def list_insights():
    # Order by slug (newest to oldest as placeholder)
    ordered = sorted(BLOG_POSTS.items(), key=lambda x: x[0], reverse=True)
    result = []
    for slug, data in ordered:
        result.append({
            "slug": slug,
            "title": data["title"],
            "excerpt": excerpt(data["body"])
        })
    return jsonify(result)

@app.route('/insights/<slug>', methods=['GET'])
def get_insight(slug):
    post = BLOG_POSTS.get(slug)
    if not post:
        abort(404, description="Post not found")
    return jsonify({"title": post["title"], "body": post["body"]})

# ---------- ROI Calculator ----------
def compute_roi(data):
    # Unpack step data with defaults
    step1 = data.get("step1", {})
    step2 = data.get("step2", {})
    step3 = data.get("destinations", [])

    pallets = float(step1["annual_pallets"])
    port_split = float(step1["port_split"])
    pallets_per_container = float(step1.get("pallets_per_container", 20))
    months = float(step1.get("storage_months", 1.5))

    dray_se = float(step2["dray_se"])
    dray_ne = float(step2["dray_ne"])
    storage_se = float(step2["storage_se"])
    storage_ne = float(step2["storage_ne"])
    handling = float(step2["handling"])
    risk = float(step2["risk_buffer"])
    ftz = float(step2["ftz_savings"])

    # Destinations processing
    dest_se = [d for d in step3 if d["region"] == "SE"]
    dest_ne = [d for d in step3 if d["region"] == "NE"]
    dest_total = len(dest_se) + len(dest_ne)
    if dest_total == 0:
        raise ValueError("At least one destination required")
    share = pallets / dest_total

    containers = pallets / pallets_per_container
    frac_east = port_split / 100.0
    frac_gulf = 1 - frac_east
    dest_se_cnt = len(dest_se)
    dest_ne_cnt = len(dest_ne)
    frac_dest_se = dest_se_cnt / dest_total
    frac_dest_ne = dest_ne_cnt / dest_total

    # Scenario A – SE only
    inbound_a = containers * (frac_east * dray_se + frac_gulf * dray_se * 1.3)
    storage_a = pallets * months * storage_se
    handling_a = pallets * handling
    outbound_a = sum(((d["cost"] * (1.5 if d["region"] == "NE" else 1.0)) * share) for d in step3)
    total_a = (inbound_a + storage_a + handling_a + outbound_a) * (1 + risk/100) * (1 - ftz/100)

    # Scenario B – NE only
    inbound_b = containers * (frac_east * dray_ne * 1.3 + frac_gulf * dray_ne)
    storage_b = pallets * months * storage_ne
    handling_b = handling_a
    outbound_b = sum(((d["cost"] * (1.5 if d["region"] == "SE" else 1.0)) * share) for d in step3)
    total_b = (inbound_b + storage_b + handling_b + outbound_b) * (1 + risk/100) * (1 - ftz/100)

    # Scenario C – Hybrid
    inbound_c = containers * (frac_east * dray_se + frac_gulf * dray_ne)
    storage_c = pallets * months * (frac_dest_se * storage_se + frac_dest_ne * storage_ne)
    handling_c = handling_a
    outbound_c = sum((d["cost"] * share) for d in step3)
    total_c = (inbound_c + storage_c + handling_c + outbound_c) * (1 + risk/100) * (1 - ftz/100)

    # ROI calculations
    roi_b = (total_a - total_b) / total_a * 100
    roi_c = (total_a - total_c) / total_a * 100

    return {
        "scenarioA": {"total_cost": total_a, "cost_per_pallet": total_a / pallets},
        "scenarioB": {"total_cost": total_b, "cost_per_pallet": total_b / pallets, "roi_vs_A": roi_b},
        "scenarioC": {"total_cost": total_c, "cost_per_pallet": total_c / pallets, "roi_vs_A": roi_c}
    }

@app.route('/roi-calculator', methods=['POST'])
def roi_calculator():
    try:
        data = request.get_json()
        result = compute_roi(data)
        return jsonify(result)
    except Exception as e:
        abort(400, description=str(e))

# ---------- Contact Form ----------
@app.route('/contact', methods=['POST'])
def contact():
    payload = request.get_json()
    name = payload.get("name", "").strip()
    email = payload.get("email", "").strip()
    phone = payload.get("phone", "").strip()
    inquiry = payload.get("inquiry_type", "")
    message = payload.get("message", "")

    errors = []
    if not name:
        errors.append("Name required")
    if not email or not validate_email(email):
        errors.append("Valid email required")
    if phone and not validate_phone(phone):
        errors.append("Phone format invalid")
    if inquiry not in ["General Inquiry","Service Question","Partnership Opportunity","Media/Press","Other"]:
        errors.append("Invalid inquiry type")
    if len(message) < 10:
        errors.append("Message must be at least 10 characters")
    if errors:
        abort(400, description="; ".join(errors))

    return jsonify({"message": "Message sent successfully! We'll respond within 24 hours."})

# ---------- Quote Request ----------
QUOTES = []  # simple in‑memory storage

@app.route('/quote-request', methods=['POST'])
def quote():
    payload = request.get_json()
    name = payload.get("name", "").strip()
    email = payload.get("email", "").strip()
    phone = payload.get("phone", "").strip()
    company = payload.get("company", "").strip()
    interests = payload.get("service_interests", [])
    industry = payload.get("industry", "")
    volume = payload.get("estimated_volume")
    timeline = payload.get("timeline", "")
    contact_method = payload.get("contact_method", "")
    # Message optional
    errors = []
    if not name:
        errors.append("Name required")
    if not email or not validate_email(email):
        errors.append("Valid email required")
    if contact_method == "Phone" and not validate_phone(phone):
        errors.append("Phone required and must be valid")
    if not company:
        errors.append("Company required")
    if not interests or not isinstance(interests, list):
        errors.append("At least one service interest required")
    if industry not in ["Food & Beverage","Wine & Spirits","Retail/CPG","Agriculture/Floral","Other"]:
        errors.append("Invalid industry")
    if volume is None or float(volume) < 0:
        errors.append("Estimated volume must be >=0")
    if timeline not in ["ASAP (0–30 days)","1–3 months","3–6 months","6+ months"]:
        errors.append("Invalid timeline")
    if contact_method not in ["Email","Phone"]:
        errors.append("Invalid contact method")
    if errors:
        abort(400, description="; ".join(errors))

    quote_entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "name": name,
        "email": email,
        "phone": phone,
        "company": company,
        "service_interests": interests,
        "industry": industry,
        "estimated_volume": volume,
        "timeline": timeline,
        "contact_method": contact_method,
        "message": payload.get("message", "")
    }
    QUOTES.append(quote_entry)
    return jsonify({"message": "Request sent successfully! We'll respond within 4 business hours."})

# ---------- Quotes Admin ----------
ADMIN_PASSWORD = "apex-logistics-3421"

def check_auth(auth_header):
    if not auth_header or not auth_header.startswith("Basic "):
        return False
    import base64
    enc = auth_header.split(" ",1)[1]
    try:
        decoded = base64.b64decode(enc).decode()
        _, pwd = decoded.split(":",1)
        return pwd == ADMIN_PASSWORD
    except Exception:
        return False

@app.route('/admin/quotes', methods=['GET'])
def admin_quotes():
    auth = request.headers.get("Authorization")
    if not check_auth(auth):
        return Response('Unauthorized', 401, {'WWW-Authenticate':'Basic realm="Login Required"'})
    # newest first
    sorted_quotes = sorted(QUOTES, key=lambda q: q["timestamp"], reverse=True)
    return jsonify(sorted_quotes)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
