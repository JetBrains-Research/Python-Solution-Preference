"""HVAC/Plumbing Service Platform MVP - HTTP API."""
from __future__ import annotations

import re
import uuid
import secrets
from datetime import datetime, date, timezone
from functools import wraps
from flask import Flask, request, jsonify, g

app = Flask(__name__)

# ---------- In-memory stores ----------
USERS = {}          # user_id -> user dict
USERS_BY_EMAIL = {} # email -> user_id
TOKENS = {}         # auth_token -> user_id
PROPERTIES = {}     # prop_id -> prop
EQUIPMENT = {}      # eq_id -> eq
BOOKINGS = {}       # booking_id -> booking
TRACKING = {}       # tracking_token -> booking_id
JOBS = {}           # job_id -> job
INVOICES = {}       # invoice_id -> invoice

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
ZIP_RE = re.compile(r"^\d{5}$")

SERVICE_TYPES = {"HVAC", "Plumbing"}
BOOKING_TYPES = {"Residential", "Commercial"}
CATEGORIES = {"Installation", "Repair", "Maintenance", "Emergency"}
URGENCIES = {"Standard", "Urgent", "Emergency"}
TIME_WINDOWS = {"AM", "PM", "Any"}
EQUIPMENT_TYPES = {
    "Furnace", "AC", "Heat Pump", "Boiler", "Water Heater",
    "Thermostat", "Humidifier", "Air Purifier", "Water Softener",
    "Plumbing Fixture", "Other",
}


def err(msg, code=400):
    return jsonify({"error": msg}), code


def today_utc() -> date:
    return datetime.now(timezone.utc).date()


def parse_date(s):
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except Exception:
        return None


def new_id():
    return uuid.uuid4().hex


# ---------- Auth ----------
def auth_required(role=None, optional=False):
    def deco(fn):
        @wraps(fn)
        def wrapper(*a, **kw):
            token = request.headers.get("Authorization", "")
            if token.startswith("Bearer "):
                token = token[7:]
            user_id = TOKENS.get(token)
            user = USERS.get(user_id) if user_id else None
            if not user:
                if optional:
                    g.user = None
                    return fn(*a, **kw)
                return err("Unauthorized", 401)
            if role and user["role"] != role:
                return err("Forbidden", 403)
            g.user = user
            return fn(*a, **kw)
        return wrapper
    return deco


@app.post("/api/auth/signup")
def signup():
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""
    role = data.get("role")
    if not name:
        return err("name required")
    if not EMAIL_RE.match(email):
        return err("invalid email")
    if email in USERS_BY_EMAIL:
        return err("email already registered")
    if len(password) < 6:
        return err("password must be at least 6 chars")
    if role not in ("Client", "Technician"):
        return err("role must be Client or Technician")
    uid = new_id()
    USERS[uid] = {"id": uid, "name": name, "email": email,
                  "password": password, "role": role}
    USERS_BY_EMAIL[email] = uid
    token = secrets.token_hex(24)
    TOKENS[token] = uid
    return jsonify({"user": _public_user(USERS[uid]), "token": token}), 201


@app.post("/api/auth/login")
def login():
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""
    uid = USERS_BY_EMAIL.get(email)
    if not uid or USERS[uid]["password"] != password:
        return err("invalid credentials", 401)
    token = secrets.token_hex(24)
    TOKENS[token] = uid
    return jsonify({"user": _public_user(USERS[uid]), "token": token})


def _public_user(u):
    return {"id": u["id"], "name": u["name"], "email": u["email"], "role": u["role"]}


# ---------- Properties ----------
def _validate_address(d):
    for f in ("street", "city", "state", "zip"):
        if not d.get(f):
            return f"{f} required"
    if not ZIP_RE.match(str(d["zip"])):
        return "zip must be 5 digits"
    return None


