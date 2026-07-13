#!/usr/bin/env python3
import requests
import json
import sys

BASE_URL = "http://localhost:12345/api"

def test_all():
    errors = []
    
    # Test 1: Login as admin
    print("Test 1: Login as admin...")
    resp = requests.post(f"{BASE_URL}/auth/login", json={"username": "admin", "password": "admin123"})
    if resp.status_code != 200:
        errors.append(f"Admin login failed: {resp.text}")
        return errors
    admin_data = resp.json()
    admin_token = admin_data["token"]
    print("  ✓ Admin login successful")
    
    # Test 2: Login as buyer
    print("Test 2: Login as buyer...")
    resp = requests.post(f"{BASE_URL}/auth/login", json={"username": "buyer1", "password": "buyer123"})
    if resp.status_code != 200:
        errors.append(f"Buyer login failed: {resp.text}")
        return errors
    buyer_token = resp.json()["token"]
    print("  ✓ Buyer login successful")
    
    # Test 3: Get categories
    print("Test 3: Get categories...")
    resp = requests.get(f"{BASE_URL}/categories", headers={"Authorization": f"Bearer {admin_token}"})
    if resp.status_code != 200 or len(resp.json()["categories"]) < 5:
        errors.append(f"Get categories failed: {resp.text}")
    else:
        print("  ✓ Categories retrieved")
    
    # Test 4: Get stages
    print("Test 4: Get stages...")
    resp = requests.get(f"{BASE_URL}/stages", headers={"Authorization": f"Bearer {admin_token}"})
    if resp.status_code != 200 or len(resp.json()["stages"]) < 4:
        errors.append(f"Get stages failed: {resp.text}")
    else:
        print("  ✓ Stages retrieved")
    
    # Test 5: Get suppliers
    print("Test 5: Get suppliers...")
    resp = requests.get(f"{BASE_URL}/suppliers", headers={"Authorization": f"Bearer {admin_token}"})
    if resp.status_code != 200:
        errors.append(f"Get suppliers failed: {resp.text}")
    else:
        print("  ✓ Suppliers retrieved")
    
    # Test 6: Get purchase requests
    print("Test 6: Get purchase requests...")
    resp = requests.get(f"{BASE_URL}/purchase-requests", headers={"Authorization": f"Bearer {admin_token}"})
    if resp.status_code != 200:
        errors.append(f"Get purchase requests failed: {resp.text}")
    else:
        print("  ✓ Purchase requests retrieved")
    
    # Test 7: Get RFQs
    print("Test 7: Get RFQs...")
    resp = requests.get(f"{BASE_URL}/rfqs", headers={"Authorization": f"Bearer {admin_token}"})
    if resp.status_code != 200:
        errors.append(f"Get RFQs failed: {resp.text}")
    else:
        print("  ✓ RFQs retrieved")
    
    # Test 8: Get orders
    print("Test 8: Get orders...")
    resp = requests.get(f"{BASE_URL}/orders", headers={"Authorization": f"Bearer {admin_token}"})
    if resp.status_code != 200:
        errors.append(f"Get orders failed: {resp.text}")
    else:
        print("  ✓ Orders retrieved")
    
    # Test 9: Dashboard
    print("Test 9: Get dashboard...")
    resp = requests.get(f"{BASE_URL}/dashboard", headers={"Authorization": f"Bearer {admin_token}"})
    if resp.status_code != 200:
        errors.append(f"Get dashboard failed: {resp.text}")
    else:
        print("  ✓ Dashboard retrieved")
    
    # Test 10: Buyer cannot access users
    print("Test 10: Buyer cannot access users...")
    resp = requests.get(f"{BASE_URL}/users", headers={"Authorization": f"Bearer {buyer_token}"})
    if resp.status_code != 403:
        errors.append(f"Buyer should not access users: {resp.status_code}")
    else:
        print("  ✓ Buyer access denied correctly")
    
    # Test 11: Get users (admin only)
    print("Test 11: Admin can access users...")
    resp = requests.get(f"{BASE_URL}/users", headers={"Authorization": f"Bearer {admin_token}"})
    if resp.status_code != 200:
        errors.append(f"Admin get users failed: {resp.text}")
    else:
        print("  ✓ Admin users access successful")
    
    # Test 12: Supplier score calculation
    print("Test 12: Supplier score calculation...")
    resp = requests.get(f"{BASE_URL}/suppliers/1", headers={"Authorization": f"Bearer {admin_token}"})
    if resp.status_code == 200:
        score = resp.json().get("score", 0)
        if score == 91:  # (95*0.35) + (90*0.35) + (88*0.30) = 91
            print("  ✓ Supplier score calculated correctly")
        else:
            errors.append(f"Supplier score incorrect: {score}")
    else:
        errors.append(f"Get supplier failed: {resp.text}")
    
    print("\n" + "="*50)
    if errors:
        print("TESTS FAILED:")
        for e in errors:
            print(f"  ✗ {e}")
        sys.exit(1)
    else:
        print("ALL TESTS PASSED!")
        sys.exit(0)

if __name__ == "__main__":
    test_all()
