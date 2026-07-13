#!/usr/bin/env python3
"""Integration tests for the Energy Auditing Field App"""
import requests
import json
import os
import sys

BASE_URL = "http://localhost:8000"

def test_all():
    # Start server in background
    import subprocess
    import time
    
    # Remove old DB
    if os.path.exists("app.db"):
        os.remove("app.db")
    if os.path.exists("photos"):
        import shutil
        shutil.rmtree("photos", ignore_errors=True)
    
    # Start server
    server = subprocess.Popen([sys.executable, "main.py"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    time.sleep(2)  # Wait for server to start
    
    try:
        # 1. Register
        print("=== Test 1: Register ===")
        resp = requests.post(f"{BASE_URL}/api/register", json={
            "name": "Test User",
            "email": "test@example.com",
            "password": "password123"
        })
        print(f"Status: {resp.status_code}")
        data = resp.json()
        print(f"Response: {json.dumps(data, indent=2)}")
        token = data["token"]
        headers = {"Authorization": f"Bearer {token}"}
        assert resp.status_code == 200
        assert "token" in data
        
        # 2. Login
        print("\n=== Test 2: Login ===")
        resp = requests.post(f"{BASE_URL}/api/login", json={
            "email": "test@example.com",
            "password": "password123"
        })
        print(f"Status: {resp.status_code}")
        data2 = resp.json()
        print(f"Response: {json.dumps(data2, indent=2)}")
        assert resp.status_code == 200
        token = data2["token"]
        headers = {"Authorization": f"Bearer {token}"}
        
        # 3. Create Job
        print("\n=== Test 3: Create Job ===")
        resp = requests.post(f"{BASE_URL}/api/jobs", json={
            "street": "123 Main St",
            "city": "Albany",
            "state": "NY",
            "zip": "12201",
            "builder_name": "ABC Builders",
            "scheduled_date": "2025-06-15",
            "house_volume": 15000.0,
            "conditioned_floor_area": 2000.0,
            "num_stories": 2,
            "surface_area": 3500.0
        }, headers=headers)
        print(f"Status: {resp.status_code}")
        job = resp.json()
        print(f"Response: {json.dumps(job, indent=2)}")
        job_id = job["id"]
        assert resp.status_code == 200
        assert job["status"] == "Pending"
        
        # 4. List Jobs
        print("\n=== Test 4: List Jobs ===")
        resp = requests.get(f"{BASE_URL}/api/jobs", headers=headers)
        print(f"Status: {resp.status_code}")
        jobs = resp.json()
        print(f"Response: {json.dumps(jobs, indent=2)}")
        assert len(jobs) == 1
        assert jobs[0]["id"] == job_id
        
        # 5. Get Job Details (initial)
        print("\n=== Test 5: Job Details (initial) ===")
        resp = requests.get(f"{BASE_URL}/api/jobs/{job_id}", headers=headers)
        print(f"Status: {resp.status_code}")
        details = resp.json()
        print(f"Checklist items: {len(details['checklist']['items'])}")
        assert len(details['checklist']['items']) == 10
        assert all(it['status'] == 'Not Started' for it in details['checklist']['items'])
        
        # 6. Update Checklist Items
        print("\n=== Test 6: Update Checklist ===")
        statuses = ["Passed", "Failed", "N/A", "Passed", "Passed", "Failed", "N/A", "Passed", "Passed", "Passed"]
        for i, stat in enumerate(statuses, 1):
            resp = requests.put(f"{BASE_URL}/api/jobs/{job_id}/checklist/{i}", json={"status": stat}, headers=headers)
            assert resp.status_code == 200, f"Item {i} failed: {resp.text}"
        print("All 10 items updated")
        
        # Verify job moved to In Progress (checklist done but others not)
        resp = requests.get(f"{BASE_URL}/api/jobs/{job_id}", headers=headers)
        details = resp.json()
        print(f"Status after checklist update: {details['status']}")
        print(f"Checklist summary: {details['checklist']['summary']}")
        # 7 Passed out of 8 applicable = 7/8 = 87.5% -> rounds to 88%
        assert "88%" in details['checklist']['summary'], f"Expected 88% in summary, got: {details['checklist']['summary']}"
        
        # 7. Blower Door Test
        print("\n=== Test 7: Blower Door Test ===")
        bd_points = [
            {"house_pressure": 50.0, "fan_pressure": 120.0, "ring_config": "Ring A"},
            {"house_pressure": 45.0, "fan_pressure": 115.0, "ring_config": "Ring A"},
            {"house_pressure": 40.0, "fan_pressure": 108.0, "ring_config": "Ring A"},
            {"house_pressure": 35.0, "fan_pressure": 100.0, "ring_config": "Ring A"},
            {"house_pressure": 30.0, "fan_pressure": 92.0, "ring_config": "Ring A"},
        ]
        resp = requests.post(f"{BASE_URL}/api/jobs/{job_id}/blower-door", json={"data_points": bd_points}, headers=headers)
        print(f"Save: {resp.status_code} - {resp.json()}")
        assert resp.status_code == 200
        
        resp = requests.post(f"{BASE_URL}/api/jobs/{job_id}/blower-door/calculate", headers=headers)
        print(f"Calculate: {resp.status_code}")
        bd_result = resp.json()
        print(f"BD Result: {json.dumps(bd_result, indent=2)}")
        assert resp.status_code == 200
        assert "cfm50" in bd_result
        assert "ach50" in bd_result
        assert "r_squared" in bd_result
        
        # 8. Duct Leakage Test
        print("\n=== Test 8: Duct Leakage Test ===")
        dl_data = {
            "test_types": "BOTH",
            "tdl_ring_config": "Ring B",
            "tdl_fan_pressure": 50.0,
            "dlo_house_pressure": -25.0,
            "dlo_ring_config": "Ring B",
            "dlo_fan_pressure": 45.0
        }
        resp = requests.post(f"{BASE_URL}/api/jobs/{job_id}/duct-leakage", json=dl_data, headers=headers)
        print(f"Save: {resp.status_code} - {resp.json()}")
        assert resp.status_code == 200
        
        resp = requests.post(f"{BASE_URL}/api/jobs/{job_id}/duct-leakage/calculate", headers=headers)
        print(f"Calculate: {resp.status_code}")
        dl_result = resp.json()
        print(f"DL Result: {json.dumps(dl_result, indent=2)}")
        assert resp.status_code == 200
        assert "overall_compliance_pass" in dl_result
        
        # 9. Verify job is Completed
        print("\n=== Test 9: Job Completed ===")
        resp = requests.get(f"{BASE_URL}/api/jobs/{job_id}", headers=headers)
        details = resp.json()
        print(f"Status: {details['status']}")
        assert details['status'] == 'Completed', f"Expected Completed, got {details['status']}"
        
        # 10. Photo upload
        print("\n=== Test 10: Photo Upload ===")
        # Create a tiny JPEG
        import io
        from PIL import Image as PILImage
        try:
            img = PILImage.new('RGB', (10, 10), color='red')
            buf = io.BytesIO()
            img.save(buf, format='JPEG')
            buf.seek(0)
            
            resp = requests.post(f"{BASE_URL}/api/jobs/{job_id}/photos", 
                                 files={"file": ("test.jpg", buf, "image/jpeg")},
                                 headers=headers)
            print(f"Upload: {resp.status_code} - {resp.json()}")
            photo_id = resp.json()["id"]
            assert resp.status_code == 200
            
            # Get photo
            resp = requests.get(f"{BASE_URL}/api/jobs/{job_id}/photos/{photo_id}", headers=headers)
            print(f"Get photo: {resp.status_code}")
            assert resp.status_code == 200
            
            # Delete photo
            resp = requests.delete(f"{BASE_URL}/api/jobs/{job_id}/photos/{photo_id}", headers=headers)
            print(f"Delete photo: {resp.status_code} - {resp.json()}")
            assert resp.status_code == 200
        except ImportError:
            print("PIL not available, skipping photo upload test")
        
        # 11. Test logout
        print("\n=== Test 11: Logout ===")
        resp = requests.post(f"{BASE_URL}/api/logout", headers=headers)
        print(f"Status: {resp.status_code} - {resp.json()}")
        assert resp.status_code == 200
        
        # 12. Test auth failure
        print("\n=== Test 12: Auth failure ===")
        resp = requests.get(f"{BASE_URL}/api/jobs")
        print(f"No auth: {resp.status_code}")
        assert resp.status_code == 403
        
        print("\n" + "="*50)
        print("ALL TESTS PASSED!")
        print("="*50)
        
    finally:
        server.terminate()
        server.wait()

if __name__ == "__main__":
    test_all()
