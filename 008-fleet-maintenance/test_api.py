import requests
import time
import sys

BASE_URL = "http://127.0.0.1:5000"

def test():
    # 1. Create Vehicles
    print("Creating vehicles...")
    v1 = requests.post(f"{BASE_URL}/vehicles", json={"name": "Car A", "odometer": 10000}).json()
    v2 = requests.post(f"{BASE_URL}/vehicles", json={"name": "Car B", "odometer": 20000}).json()
    print(f"Created v1: {v1['id']}, v2: {v2['id']}")

    # 2. Verify List Vehicles (Creation Order)
    print("Checking vehicle list order...")
    vehicles = requests.get(f"{BASE_URL}/vehicles").json()
    assert vehicles[0]['name'] == "Car A"
    assert vehicles[1]['name'] == "Car B"
    print("Vehicle order OK")

    # 3. Create Tasks for v1
    print("Creating tasks for Car A...")
    # Task 1: Overdue immediately (never completed)
    t1 = requests.post(f"{BASE_URL}/vehicles/{v1['id']}/tasks", json={"name": "Oil Change", "interval": 5000}).json()
    # Task 2: OK
    t2 = requests.post(f"{BASE_URL}/vehicles/{v1['id']}/tasks", json={"name": "Air Filter", "interval": 15000}).json()
    # Task 3: Due Soon (we will make it due soon by marking it done at a certain odometer)
    t3 = requests.post(f"{BASE_URL}/vehicles/{v1['id']}/tasks", json={"name": "Tires", "interval": 10000}).json()
    
    # Mark t3 as done at 10000 (current odometer)
    # distance_elapsed = 10000 - 10000 = 0. distance_until_due = 10000 - 0 = 10000 (OK)
    requests.patch(f"{BASE_URL}/tasks/{t3['id']}/done").json()
    
    # Now update odometer to 19100
    # t1: never completed -> Overdue
    # t2: never completed -> Overdue
    # t3: 19100 - 10000 = 9100. distance_until_due = 10000 - 9100 = 900 (Due Soon)
    requests.patch(f"{BASE_URL}/vehicles/{v1['id']}/odometer", json={"odometer": 19100}).json()
    
    # Let's refine t2 to be OK.
    # We need t2 to have been completed at say 15000.
    # 19100 - 15000 = 4100. Interval 15000. dist_until_due = 15000 - 4100 = 10900 (OK)
    # Wait, we can't change interval. Let's just mark t2 as done.
    # To do that we need to have had odometer at 15000.
    # Since we are already at 19100, marking it done now means last_completed = 19100.
    # distance_elapsed = 0. distance_until_due = 15000 (OK).
    requests.patch(f"{BASE_URL}/tasks/{t2['id']}/done").json()

    # Now for v1:
    # t1: Overdue (never completed)
    # t3: Due Soon (dist_until_due = 900)
    # t2: OK (dist_until_due = 15000)
    
    v1_detail = requests.get(f"{BASE_URL}/vehicles/{v1['id']}").json()
    tasks = v1_detail['tasks']
    
    assert tasks[0]['name'] == "Oil Change" and tasks[0]['status'] == "Overdue"
    assert tasks[1]['name'] == "Tires" and tasks[1]['status'] == "Due Soon"
    assert tasks[2]['name'] == "Air Filter" and tasks[2]['status'] == "OK"
    print("Task sorting and status OK")

    # 4. Check Aggregated Status
    vehicles = requests.get(f"{BASE_URL}/vehicles").json()
    v1_agg = next(v for v in vehicles if v['id'] == v1['id'])
    assert v1_agg['status'] == "Overdue"
    print("Aggregated status OK")

    # 5. Test Odometer decrease rejection
    resp = requests.patch(f"{BASE_URL}/vehicles/{v1['id']}/odometer", json={"odometer": 18000})
    assert resp.status_code == 400
    print("Odometer decrease rejected OK")

    # 6. Test Deletion
    requests.delete(f"{BASE_URL}/vehicles/{v2['id']}").json()
    vehicles = requests.get(f"{BASE_URL}/vehicles").json()
    assert len(vehicles) == 1
    print("Vehicle deletion OK")

    print("ALL TESTS PASSED")

if __name__ == "__main__":
    test()
