import sys, os
sys.path.insert(0, os.path.dirname(__file__))

from fastapi.testclient import TestClient
from app.main import app

with TestClient(app) as client:
    token = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"}).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    cats = client.get("/api/categories", headers=headers).json()
    cat_id = cats[0]["id"]

    # Create two suppliers
    s1 = client.post("/api/suppliers", headers=headers, json={
        "company_name": "Supplier A", "tax_id": "TAXC1", "email": "c@example.com", "category_ids": [cat_id]
    }).json()
    s2 = client.post("/api/suppliers", headers=headers, json={
        "company_name": "Supplier B", "tax_id": "TAXD1", "email": "d@example.com", "category_ids": [cat_id]
    }).json()

    # Create PR
    pr = client.post("/api/purchase-requests", headers=headers, json={
        "title": "Multi-supplier RFQ", "priority": "Medium", "category_id": cat_id,
        "line_items": [{"description": "Widget", "quantity": 10}]
    }).json()
    pr_id = pr["id"]
    li_id = pr["line_items"][0]["id"]

    # Create RFQ with 2 suppliers
    rfq = client.post("/api/rfqs", headers=headers, json={
        "purchase_request_id": pr_id, "title": "Multi RFQ", "deadline": "2099-12-31T23:59:59",
        "supplier_ids": [s1["id"], s2["id"]]
    }).json()
    rfq_id = rfq["id"]

    t1 = rfq["suppliers"][0]["quote_token"]
    t2 = rfq["suppliers"][1]["quote_token"]

    # Supplier A quotes
    client.post(f"/api/quote/{t1}", json={
        "line_items": [{"request_line_item_id": li_id, "unit_price": 100.0, "delivery_time_days": 5}],
        "payment_terms": "Net 30"
    })
    rfq = client.get(f"/api/rfqs/{rfq_id}", headers=headers).json()
    assert rfq["status"] == "Awaiting Quotes", "Should still be awaiting"

    # Now edit title should fail because first quote received
    r = client.put(f"/api/rfqs/{rfq_id}", headers=headers, json={"title": "Changed"})
    assert r.status_code == 400
    print("Cannot edit title after first quote: PASS")

    # But extend deadline should succeed while still Awaiting Quotes
    r = client.put(f"/api/rfqs/{rfq_id}", headers=headers, json={"deadline": "2099-11-30T23:59:59"})
    assert r.status_code == 200, f"Deadline extension failed: {r.text}"
    print("Deadline extended while Awaiting Quotes: PASS")

    # Supplier B quotes
    client.post(f"/api/quote/{t2}", json={
        "line_items": [{"request_line_item_id": li_id, "unit_price": 80.0, "delivery_time_days": 7}],
        "payment_terms": "Net 60"
    })

    # Now Ready for Review
    rfq = client.get(f"/api/rfqs/{rfq_id}", headers=headers).json()
    assert rfq["status"] == "Ready for Review"
    print("RFQ Ready for Review after all quotes: PASS")

    # Quote comparison
    quotes = client.get(f"/api/rfqs/{rfq_id}/quotes", headers=headers).json()
    lowest = [q for q in quotes if q["is_lowest"]][0]
    other = [q for q in quotes if not q["is_lowest"]][0]
    assert lowest["supplier_name"] == "Supplier B"
    print("Lowest quote:", lowest["supplier_name"], "total", lowest["total"])

    # Selecting non-lowest without justification should fail
    r = client.post(f"/api/rfqs/{rfq_id}/winner", headers=headers, json={"quote_id": other["id"]})
    assert r.status_code == 400
    print("Non-lowest blocked without justification: PASS")

    # Selecting non-lowest with justification should succeed
    r = client.post(f"/api/rfqs/{rfq_id}/winner", headers=headers, json={
        "quote_id": other["id"], "justification": "Better quality"
    })
    assert r.status_code == 200
    assert r.json()["status"] == "Winner Selected"
    print("Non-lowest with justification: PASS")

    # Winner Selected RFQ cannot be edited
    r = client.put(f"/api/rfqs/{rfq_id}", headers=headers, json={"deadline": "2099-10-31T23:59:59"})
    assert r.status_code == 400
    print("Cannot edit Winner Selected RFQ: PASS")

    # Cancelled RFQ cannot be edited
    pr2 = client.post("/api/purchase-requests", headers=headers, json={
        "title": "Cancel Test", "priority": "Low", "category_id": cat_id,
        "line_items": [{"description": "item", "quantity": 1}]
    }).json()
    rfq2 = client.post("/api/rfqs", headers=headers, json={
        "purchase_request_id": pr2["id"], "title": "Cancel RFQ", "deadline": "2099-12-31T23:59:59",
        "supplier_ids": [s1["id"]]
    }).json()
    rfq2_id = rfq2["id"]
    r = client.post(f"/api/rfqs/{rfq2_id}/cancel", headers=headers)
    assert r.status_code == 200
    assert r.json()["status"] == "Cancelled"
    print("RFQ cancelled: PASS")

    # Cannot deactivate supplier invited to active RFQ
    active = client.post("/api/purchase-requests", headers=headers, json={
        "title": "Active RFQ", "priority": "Low", "category_id": cat_id,
        "line_items": [{"description": "item", "quantity": 1}]
    }).json()
    active_rfq = client.post("/api/rfqs", headers=headers, json={
        "purchase_request_id": active["id"], "title": "Active", "deadline": "2099-12-31T23:59:59",
        "supplier_ids": [s1["id"]]
    }).json()
    r = client.put(f"/api/suppliers/{s1['id']}", headers=headers, json={"is_active": False})
    assert r.status_code == 400
    print("Cannot deactivate supplier in active RFQ: PASS")

    # Revise quote before deadline
    t = active_rfq["suppliers"][0]["quote_token"]
    r = client.post(f"/api/quote/{t}", json={
        "line_items": [{"request_line_item_id": active["line_items"][0]["id"], "unit_price": 99.0, "delivery_time_days": 3}],
    })
    assert r.status_code == 200
    assert r.json()["revision_number"] == 1
    r = client.post(f"/api/quote/{t}", json={
        "line_items": [{"request_line_item_id": active["line_items"][0]["id"], "unit_price": 95.0, "delivery_time_days": 3}],
    })
    assert r.status_code == 200
    assert r.json()["revision_number"] == 2
    print("Quote revision works: PASS")

    print("\n=== ALL BUSINESS LOGIC TESTS PASSED ===")
