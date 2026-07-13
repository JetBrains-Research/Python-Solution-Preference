#!/usr/bin/env python3
import subprocess
import time
import requests
import json
import sys

def start_server():
    """Start the Flask server in the background."""
    print("Starting Flask server...")
    server_process = subprocess.Popen(['python3', 'app.py'], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    time.sleep(2)  # Give server time to start
    return server_process

def stop_server(server_process):
    """Stop the Flask server."""
    print("Stopping Flask server...")
    server_process.terminate()
    server_process.wait()

def test_schedule_endpoint():
    """Test the schedule endpoint."""
    print("Testing GET /schedule...")

    # Test default date (today)
    response = requests.get('http://127.0.0.1:5000/schedule')
    assert response.status_code == 200
    data = response.json()
    assert 'date' in data
    assert 'schedule' in data
    assert set(data['schedule'].keys()) == {'Alex', 'Lucy', 'George'}

    # Test specific date
    response = requests.get('http://127.0.0.1:5000/schedule?date=2026-07-08')
    assert response.status_code == 200
    data = response.json()
    assert data['date'] == '2026-07-08'

    print("✓ Schedule endpoint tests passed")

def test_add_appointment():
    """Test adding appointments."""
    print("Testing POST /appointments...")

    # Test valid appointment
    response = requests.post(
        'http://127.0.0.1:5000/appointments',
        json={
            'date': '2026-07-09',
            'barber': 'Alex',
            'start_time': '09:00',
            'customer_name': 'John Doe',
            'notes': 'Haircut'
        }
    )
    assert response.status_code == 201
    data = response.json()
    assert 'appointment' in data
    assert data['appointment']['customer_name'] == 'John Doe'

    # Test double booking
    response = requests.post(
        'http://127.0.0.1:5000/appointments',
        json={
            'date': '2026-07-09',
            'barber': 'Alex',
            'start_time': '09:00',
            'customer_name': 'Jane Smith'
        }
    )
    assert response.status_code == 409
    assert 'already booked' in response.json()['error']

    # Test empty customer name
    response = requests.post(
        'http://127.0.0.1:5000/appointments',
        json={
            'date': '2026-07-09',
            'barber': 'Alex',
            'start_time': '09:30',
            'customer_name': ''
        }
    )
    assert response.status_code == 400
    assert 'Customer name cannot be empty' in response.json()['error']

    # Test invalid time (outside hours)
    response = requests.post(
        'http://127.0.0.1:5000/appointments',
        json={
            'date': '2026-07-09',
            'barber': 'Alex',
            'start_time': '18:30',
            'customer_name': 'Test'
        }
    )
    assert response.status_code == 400
    assert '09:00 and 18:00' in response.json()['error']

    # Test invalid time (not 30-min aligned)
    response = requests.post(
        'http://127.0.0.1:5000/appointments',
        json={
            'date': '2026-07-09',
            'barber': 'Alex',
            'start_time': '10:15',
            'customer_name': 'Test'
        }
    )
    assert response.status_code == 400
    assert '30-minute intervals' in response.json()['error']

    # Test invalid barber
    response = requests.post(
        'http://127.0.0.1:5000/appointments',
        json={
            'date': '2026-07-09',
            'barber': 'InvalidBarber',
            'start_time': '09:00',
            'customer_name': 'Test'
        }
    )
    assert response.status_code == 400
    assert 'Invalid barber' in response.json()['error']

    print("✓ Add appointment tests passed")

def test_view_appointment():
    """Test viewing an appointment."""
    print("Testing GET /appointments/<id>...")

    # First add an appointment
    response = requests.post(
        'http://127.0.0.1:5000/appointments',
        json={
            'date': '2026-07-10',
            'barber': 'Lucy',
            'start_time': '10:00',
            'customer_name': 'Bob Smith',
            'notes': 'Beard trim'
        }
    )
    appointment_id = response.json()['appointment']['id']

    # Test viewing the appointment
    response = requests.get(f'http://127.0.0.1:5000/appointments/{appointment_id}')
    assert response.status_code == 200
    data = response.json()
    assert data['customer_name'] == 'Bob Smith'
    assert data['barber'] == 'Lucy'
    assert data['start_time'] == '10:00'

    # Test viewing non-existent appointment
    response = requests.get('http://127.0.0.1:5000/appointments/non-existent-id')
    assert response.status_code == 404

    print("✓ View appointment tests passed")

def test_update_appointment():
    """Test updating an appointment."""
    print("Testing PUT /appointments/<id>...")

    # First add an appointment
    response = requests.post(
        'http://127.0.0.1:5000/appointments',
        json={
            'date': '2026-07-11',
            'barber': 'George',
            'start_time': '11:00',
            'customer_name': 'Alice Johnson',
            'notes': ''
        }
    )
    appointment_id = response.json()['appointment']['id']

    # Test updating customer name and notes
    response = requests.put(
        f'http://127.0.0.1:5000/appointments/{appointment_id}',
        json={
            'customer_name': 'Alice Smith',
            'notes': 'Color treatment'
        }
    )
    assert response.status_code == 200
    data = response.json()
    assert data['appointment']['customer_name'] == 'Alice Smith'
    assert data['appointment']['notes'] == 'Color treatment'

    # Test updating with empty customer name
    response = requests.put(
        f'http://127.0.0.1:5000/appointments/{appointment_id}',
        json={
            'customer_name': ''
        }
    )
    assert response.status_code == 400
    assert 'Customer name cannot be empty' in response.json()['error']

    print("✓ Update appointment tests passed")

def test_cancel_appointment():
    """Test canceling an appointment."""
    print("Testing DELETE /appointments/<id>...")

    # First add an appointment
    response = requests.post(
        'http://127.0.0.1:5000/appointments',
        json={
            'date': '2026-07-12',
            'barber': 'Alex',
            'start_time': '14:00',
            'customer_name': 'Charlie Brown'
        }
    )
    appointment_id = response.json()['appointment']['id']

    # Test canceling the appointment
    response = requests.delete(f'http://127.0.0.1:5000/appointments/{appointment_id}')
    assert response.status_code == 200
    assert 'cancelled successfully' in response.json()['message']

    # Verify it's actually cancelled
    response = requests.get(f'http://127.0.0.1:5000/appointments/{appointment_id}')
    assert response.status_code == 404

    # Test canceling non-existent appointment
    response = requests.delete('http://127.0.0.1:5000/appointments/non-existent-id')
    assert response.status_code == 404

    print("✓ Cancel appointment tests passed")

def main():
    """Run all tests."""
    server_process = None
    try:
        server_process = start_server()

        # Wait a bit more to ensure server is ready
        time.sleep(1)

        test_schedule_endpoint()
        test_add_appointment()
        test_view_appointment()
        test_update_appointment()
        test_cancel_appointment()

        print("\n✅ All tests passed!")
        return 0

    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return 1
    finally:
        if server_process:
            stop_server(server_process)

if __name__ == '__main__':
    sys.exit(main())
