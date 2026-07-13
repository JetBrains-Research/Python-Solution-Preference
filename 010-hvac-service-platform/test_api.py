import requests
import json
from datetime import datetime, timedelta

BASE_URL = "http://localhost:8000"

def test_signup_and_login():
    # Test client signup
    client_data = {
        "name": "John Doe",
        "email": "john@example.com",
        "password": "password123",
        "role": "Client"
    }
    resp = requests.post(f"{BASE_URL}/signup", json=client_data)
    assert resp.status_code == 200, f"Client signup failed: {resp.text}"
    client = resp.json()
    client_token = resp.headers.get("Authorization", "").replace("Bearer ", "")
    print(f"Client signed up: {client['id']}, token: {client_token[:20]}...")
    
    # Test technician signup
    tech_data = {
        "name": "Jane Smith",
        "email": "jane@example.com",
        "password": "password123",
        "role": "Technician"
    }
    resp = requests.post(f"{BASE_URL}/signup", json=tech_data)
    assert resp.status_code == 200, f"Technician signup failed: {resp.text}"
    tech = resp.json()
    tech_token = resp.headers.get("Authorization", "").replace("Bearer ", "")
    print(f"Technician signed up: {tech['id']}, token: {tech_token[:20]}...")
    
    return client_token, tech_token, client['id'], tech['id']

def test_properties(client_token, client_id):
    headers = {"Authorization": f"Bearer {client_token}"}
    
    # Create property
    property_data = {
        "label": "Main House",
        "street": "123 Main St",
        "city": "Springfield",
        "state": "IL",
        "zip_code": "62701"
    }
    resp = requests.post(f"{BASE_URL}/properties", json=property_data, headers=headers)
    assert resp.status_code == 200, f"Create property failed: {resp.text}"
    property_id = resp.json()['id']
    print(f"Property created: {property_id}")
    
    # List properties
    resp = requests.get(f"{BASE_URL}/properties", headers=headers)
    assert resp.status_code == 200, f"List properties failed: {resp.text}"
    assert len(resp.json()) >= 1
    print(f"Properties listed: {len(resp.json())}")
    
    # Add equipment
    equipment_data = {
        "service_type": "HVAC",
        "equipment_type": "Furnace",
        "manufacturer": "Carrier",
        "model": "Model 123"
    }
    resp = requests.post(f"{BASE_URL}/properties/{property_id}/equipment", json=equipment_data, headers=headers)
    assert resp.status_code == 200, f"Add equipment failed: {resp.text}"
    print(f"Equipment added: {resp.json()['id']}")
    
    return property_id

def test_guest_booking():
    # Guest booking (no auth)
    booking_data = {
        "service_type": "HVAC",
        "booking_type": "Residential",
        "category": "Repair",
        "urgency": "Standard",
        "name": "Guest User",
        "email": "guest@example.com",
        "phone": "5551234567",
        "street": "456 Oak Ave",
        "city": "Chicago",
        "state": "IL",
        "zip_code": "60601",
        "description": "AC not working"
    }
    resp = requests.post(f"{BASE_URL}/bookings", json=booking_data)
    assert resp.status_code == 200, f"Guest booking failed: {resp.text}"
    booking = resp.json()
    tracking_token = booking['tracking_token']
    print(f"Guest booking created: {booking['id']}, token: {tracking_token[:20]}...")
    
    # Guest can view booking via token
    resp = requests.get(f"{BASE_URL}/bookings/token/{tracking_token}")
    assert resp.status_code == 200, f"Guest view booking failed: {resp.text}"
    print(f"Guest booking viewed via token")
    
    return tracking_token

def test_client_booking(client_token, property_id):
    headers = {"Authorization": f"Bearer {client_token}"}
    
    # Client booking with property
    booking_data = {
        "service_type": "Plumbing",
        "booking_type": "Residential",
        "category": "Maintenance",
        "urgency": "Urgent",
        "phone": "5559876543",
        "property_id": property_id,
        "description": "Need plumbing maintenance"
    }
    resp = requests.post(f"{BASE_URL}/bookings", json=booking_data, headers=headers)
    assert resp.status_code == 200, f"Client booking failed: {resp.text}"
    booking = resp.json()
    print(f"Client booking created: {booking['id']}, state: {booking['state']}")
    
    # Client can view their bookings
    resp = requests.get(f"{BASE_URL}/bookings", headers=headers)
    assert resp.status_code == 200, f"Client list bookings failed: {resp.text}"
    print(f"Client bookings: {len(resp.json())}")
    
    return booking['id']

