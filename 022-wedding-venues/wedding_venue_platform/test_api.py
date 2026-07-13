#!/usr/bin/env python3
"""Test script for Wedding Venue Platform API"""

import requests
import json
from datetime import date, timedelta

BASE_URL = "http://localhost:8765"

def test_api():
    print("=== Testing Wedding Venue Platform API ===\n")
    
    # 1. Test signup - Manager
    print("1. Creating Manager account...")
    manager_data = {
        "email": "manager@example.com",
        "password": "password123",
        "role": "manager",
        "name": "John Manager",
        "phone": "555-1234",
        "business_name": "Dream Venues Ltd"
    }
    response = requests.post(f"{BASE_URL}/accounts/signup", json=manager_data)
    print(f"   Status: {response.status_code}")
    if response.status_code != 201:
        print(f"   Error: {response.text}")
        return
    manager = response.json()
    manager_id = manager['id']
    print(f"   Manager ID: {manager_id}\n")
    
    # 2. Test signup - Couple
    print("2. Creating Couple account...")
    couple_data = {
        "email": "couple@example.com",
        "password": "password123",
        "role": "couple",
        "partner_name": "Jane Doe",
        "postcode": "B34",
        "wedding_date": (date.today() + timedelta(days=180)).isoformat(),
        "venue_type_preference": "Either"
    }
    response = requests.post(f"{BASE_URL}/accounts/signup", json=couple_data)
    print(f"   Status: {response.status_code}")
    if response.status_code != 201:
        print(f"   Error: {response.text}")
        return
    couple = response.json()
    couple_id = couple['id']
    print(f"   Couple ID: {couple_id}\n")
    
    # 3. Create a venue
    print("3. Creating a venue...")
    venue_data = {
        "name": "Grand Hall",
        "address": "123 Main Street",
        "postcode": "B34",
        "description": "A beautiful grand hall perfect for weddings. Our venue offers stunning views, elegant decor, and world-class service. We have been hosting memorable weddings for over 20 years. The hall features a large dance floor, state-of-the-art sound system, and professional lighting. Our experienced staff will ensure your special day runs smoothly. We offer customizable packages to suit your needs and budget. The venue can be decorated to match any theme you desire. Our catering partners provide exceptional food and beverages. Book your dream wedding with us today!",
        "contact_info": "info@grandhall.com",
        "min_capacity": 50,
        "max_capacity": 200,
        "base_fee": 2000.0,
        "per_person_fee": 50.0,
        "venue_type": "Both",
        "status": "Active",
        "main_image": "https://example.com/main.jpg",
        "images": ["https://example.com/img1.jpg", "https://example.com/img2.jpg"]
    }
    response = requests.post(f"{BASE_URL}/venues", json=venue_data, params={"manager_id": manager_id})
    print(f"   Status: {response.status_code}")
    if response.status_code != 201:
        print(f"   Error: {response.text}")
        return
    venue = response.json()
    venue_id = venue['id']
    print(f"   Venue ID: {venue_id}\n")
    
    # 4. Search venues
    print("4. Searching venues...")
    search_data = {
        "postcode": "B34",
        "date": (date.today() + timedelta(days=90)).isoformat(),
        "guest_count": 100,
        "venue_type": "Either"
    }
    response = requests.post(f"{BASE_URL}/search", json=search_data)
    print(f"   Status: {response.status_code}")
    results = response.json()
    print(f"   Found {len(results)} venues\n")
    
    # 5. Get venue details
    print("5. Getting venue details...")
    response = requests.get(f"{BASE_URL}/venues/{venue_id}", params={"guest_count": 100})
    print(f"   Status: {response.status_code}")
    if response.status_code != 200:
        print(f"   Error: {response.text}")
        return
    venue_detail = response.json()
    print(f"   Estimated price: {venue_detail.get('estimated_price')}\n")
    
    # 6. Create tour slot
    print("6. Creating tour slot...")
    slot_data = {
        "slot_date": (date.today() + timedelta(days=30)).isoformat(),
        "slot_time": "14:00",
        "duration_minutes": 60,
        "capacity": 5
    }
    response = requests.post(f"{BASE_URL}/tours/slots/venue/{venue_id}", json=slot_data, params={"manager_id": manager_id})
    print(f"   Status: {response.status_code}")
    if response.status_code != 201:
        print(f"   Error: {response.text}")
        return
    slot = response.json()
    slot_id = slot['id']
    print(f"   Slot ID: {slot_id}\n")
    
    # 7. Book tour slot
    print("7. Booking tour slot...")
    booking_data = {
        "slot_id": slot_id,
        "tour_type": "In-Person",
        "attendee_count": 2,
        "notes": "Looking for an outdoor venue"
    }
    response = requests.post(f"{BASE_URL}/tours/bookings", json=booking_data, params={"couple_id": couple_id})
    print(f"   Status: {response.status_code}")
    if response.status_code != 201:
        print(f"   Error: {response.text}")
        return
    tour_booking = response.json()
    tour_booking_id = tour_booking['id']
    print(f"   Booking ID: {tour_booking_id}, Status: {tour_booking['status']}\n")
    
    # 8. Approve tour booking
    print("8. Approving tour booking...")
    update_data = {"status": "Approved"}
    response = requests.put(f"{BASE_URL}/tours/bookings/{tour_booking_id}", json=update_data, params={"manager_id": manager_id})
    print(f"   Status: {response.status_code}")
    if response.status_code != 200:
        print(f"   Error: {response.text}")
        return
    updated = response.json()
    print(f"   New Status: {updated['status']}\n")
    
    # 9. Create wedding booking request
    print("9. Creating wedding booking request...")
    wedding_data = {
        "venue_id": venue_id,
        "booking_date": (date.today() + timedelta(days=180)).isoformat(),
        "guest_count": 100,
        "note": "We love your venue!"
    }
    response = requests.post(f"{BASE_URL}/weddings/requests", json=wedding_data, params={"couple_id": couple_id})
    print(f"   Status: {response.status_code}")
    if response.status_code != 201:
        print(f"   Error: {response.text}")
        return
    wedding_booking = response.json()
    wedding_booking_id = wedding_booking['id']
    print(f"   Booking ID: {wedding_booking_id}, Status: {wedding_booking['status']}\n")
    
    # 10. Confirm wedding booking
    print("10. Confirming wedding booking...")
    confirm_data = {"status": "Confirmed"}
    response = requests.put(f"{BASE_URL}/weddings/requests/{wedding_booking_id}", json=confirm_data, params={"manager_id": manager_id})
    print(f"   Status: {response.status_code}")
    if response.status_code != 200:
        print(f"   Error: {response.text}")
        return
    confirmed = response.json()
    print(f"   New Status: {confirmed['status']}\n")
    
    # 11. Create blocked date
    print("11. Creating blocked date...")
    blocked_data = {
        "blocked_date": (date.today() + timedelta(days=60)).isoformat(),
        "note": "Staff training"
    }
    response = requests.post(f"{BASE_URL}/blocked-dates/venue/{venue_id}", json=blocked_data, params={"manager_id": manager_id})
    print(f"   Status: {response.status_code}")
    if response.status_code != 201:
        print(f"   Error: {response.text}")
        return
    blocked = response.json()
    print(f"   Blocked date: {blocked['blocked_date']}\n")
    
    # 12. Try to book on blocked date (should fail)
    print("12. Attempting to book on blocked date (should fail)...")
    bad_wedding_data = {
        "venue_id": venue_id,
        "booking_date": (date.today() + timedelta(days=60)).isoformat(),
        "guest_count": 100
    }
    response = requests.post(f"{BASE_URL}/weddings/requests", json=bad_wedding_data, params={"couple_id": couple_id})
    print(f"   Status: {response.status_code} (expected 400)\n")
    
    print("=== All tests completed ===")

if __name__ == "__main__":
    test_api()
