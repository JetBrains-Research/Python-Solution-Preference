import sys, os
sys.path.insert(0, os.path.dirname(__file__))

from fastapi.testclient import TestClient
from app.main import app

with TestClient(app) as client:
    # Auth
    r = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
    assert r.status_code == 200, f"Login failed: {r.text}"
    token = r.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Categories
    r = client.get("/api/categories", headers=headers)
    assert r.status_code == 200, f"Get categories failed: {r.text}"
    cats = r.json()
    print("Categories:", [c["name"] for c in cats])

    # Create supplier
    r = client.post("/api/suppliers", headers=headers, json={
        "company_name": "Acme Corp",
        "tax_id": "TAX123",
        "email": "acme@example.com",
        "category_ids": [cats[0]["id"]]
    })
    assert r.status_code == 201, f"Create supplier failed: {r.text}"
    supplier_id = r.json()["id"]
    print("Supplier created:", r.json()["company_name"])

    # Search suppliers
    r = client.get("/api/suppliers?query=Acme", headers=headers)
    assert r.status_code == 200

    # Create purchase request
    r = client.post("/api/purchase-requests", headers=headers, json={
        "title": "Office Chairs",
        "priority": "Medium",
        "category_id": cats[0]["id"],
        "line_items": [{"description": "Ergonomic chair", "quantity": 5}]
    })
    assert r.status_code == 201, f"Create PR failed: {r.text}"
    pr_id = r.json()["id"]
    print("PR created:", r.json()["title"], "stage:", r.json()["current_stage_name"])

    # Create RFQ
    r = client.post("/api/rfqs", headers=headers, json={
        "purchase_request_id": pr_id,
        "title": "RFQ for chairs",
        "deadline": "2099-12-31T23:59:59",
        "supplier_ids": [supplier_id]
    })
    assert r.status_code == 201, f"Create RFQ failed: {r.text}"
    rfq_id = r.json()["id"]
    print("RFQ created:", r.json()["title"], "status:", r.json()["status"])

    # Check PR moved to In Review
    r = client.get(f"/api/purchase-requests/{pr_id}", headers=headers)
    assert r.status_code == 200
    print("PR stage after RFQ:", r.json()["current_stage_name"])

    # Get quote token
    r = client.get(f"/api/rfqs/{rfq_id}", headers=headers)
    assert r.status_code == 200
    token = r.json()["suppliers"][0]["quote_token"]
    print("Quote token:", token[:10] + "...")

    # Supplier submits quote
    r = client.post(f"/api/quote/{token}", json={
        "line_items": [{"request_line_item_id": r.json()["purchase_request_id"], "unit_price": 100.0, "delivery_time_days": 10}],
        "payment_terms": "Net 30",
        "notes": "First quote"
    })
    assert r.status_code == 200, f"Quote submit failed: {r.text}"
    print("Quote submitted:", r.json()["revision_number"])

    # RFQ should now be Ready for Review
    r = client.get(f"/api/rfqs/{rfq_id}", headers=headers)
    assert r.status_code == 200
    print("RFQ status after quote:", r.json()["status"])

    # Get quotes for comparison
    r = client.get(f"/api/rfqs/{rfq_id}/quotes", headers=headers)
    assert r.status_code == 200
    quotes = r.json()
    print("Quotes count:", len(quotes), "lowest:", quotes[0]["is_lowest"])

    # Select winner
    quote_id = quotes[0]["id"]
    r = client.post(f"/api/rfqs/{rfq_id}/winner", headers=headers, json={"quote_id": quote_id})
    assert r.status_code == 200, f"Select winner failed: {r.text}"
    print("RFQ after winner:", r.json()["status"])

    # Check PR moved to Ordered
    r = client.get(f"/api/purchase-requests/{pr_id}", headers=headers)
    assert r.status_code == 200
    print("PR stage after winner:", r.json()["current_stage_name"])

    # Check orders
    r = client.get("/api/orders", headers=headers)
    assert r.status_code == 200
    orders = r.json()
    print("Orders count:", len(orders), "order number:", orders[0]["order_number"])

    # Progress order status
    order_id = orders[0]["id"]
    for status in ["Confirmed", "Shipped", "Delivered"]:
        r = client.put(f"/api/orders/{order_id}/status", headers=headers, json={"status": status})
        assert r.status_code == 200, f"Status update to {status} failed: {r.text}"
        print("Order status:", r.json()["current_status"])

    # Rate supplier
    r = client.post(f"/api/orders/{order_id}/rate", headers=headers, json={"punctuality": 90, "quality": 85, "reliability": 95})
    assert r.status_code == 200, f"Rate failed: {r.text}"
    print("Supplier score:", r.json()["overall_score"])

    # Dashboard
    r = client.get("/api/dashboard", headers=headers)
    assert r.status_code == 200
    print("Dashboard keys:", list(r.json().keys()))

    # Clone PR
    r = client.post(f"/api/purchase-requests/{pr_id}/clone", headers=headers)
    assert r.status_code == 200, f"Clone failed: {r.text}"
    print("Cloned PR title:", r.json()["title"], "stage:", r.json()["current_stage_name"])

    # Reorder
    r = client.post(f"/api/orders/{order_id}/reorder", headers=headers)
    assert r.status_code == 200, f"Reorder failed: {r.text}"
    print("Reordered PR title:", r.json()["title"])

    # Stages
    r = client.get("/api/stages", headers=headers)
    assert r.status_code == 200
    print("Stages:", [s["name"] for s in r.json()])

    # Stage history
    r = client.get(f"/api/purchase-requests/{pr_id}/history", headers=headers)
    assert r.status_code == 200
    print("Stage history count:", len(r.json()))

    # Cancel RFQ test
    r = client.post("/api/purchase-requests", headers=headers, json={
        "title": "Test Cancel",
        "priority": "Low",
        "category_id": cats[0]["id"],
        "line_items": [{"description": "Test item", "quantity": 1}]
    })
    new_pr_id = r.json()["id"]

    r = client.post("/api/rfqs", headers=headers, json={
        "purchase_request_id": new_pr_id,
        "title": "Cancel RFQ",
        "deadline": "2099-12-31T23:59:59",
        "supplier_ids": [supplier_id]
    })
    cancel_rfq_id = r.json()["id"]

    r = client.post(f"/api/rfqs/{cancel_rfq_id}/cancel", headers=headers)
    assert r.status_code == 200, f"Cancel failed: {r.text}"
    print("RFQ after cancel:", r.json()["status"])

    r = client.get(f"/api/purchase-requests/{new_pr_id}", headers=headers)
    assert r.status_code == 200
    print("PR stage after cancel:", r.json()["current_stage_name"])

    # Delete PR with no RFQ
    r = client.post("/api/purchase-requests", headers=headers, json={
        "title": "Delete me",
        "priority": "Low",
        "category_id": cats[0]["id"],
        "line_items": [{"description": "Delete item", "quantity": 1}]
    })
    del_pr_id = r.json()["id"]

    r = client.delete(f"/api/purchase-requests/{del_pr_id}", headers=headers)
    assert r.status_code == 204, f"Delete PR failed: {r.text}"
    print("PR deleted successfully")

    print("\n=== ALL TESTS PASSED ===")