def test_technician_booking_list(tech_token):
    headers = {"Authorization": f"Bearer {tech_token}"}
    
    # Technician can see all new bookings
    resp = requests.get(f"{BASE_URL}/bookings", headers=headers)
    assert resp.status_code == 200, f"Technician list bookings failed: {resp.text}"
    bookings = resp.json()
    print(f"Technician sees {len(bookings)} new bookings")
    
    if bookings:
        return bookings[0]['id']
    return None

def test_convert_to_job(tech_token, booking_id):
    headers = {"Authorization": f"Bearer {tech_token}"}
    
    # Convert booking to job
    future_date = datetime.utcnow() + timedelta(days=1)
    job_data = {
        "scheduled_date": future_date.isoformat(),
        "time_window": "AM"
    }
    resp = requests.post(f"{BASE_URL}/bookings/{booking_id}/convert", json=job_data, headers=headers)
    assert resp.status_code == 200, f"Convert to job failed: {resp.text}"
    job = resp.json()
    print(f"Job created: {job['id']}, status: {job['status']}")
    
    return job['id']

def test_job_workflow(tech_token, job_id):
    headers = {"Authorization": f"Bearer {tech_token}"}
    
    # Add note
    note_data = {"content": "Arrived at site, assessed issue"}
    resp = requests.post(f"{BASE_URL}/jobs/{job_id}/notes", json=note_data, headers=headers)
    assert resp.status_code == 200, f"Add note failed: {resp.text}"
    print(f"Note added: {resp.json()['id']}")
    
    # Add photo
    photo_data = {"filename": "photo1.jpg"}
    resp = requests.post(f"{BASE_URL}/jobs/{job_id}/photos", json=photo_data, headers=headers)
    assert resp.status_code == 200, f"Add photo failed: {resp.text}"
    print(f"Photo added: {resp.json()['id']}")
    
    # Update status to In Progress
    resp = requests.post(f"{BASE_URL}/jobs/{job_id}/status?status=In%20Progress", headers=headers)
    assert resp.status_code == 200, f"Update status failed: {resp.text}"
    print(f"Status updated to: {resp.json()['status']}")
    
    # Update status to Completed
    resp = requests.post(f"{BASE_URL}/jobs/{job_id}/status?status=Completed", headers=headers)
    assert resp.status_code == 200, f"Complete job failed: {resp.text}"
    print(f"Job completed")
    
    return job_id

def test_invoice_workflow(tech_token, job_id):
    headers = {"Authorization": f"Bearer {tech_token}"}
    
    # Create invoice
    future_date = datetime.utcnow() + timedelta(days=30)
    invoice_data = {
        "amount": 500,
        "due_date": future_date.isoformat()
    }
    resp = requests.post(f"{BASE_URL}/jobs/{job_id}/invoices", json=invoice_data, headers=headers)
    assert resp.status_code == 200, f"Create invoice failed: {resp.text}"
    invoice = resp.json()
    print(f"Invoice created: {invoice['id']}, status: {invoice['status']}")
    
    # Send invoice
    resp = requests.post(f"{BASE_URL}/invoices/{invoice['id']}/send", headers=headers)
    assert resp.status_code == 200, f"Send invoice failed: {resp.text}"
    print(f"Invoice sent")
    
    # Mark paid
    resp = requests.post(f"{BASE_URL}/invoices/{invoice['id']}/mark-paid", headers=headers)
    assert resp.status_code == 200, f"Mark paid failed: {resp.text}"
    print(f"Invoice marked paid")
    
    return invoice['id']

def main():
    print("=" * 50)
    print("Testing HVAC/Plumbing Service Platform API")
    print("=" * 50)
    
    # Test auth
    client_token, tech_token, client_id, tech_id = test_signup_and_login()
    print()
    
    # Test properties
    property_id = test_properties(client_token, client_id)
    print()
    
    # Test guest booking
    guest_token = test_guest_booking()
    print()
    
    # Test client booking
    client_booking_id = test_client_booking(client_token, property_id)
    print()
    
    # Test technician workflow
    booking_id = test_technician_booking_list(tech_token)
    print()
    
    if booking_id:
        job_id = test_convert_to_job(tech_token, booking_id)
        print()
        test_job_workflow(tech_token, job_id)
        print()
        test_invoice_workflow(tech_token, job_id)
        print()
    
    print("=" * 50)
    print("All tests passed!")
    print("=" * 50)

if __name__ == "__main__":
    main()
