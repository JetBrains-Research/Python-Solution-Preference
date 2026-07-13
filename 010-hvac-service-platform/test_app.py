"""End-to-end tests exercising the HVAC/Plumbing platform API."""
from datetime import datetime, timedelta, timezone
def today():
    return datetime.now(timezone.utc).date()
class date:
    @staticmethod
    def today():
        return today()
from app import app

client = app.test_client()


def post(path, data=None, token=None):
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return client.post(path, json=data or {}, headers=headers)


def get(path, token=None):
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return client.get(path, headers=headers)


def dele(path, token=None):
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return client.delete(path, headers=headers)


# --- Signup validations
r = post("/api/auth/signup", {"name": "C", "email": "bad", "password": "abcdef", "role": "Client"})
assert r.status_code == 400, r.json
r = post("/api/auth/signup", {"name": "C", "email": "c@x.com", "password": "123", "role": "Client"})
assert r.status_code == 400
r = post("/api/auth/signup", {"name": "C", "email": "c@x.com", "password": "abcdef", "role": "Bad"})
assert r.status_code == 400

# --- Sign up client + technician
r = post("/api/auth/signup", {"name": "Alice", "email": "alice@x.com", "password": "abcdef", "role": "Client"})
assert r.status_code == 201, r.json
client_token = r.json["token"]
r2 = post("/api/auth/signup", {"name": "Alice", "email": "alice@x.com", "password": "abcdef", "role": "Client"})
assert r2.status_code == 400

r = post("/api/auth/signup", {"name": "Bob", "email": "bob@x.com", "password": "abcdef", "role": "Technician"})
tech_token = r.json["token"]

# --- Login
r = post("/api/auth/login", {"email": "alice@x.com", "password": "wrong"})
assert r.status_code == 401
r = post("/api/auth/login", {"email": "alice@x.com", "password": "abcdef"})
assert r.status_code == 200

# --- Property
r = post("/api/properties", {"label": "Home", "street": "1 Main", "city": "NYC",
                              "state": "NY", "zip": "12345"}, token=client_token)
assert r.status_code == 201, r.json
prop_id = r.json["id"]

r = post("/api/properties", {"label": "Home", "street": "1 Main", "city": "NYC",
                              "state": "NY", "zip": "123"}, token=client_token)
assert r.status_code == 400  # bad zip

# Add equipment
r = post(f"/api/properties/{prop_id}/equipment",
         {"service_type": "HVAC", "equipment_type": "Furnace"}, token=client_token)
assert r.status_code == 201, r.json
eq_id = r.json["id"]

r = get(f"/api/properties/{prop_id}/equipment", token=client_token)
assert len(r.json) == 1

# Guest booking - missing address
r = post("/api/bookings", {
    "service_type": "HVAC", "booking_type": "Residential", "category": "Repair",
    "urgency": "Standard", "name": "Guest", "email": "g@x.com", "phone": "5551234567",
})
assert r.status_code == 400

# Guest booking - full valid
r = post("/api/bookings", {
    "service_type": "HVAC", "booking_type": "Residential", "category": "Repair",
    "urgency": "Standard", "name": "Guest", "email": "g@x.com", "phone": "5551234567",
    "address": {"street": "2 Elm", "city": "NYC", "state": "NY", "zip": "10001"},
})
assert r.status_code == 201, r.json
guest_bid = r.json["id"]
guest_token = r.json["tracking_token"]

# Track
r = get(f"/api/track/{guest_token}")
assert r.status_code == 200
assert r.json["booking"]["id"] == guest_bid

# Commercial requires company name
r = post("/api/bookings", {
    "service_type": "Plumbing", "booking_type": "Commercial", "category": "Installation",
    "urgency": "Urgent", "name": "Guest", "email": "g@x.com", "phone": "5551234567",
    "address": {"street": "2 Elm", "city": "NYC", "state": "NY", "zip": "10001"},
})
assert r.status_code == 400

r = post("/api/bookings", {
    "service_type": "Plumbing", "booking_type": "Commercial", "category": "Installation",
    "urgency": "Urgent", "name": "Guest", "email": "g@x.com", "phone": "5551234567",
    "company_name": "ACME",
    "address": {"street": "2 Elm", "city": "NYC", "state": "NY", "zip": "10001"},
})
assert r.status_code == 201

# Past preferred_date
past = (date.today() - timedelta(days=1)).isoformat()
r = post("/api/bookings", {
    "service_type": "HVAC", "booking_type": "Residential", "category": "Repair",
    "urgency": "Standard", "name": "Guest", "email": "g@x.com", "phone": "5551234567",
    "address": {"street": "2 Elm", "city": "NYC", "state": "NY", "zip": "10001"},
    "preferred_date": past,
})
assert r.status_code == 400