@app.post("/api/properties")
@auth_required(role="Client")
def create_property():
    data = request.get_json(silent=True) or {}
    if not data.get("label"):
        return err("label required")
    e = _validate_address(data)
    if e:
        return err(e)
    pid = new_id()
    PROPERTIES[pid] = {
        "id": pid, "client_id": g.user["id"], "label": data["label"],
        "street": data["street"], "city": data["city"],
        "state": data["state"], "zip": str(data["zip"]),
    }
    return jsonify(PROPERTIES[pid]), 201


@app.get("/api/properties")
@auth_required(role="Client")
def list_properties():
    return jsonify([p for p in PROPERTIES.values() if p["client_id"] == g.user["id"]])


@app.get("/api/properties/<pid>")
@auth_required(role="Client")
def get_property(pid):
    p = PROPERTIES.get(pid)
    if not p or p["client_id"] != g.user["id"]:
        return err("not found", 404)
    eq = [e for e in EQUIPMENT.values() if e["property_id"] == pid]
    return jsonify({**p, "equipment": eq})


@app.delete("/api/properties/<pid>")
@auth_required(role="Client")
def delete_property(pid):
    p = PROPERTIES.get(pid)
    if not p or p["client_id"] != g.user["id"]:
        return err("not found", 404)
    # cascade
    to_del = [eid for eid, e in EQUIPMENT.items() if e["property_id"] == pid]
    for eid in to_del:
        del EQUIPMENT[eid]
    del PROPERTIES[pid]
    return jsonify({"deleted": True})


@app.post("/api/properties/<pid>/equipment")
@auth_required(role="Client")
def add_equipment(pid):
    p = PROPERTIES.get(pid)
    if not p or p["client_id"] != g.user["id"]:
        return err("not found", 404)
    data = request.get_json(silent=True) or {}
    if data.get("service_type") not in SERVICE_TYPES:
        return err("invalid service_type")
    if data.get("equipment_type") not in EQUIPMENT_TYPES:
        return err("invalid equipment_type")
    eid = new_id()
    EQUIPMENT[eid] = {
        "id": eid, "property_id": pid,
        "service_type": data["service_type"],
        "equipment_type": data["equipment_type"],
        "manufacturer": data.get("manufacturer"),
        "model": data.get("model"),
        "serial": data.get("serial"),
        "install_date": data.get("install_date"),
        "notes": data.get("notes"),
    }
    return jsonify(EQUIPMENT[eid]), 201


@app.get("/api/properties/<pid>/equipment")
@auth_required(role="Client")
def list_equipment(pid):
    p = PROPERTIES.get(pid)
    if not p or p["client_id"] != g.user["id"]:
        return err("not found", 404)
    return jsonify([e for e in EQUIPMENT.values() if e["property_id"] == pid])


