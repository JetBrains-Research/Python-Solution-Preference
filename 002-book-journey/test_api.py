import pytest
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

def test_auth():
    # Valid login
    response = client.post("/login", json={"username": "alice123"})
    assert response.status_code == 200
    
    # Invalid login (too short)
    response = client.post("/login", json={"username": "al"})
    assert response.status_code == 400
    
    # Invalid login (special chars)
    response = client.post("/login", json={"username": "alice!"})
    assert response.status_code == 400

def test_browse_books():
    # All books
    response = client.get("/books")
    assert response.status_code == 200
    assert len(response.json()) == 3
    
    # Search filter
    response = client.get("/books?q=Orwell")
    assert response.status_code == 200
    assert len(response.json()) == 1
    assert response.json()[0]["title"] == "1984"

def test_journey_and_checkpoints():
    # Login users
    client.post("/login", json={"username": "alice"})
    client.post("/login", json={"username": "bob"})
    
    # Alice adds checkpoint to book 1
    resp = client.post("/books/1/checkpoints", 
                       headers={"X-Username": "alice"}, 
                       json={"chapter": 1, "note": "Great start!", "mood": "Excited"})
    assert resp.status_code == 200
    
    # Bob adds checkpoint to book 1 (chapter 2)
    resp = client.post("/books/1/checkpoints", 
                       headers={"X-Username": "bob"}, 
                       json={"chapter": 2, "note": "Interesting", "mood": "Curious"})
    assert resp.status_code == 200

    # Alice's journey
    resp = client.get("/my-journey", headers={"X-Username": "alice"})
    assert resp.status_code == 200
    assert len(resp.json()) == 1
    assert resp.json()[0]["title"] == "The Great Gatsby"

    # Book details for book 1
    resp = client.get("/books/1", headers={"X-Username": "alice"})
    data = resp.json()
    assert data["details"]["title"] == "The Great Gatsby"
    assert data["your_journey"]["count"] == 1
    assert len(data["reader_checkpoints"]) == 2
    assert data["reader_checkpoints"][0]["username"] == "alice"
    assert data["reader_checkpoints"][0]["is_mine"] is True
    assert data["reader_checkpoints"][1]["username"] == "bob"
    assert data["reader_checkpoints"][1]["is_mine"] is False

def test_checkpoint_validation():
    client.post("/login", json={"username": "val_user"})
    
    # Invalid chapter (too high)
    resp = client.post("/books/1/checkpoints", 
                       headers={"X-Username": "val_user"}, 
                       json={"chapter": 100, "note": "Valid note"})
    assert resp.status_code == 400
    
    # Invalid note (too long)
    resp = client.post("/books/1/checkpoints", 
                       headers={"X-Username": "val_user"}, 
                       json={"chapter": 1, "note": "a" * 281})
    assert resp.status_code == 400
    
    # Invalid note (empty/whitespace)
    resp = client.post("/books/1/checkpoints", 
                       headers={"X-Username": "val_user"}, 
                       json={"chapter": 1, "note": "   "})
    assert resp.status_code == 400
    
    # Invalid mood
    resp = client.post("/books/1/checkpoints", 
                       headers={"X-Username": "val_user"}, 
                       json={"chapter": 1, "note": "Valid", "mood": "Angry"})
    assert resp.status_code == 400