# Client booking using property
r = post("/api/bookings", {
    "service_type": "HVAC", "booking_type": "Residential", "category": "Maintenance",
    "urgency": "Standard", "phone": "5551234567", "property_id": prop_id,
}, token=client_token)
assert r.status_code == 201, r.json
client_bid = r.json["id"]
assert r.json["booking"]["client_id"] is not None
assert r.json["booking"]["name"] == "Alice"

# List bookings - client
r = get("/api/bookings", token=client_token)
assert len(r.json) == 1

# Tech sees all New
r = get("/api/bookings", token=tech_token)
assert len(r.json) >= 3

# Convert booking to job
today = date.today().isoformat()
r = post(f"/api/bookings/{client_bid}/convert",
         {"scheduled_date": today, "time_window": "AM"}, token=tech_token)
assert r.status_code == 201, r.json
job_id = r.json["id"]

# Second conversion fails
r = post(f"/api/bookings/{client_bid}/convert",
         {"scheduled_date": today, "time_window": "AM"}, token=tech_token)
assert r.status_code == 400

# Client sees job
r = get(f"/api/jobs/{job_id}", token=client_token)
assert r.status_code == 200

# Bookings list now excludes converted one for client
r = get("/api/bookings", token=client_token)
assert len(r.json) == 0

# Cannot complete without notes
r = post(f"/api/jobs/{job_id}/status", {"status": "In Progress"}, token=tech_token)
assert r.status_code == 200
r = post(f"/api/jobs/{job_id}/status", {"status": "Completed"}, token=tech_token)
assert r.status_code == 400

# Add note
r = post(f"/api/jobs/{job_id}/notes", {"text": "Repaired furnace"}, token=tech_token)
assert r.status_code == 201

# Skipping backward
r = post(f"/api/jobs/{job_id}/status", {"status": "Scheduled"}, token=tech_token)
assert r.status_code == 400

# Complete
r = post(f"/api/jobs/{job_id}/status", {"status": "Completed"}, token=tech_token)
assert r.status_code == 200

# Invoice
r = post(f"/api/jobs/{job_id}/invoices",
         {"amount": 100, "due_date": today}, token=tech_token)
assert r.status_code == 201, r.json
inv_id = r.json["id"]

# amount<=0
r = post(f"/api/jobs/{job_id}/invoices",
         {"amount": 0, "due_date": today}, token=tech_token)
assert r.status_code == 400

# active invoice conflict
r = post(f"/api/jobs/{job_id}/invoices",
         {"amount": 50, "due_date": today}, token=tech_token)
assert r.status_code == 400

# Client can't see Draft
r = get("/api/invoices", token=client_token)
assert len(r.json) == 0

# Send it
r = post(f"/api/invoices/{inv_id}/send", token=tech_token)
assert r.status_code == 200

r = get("/api/invoices", token=client_token)
assert len(r.json) == 1

# Void
r = post(f"/api/invoices/{inv_id}/void", token=tech_token)
assert r.status_code == 200

# Now can create new
r = post(f"/api/jobs/{job_id}/invoices",
         {"amount": 75, "due_date": today}, token=tech_token)
assert r.status_code == 201, r.json
inv2 = r.json["id"]
r = post(f"/api/invoices/{inv2}/send", token=tech_token)
r = post(f"/api/invoices/{inv2}/pay", token=tech_token)
assert r.status_code == 200
# Can't void paid
r = post(f"/api/invoices/{inv2}/void", token=tech_token)
assert r.status_code == 400

# Delete property cascades
r = dele(f"/api/properties/{prop_id}", token=client_token)
assert r.status_code == 200
r = get(f"/api/properties/{prop_id}/equipment", token=client_token)
assert r.status_code == 404

# Guest tracking sees invoices only after Sent
# convert guest booking, complete, send invoice
r = post(f"/api/bookings/{guest_bid}/convert",
         {"scheduled_date": today, "time_window": "PM"}, token=tech_token)
assert r.status_code == 201, r.json
gjob = r.json["id"]
r = post(f"/api/jobs/{gjob}/status", {"status": "In Progress"}, token=tech_token)
r = post(f"/api/jobs/{gjob}/notes", {"text": "done"}, token=tech_token)
r = post(f"/api/jobs/{gjob}/status", {"status": "Completed"}, token=tech_token)
assert r.status_code == 200
r = post(f"/api/jobs/{gjob}/invoices", {"amount": 200, "due_date": today}, token=tech_token)
ginv = r.json["id"]

# Track before send: no invoices
r = get(f"/api/track/{guest_token}")
assert r.json.get("invoices") == []
r = post(f"/api/invoices/{ginv}/send", token=tech_token)
r = get(f"/api/track/{guest_token}")
assert len(r.json["invoices"]) == 1

print("ALL TESTS PASSED")
