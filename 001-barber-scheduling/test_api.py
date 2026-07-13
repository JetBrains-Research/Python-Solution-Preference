#!/usr/bin/env python3
import requests
import json

BASE_URL = 'http://localhost:5001'

def test_get_schedule():
    print("=== Test: Get Schedule (today) ===")
    response = requests.get(f'{BASE_URL}/schedule')
    print(f"Status: {response.status_code}")
    print(f"Response: {json.dumps(response.json(), indent=2)}")
    print()

def test_get_schedule_date():
    print("=== Test: Get Schedule (specific date) ===")
    response = requests.get(f'{BASE_URL}/schedule?date=2024-01-15')
    print(f"Status: {response.status_code}")
    data = response.json()
    print(f"Date: {data.get('date')}")
    print(f"Number of barber schedules: {len(data.get('schedule', []))}")
    print()

def test_add_appointment():
    print("=== Test: Add Appointment ===")
    data = {
        'customer_name': 'John Doe',
        'notes': 'First visit, needs haircut',
        'date': '2024-01-15',
        'barber': 'Alex',
        'start_time': '09:00'
    }
    response = requests.post(f'{BASE_URL}/appointments', json=data)
    print(f"Status: {response.status_code}")
    print(f"Response: {json.dumps(response.json(), indent=2)}")
    print()
    return response.json().get('id') if response.status_code == 201 else None

def test_add_appointment_duplicate():
    print("=== Test: Add Duplicate Appointment (should fail) ===")
    data = {
        'customer_name': 'Jane Doe',
        'date': '2024-01-15',
        'barber': 'Alex',
        'start_time': '09:00'
    }
    response = requests.post(f'{BASE_URL}/appointments', json=data)
    print(f"Status: {response.status_code}")
    print(f"Response: {json.dumps(response.json(), indent=2)}")
    print()

def test_add_appointment_empty_name():
    print("=== Test: Add Appointment with Empty Name (should fail) ===")
    data = {
        'customer_name': '',
        'date': '2024-01-15',
        'barber': 'Alex',
        'start_time': '10:00'
    }
    response = requests.post(f'{BASE_URL}/appointments', json=data)
    print(f"Status: {response.status_code}")
    print(f"Response: {json.dumps(response.json(), indent=2)}")
    print()

def test_get_appointment(appointment_id):
    print(f"=== Test: Get Appointment ({appointment_id}) ===")
    response = requests.get(f'{BASE_URL}/appointments/{appointment_id}')
    print(f"Status: {response.status_code}")
    print(f"Response: {json.dumps(response.json(), indent=2)}")
    print()

def test_update_appointment(appointment_id):
    print(f"=== Test: Update Appointment ({appointment_id}) ===")
    data = {
        'customer_name': 'John Updated',
        'notes': 'Updated notes'
    }
    response = requests.put(f'{BASE_URL}/appointments/{appointment_id}', json=data)
    print(f"Status: {response.status_code}")
    print(f"Response: {json.dumps(response.json(), indent=2)}")
    print()

def test_update_appointment_empty_name(appointment_id):
    print(f"=== Test: Update Appointment with Empty Name (should fail) ===")
    data = {
        'customer_name': ''
    }
    response = requests.put(f'{BASE_URL}/appointments/{appointment_id}', json=data)
    print(f"Status: {response.status_code}")
    print(f"Response: {json.dumps(response.json(), indent=2)}")
    print()

def test_cancel_appointment(appointment_id):
    print(f"=== Test: Cancel Appointment ({appointment_id}) ===")
    response = requests.delete(f'{BASE_URL}/appointments/{appointment_id}')
    print(f"Status: {response.status_code}")
    print(f"Response: {json.dumps(response.json(), indent=2)}")
    print()

def test_schedule_after_booking():
    print("=== Test: Get Schedule with Booking ===")
    response = requests.get(f'{BASE_URL}/schedule?date=2024-01-15')
    print(f"Status: {response.status_code}")
    data = response.json()
    # Find Alex's schedule and check the 09:00 slot
    for barber_schedule in data['schedule']:
        if barber_schedule[0]['barber'] == 'Alex':
            for slot in barber_schedule:
                if slot['start_time'] == '09:00':
                    print(f"Alex 09:00 slot: {json.dumps(slot, indent=2)}")
    print()

def run_all_tests():
    # Test getting schedule
    test_get_schedule()
    test_get_schedule_date()
    
    # Test adding appointment
    apt_id = test_add_appointment()
    
    if apt_id:
        # Test duplicate booking
        test_add_appointment_duplicate()
        
        # Test empty name
        test_add_appointment_empty_name()
        
        # Test getting appointment
        test_get_appointment(apt_id)
        
        # Test schedule with booking
        test_schedule_after_booking()
        
        # Test updating appointment
        test_update_appointment(apt_id)
        
        # Test update with empty name
        test_update_appointment_empty_name(apt_id)
        
        # Test canceling appointment
        test_cancel_appointment(apt_id)
        
        # Verify appointment is gone
        test_get_appointment(apt_id)

if __name__ == '__main__':
    run_all_tests()
