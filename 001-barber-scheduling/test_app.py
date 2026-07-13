import unittest
from app import app
import json

class BarberShopTestCase(unittest.TestCase):
    def setUp(self):
        self.app = app.test_client()
        self.app.testing = True

    def test_full_flow(self):
        # 1. Get today's schedule
        response = self.app.get('/schedule')
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertTrue(len(data) > 0)
        
        # Get a slot for testing
        slot = data[0]
        date = slot['date']
        start_time = slot['start_time']
        end_time = slot['end_time']
        barber = slot['barber']

        # 2. Book an appointment
        payload = {
            "date": date,
            "start_time": start_time,
            "end_time": end_time,
            "barber": barber,
            "customer_name": "John Doe",
            "notes": "Trim and shave"
        }
        response = self.app.post('/appointments', json=payload)
        self.assertEqual(response.status_code, 201)

        # 3. Try to book the same slot (double booking)
        response = self.app.post('/appointments', json=payload)
        self.assertEqual(response.status_code, 409)

        # 4. Book with empty customer name
        payload_empty = payload.copy()
        payload_empty["customer_name"] = ""
        response = self.app.post('/appointments', json=payload_empty)
        self.assertEqual(response.status_code, 400)

        # 5. View appointment
        # We need to find the ID. Let's assume it's 1 for the first one created in a fresh DB
        # Better: fetch it from the schedule or just try ID 1
        response = self.app.get('/appointments/1')
        self.assertEqual(response.status_code, 200)
        app_data = json.loads(response.data)
        self.assertEqual(app_data['customer_name'], "John Doe")

        # 6. Edit appointment
        edit_payload = {"customer_name": "John Smith", "notes": "Just a trim"}
        response = self.app.put('/appointments/1', json=edit_payload)
        self.assertEqual(response.status_code, 200)

        # Verify edit
        response = self.app.get('/appointments/1')
        app_data = json.loads(response.data)
        self.assertEqual(app_data['customer_name'], "John Smith")

        # 7. Cancel appointment
        response = self.app.delete('/appointments/1')
        self.assertEqual(response.status_code, 200)

        # Verify cancelled
        response = self.app.get('/appointments/1')
        self.assertEqual(response.status_code, 404)

if __name__ == '__main__':
    # Reset DB for clean test
    import os
    if os.path.exists('barber_shop.db'):
        os.remove('barber_shop.db')
    import models
    models.init_db()
    
    unittest.main()