# ---------- Bookings ----------
@app.post("/api/bookings")
@auth_required(optional=True)
def create_booking():
    data = request.get_json(silent=True) or {}
    user = getattr(g, "user", None)

    # Enum validations
    if data.get("service_type") not in SERVICE_TYPES:
        return err("invalid service_type")
    if data.get("booking_type") not in BOOKING_TYPES:
        return err("invalid booking_type")
    if data.get("category") not in CATEGORIES:
        return err("invalid category")
    if data.get("urgency") not in URGENCIES:
        return err("invalid urgency")

    # Signed-in Client: force name/email from account; can't be overridden meaningfully
    if user and user["role"] == "Client":
        name = user["name"]
        email = user["email"]
    else:
        name = (data.get("name") or "").strip()
        email = (data.get("email") or "").strip().lower()
        if not name:
            return err("name required")
        if not EMAIL_RE.match(email):
            return err("invalid email")

    phone = (data.get("phone") or "").strip()
    digits = re.sub(r"\D", "", phone)
    if len(digits) < 10:
        return err("phone must have at least 10 digits")

    # Address: property or explicit
    address = None
    property_id = data.get("property_id")
    if property_id:
        if not user or user["role"] != "Client":
            return err("only clients can use property_id")
        p = PROPERTIES.get(property_id)
        if not p or p["client_id"] != user["id"]:
            return err("property not found")
        address = {"street": p["street"], "city": p["city"],
                   "state": p["state"], "zip": p["zip"]}
    else:
        addr = data.get("address") or {}
        e = _validate_address(addr)
        if e:
            return err(f"address: {e}")
        address = {"street": addr["street"], "city": addr["city"],
                   "state": addr["state"], "zip": str(addr["zip"])}

    # Commercial => company name required
    company_name = data.get("company_name")
    if data["booking_type"] == "Commercial" and not company_name:
        return err("company_name required for Commercial")

    # Optional fields
    preferred_date = None
    if data.get("preferred_date"):
        preferred_date = parse_date(data["preferred_date"])
        if not preferred_date:
            return err("invalid preferred_date")
        if preferred_date < today_utc():
            return err("preferred_date cannot be in the past")

    time_window = data.get("time_window")
    if time_window is not None and time_window not in TIME_WINDOWS:
        return err("invalid time_window")

    bid = new_id()
    token = secrets.token_hex(24) if not user or user["role"] != "Client" else None
    booking = {
        "id": bid,
        "state": "New",
        "service_type": data["service_type"],
        "booking_type": data["booking_type"],
        "category": data["category"],
        "urgency": data["urgency"],
        "name": name, "email": email, "phone": phone,
        "address": address,
        "company_name": company_name if data["booking_type"] == "Commercial" else None,
        "preferred_date": preferred_date.isoformat() if preferred_date else None,
        "time_window": time_window,
        "description": data.get("description"),
        "client_id": user["id"] if user and user["role"] == "Client" else None,
        "tracking_token": token,
        "job_id": None,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    BOOKINGS[bid] = booking
    if token:
        TRACKING[token] = bid

    resp = {
        "id": bid,
        "summary": {
            "service_type": booking["service_type"],
            "category": booking["category"],
            "urgency": booking["urgency"],
            "state": booking["state"],
        },
        "booking": booking,
    }
    if token:
        resp["tracking_token"] = token
    return jsonify(resp), 201


@app.get("/api/bookings")
@auth_required()
def list_bookings():
    u = g.user
    if u["role"] == "Client":
        result = [b for b in BOOKINGS.values()
                  if b["client_id"] == u["id"] and b["state"] == "New"]
    else:  # Technician
        result = [b for b in BOOKINGS.values() if b["state"] == "New"]
    return jsonify(result)


@app.get("/api/bookings/<bid>")
@auth_required(optional=True)
def get_booking(bid):
    b = BOOKINGS.get(bid)
    if not b:
        return err("not found", 404)
    u = getattr(g, "user", None)
    if u:
        if u["role"] == "Client" and b["client_id"] == u["id"]:
            return jsonify(b)
        if u["role"] == "Technician":
            return jsonify(b)
    return err("forbidden", 403)


@app.get("/api/track/<token>")
def track(token):
    bid = TRACKING.get(token)
    if not bid:
        return err("not found", 404)
    b = BOOKINGS[bid]
    resp = {"booking": b}
    if b["job_id"]:
        j = JOBS[b["job_id"]]
        resp["job"] = _job_view(j, include_notes=True)
        invs = [i for i in INVOICES.values()
                if i["job_id"] == j["id"] and i["status"] != "Draft"]
        resp["invoices"] = invs
    return jsonify(resp)


# ---------- Jobs ----------
def _job_view(j, include_notes=True):
    d = dict(j)
    tech = USERS.get(j["technician_id"])
    d["technician_name"] = tech["name"] if tech else None
    return d


@app.post("/api/bookings/<bid>/convert")
@auth_required(role="Technician")
def convert_booking(bid):
    b = BOOKINGS.get(bid)
    if not b:
        return err("not found", 404)
    if b["state"] != "New":
        return err("booking already converted")
    data = request.get_json(silent=True) or {}
    sched = parse_date(data.get("scheduled_date") or "")
    if not sched:
        return err("scheduled_date required (YYYY-MM-DD)")
    if sched < today_utc():
        return err("scheduled_date cannot be in the past")
    tw = data.get("time_window")
    if not tw:
        return err("time_window required")
    if tw not in TIME_WINDOWS:
        # allow specific time like "14:00"
        if not re.match(r"^\d{2}:\d{2}$", tw):
            return err("invalid time_window")
    jid = new_id()
    job = {
        "id": jid,
        "booking_id": bid,
        "client_id": b["client_id"],
        "technician_id": g.user["id"],
        "scheduled_date": sched.isoformat(),
        "time_window": tw,
        "status": "Scheduled",
        "notes": [],
        "photos": [],
        "address": b["address"],
        "service_type": b["service_type"],
        "category": b["category"],
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    JOBS[jid] = job
    b["state"] = "Converted"
    b["job_id"] = jid
    return jsonify(_job_view(job)), 201


@app.get("/api/jobs")
@auth_required()
def list_jobs():
    u = g.user
    if u["role"] == "Technician":
        result = [j for j in JOBS.values() if j["technician_id"] == u["id"]]
    else:
        result = [j for j in JOBS.values() if j["client_id"] == u["id"]]
    return jsonify([_job_view(j) for j in result])


def _can_access_job(j, u):
    if u["role"] == "Technician":
        return j["technician_id"] == u["id"]
    return j["client_id"] == u["id"]


@app.get("/api/jobs/<jid>")
@auth_required()
def get_job(jid):
    j = JOBS.get(jid)
    if not j:
        return err("not found", 404)
    if not _can_access_job(j, g.user):
        return err("forbidden", 403)
    return jsonify(_job_view(j))


STATUS_ORDER = ["Scheduled", "In Progress", "Completed"]


@app.post("/api/jobs/<jid>/status")
@auth_required(role="Technician")
def update_job_status(jid):
    j = JOBS.get(jid)
    if not j:
        return err("not found", 404)
    if j["technician_id"] != g.user["id"]:
        return err("forbidden", 403)
    data = request.get_json(silent=True) or {}
    new_status = data.get("status")
    if new_status not in STATUS_ORDER:
        return err("invalid status")
    cur = STATUS_ORDER.index(j["status"])
    nxt = STATUS_ORDER.index(new_status)
    if nxt != cur + 1:
        return err("invalid transition (must be next in order, no skipping/backward)")
    if new_status == "Completed" and not j["notes"]:
        return err("at least one note required to complete")
    j["status"] = new_status
    return jsonify(_job_view(j))


@app.post("/api/jobs/<jid>/notes")
@auth_required(role="Technician")
def add_note(jid):
    j = JOBS.get(jid)
    if not j:
        return err("not found", 404)
    if j["technician_id"] != g.user["id"]:
        return err("forbidden", 403)
    data = request.get_json(silent=True) or {}
    text = (data.get("text") or "").strip()
    if not text:
        return err("text required")
    note = {"id": new_id(), "text": text,
            "created_at": datetime.now(timezone.utc).isoformat()}
    j["notes"].append(note)
    return jsonify(note), 201


@app.post("/api/jobs/<jid>/photos")
@auth_required(role="Technician")
def add_photo(jid):
    j = JOBS.get(jid)
    if not j:
        return err("not found", 404)
    if j["technician_id"] != g.user["id"]:
        return err("forbidden", 403)
    data = request.get_json(silent=True) or {}
    url = (data.get("url") or "").strip()
    if not url:
        return err("url required")
    photo = {"id": new_id(), "url": url,
             "created_at": datetime.now(timezone.utc).isoformat()}
    j["photos"].append(photo)
    return jsonify(photo), 201


# ---------- Invoices ----------
def _auto_overdue(inv):
    if inv["status"] == "Sent":
        due = parse_date(inv["due_date"])
        if due and due < today_utc():
            inv["status"] = "Overdue"
    return inv


def _has_active_invoice(job_id):
    for inv in INVOICES.values():
        if inv["job_id"] == job_id:
            _auto_overdue(inv)
            if inv["status"] in ("Draft", "Sent", "Overdue"):
                return True
    return False


@app.post("/api/jobs/<jid>/invoices")
@auth_required(role="Technician")
def create_invoice(jid):
    j = JOBS.get(jid)
    if not j:
        return err("not found", 404)
    if j["technician_id"] != g.user["id"]:
        return err("forbidden", 403)
    if j["status"] != "Completed":
        return err("job must be Completed")
    data = request.get_json(silent=True) or {}
    try:
        amount = float(data.get("amount"))
    except (TypeError, ValueError):
        return err("amount required")
    if amount <= 0:
        return err("amount must be > 0")
    due = parse_date(data.get("due_date") or "")
    if not due:
        return err("due_date required")
    if due < today_utc():
        return err("due_date must be today or future")
    if _has_active_invoice(jid):
        return err("an active invoice already exists for this job")
    iid = new_id()
    inv = {
        "id": iid,
        "job_id": jid,
        "technician_id": g.user["id"],
        "client_id": j["client_id"],
        "amount": amount,
        "due_date": due.isoformat(),
        "status": "Draft",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    INVOICES[iid] = inv
    return jsonify(inv), 201


@app.get("/api/invoices")
@auth_required()
def list_invoices():
    u = g.user
    result = []
    for inv in INVOICES.values():
        _auto_overdue(inv)
        if u["role"] == "Technician":
            if inv["technician_id"] == u["id"]:
                result.append(inv)
        else:
            if inv["client_id"] == u["id"] and inv["status"] != "Draft":
                result.append(inv)
    return jsonify(result)


@app.get("/api/invoices/<iid>")
@auth_required()
def get_invoice(iid):
    inv = INVOICES.get(iid)
    if not inv:
        return err("not found", 404)
    _auto_overdue(inv)
    u = g.user
    if u["role"] == "Technician" and inv["technician_id"] == u["id"]:
        return jsonify(inv)
    if u["role"] == "Client" and inv["client_id"] == u["id"] and inv["status"] != "Draft":
        return jsonify(inv)
    return err("forbidden", 403)


@app.post("/api/invoices/<iid>/send")
@auth_required(role="Technician")
def send_invoice(iid):
    inv = INVOICES.get(iid)
    if not inv or inv["technician_id"] != g.user["id"]:
        return err("not found", 404)
    if inv["status"] != "Draft":
        return err("only Draft can be Sent")
    inv["status"] = "Sent"
    _auto_overdue(inv)
    return jsonify(inv)


@app.post("/api/invoices/<iid>/pay")
@auth_required(role="Technician")
def pay_invoice(iid):
    inv = INVOICES.get(iid)
    if not inv or inv["technician_id"] != g.user["id"]:
        return err("not found", 404)
    _auto_overdue(inv)
    if inv["status"] not in ("Sent", "Overdue"):
        return err("only Sent/Overdue can be marked Paid")
    inv["status"] = "Paid"
    return jsonify(inv)


@app.post("/api/invoices/<iid>/void")
@auth_required(role="Technician")
def void_invoice(iid):
    inv = INVOICES.get(iid)
    if not inv or inv["technician_id"] != g.user["id"]:
        return err("not found", 404)
    _auto_overdue(inv)
    if inv["status"] == "Paid":
        return err("cannot void a Paid invoice")
    if inv["status"] not in ("Draft", "Sent", "Overdue"):
        return err("cannot void this invoice")
    inv["status"] = "Void"
    return jsonify(inv)


@app.get("/api/health")
def health():
    return jsonify({"ok": True})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
