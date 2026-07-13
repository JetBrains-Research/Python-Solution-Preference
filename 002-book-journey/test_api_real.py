import time
import threading
import httpx
import pytest
import uvicorn
from main import app

def run_server():
    uvicorn.run(app, host="127.0.0.1", port=8000, log_level="error")

# Start server in background
server_thread = threading.Thread(target=run_server, daemon=True)
server_thread.start()
time.sleep(2)  # Wait for server to start

BASE_URL = "http://127.0.0.1:8000"

def test_auth():
    with httpx.Client() as client:
        # Valid login
        response = client.post(f"{BASE_URL}/login", json={"username": "alice123"})
        assert response.status_code == 200
        
        # Invalid login (too short)
        response = client.post(f"{BASE_URL}/login", json={"username": "al"})
        assert response.status_code == 400
        
        # Invalid login (special chars)
        response = client.post(f"{BASE_URL}/login", json={"username": "alice!"})
        assert response.status_code == 400

def test_browse_books():
    with httpx.Client() as client:
        # All books
        response = client.get(f"{BASE_URL}/books")
        assert response.status_code == 200
        assert len(response.json()) == 3
        
        # Search filter
        response = client.get(f"{BASE_URL}/books?q=Orwell")
        assert response.status_code == 200
        assert len(response.json()) == 1
        assert response.json()[0]["title"] == "1984"

def test_journey_and_checkpoints():
    with httpx.Client() as client:
        # Login users
        client.post(f"{BASE_URL}/login", json={"username": "alice"})
        client.post(f"{BASE_URL}/login", json={"username": "bob"})
        
        # Alice adds checkpoint to book 1
        resp = client.post(f"{BASE_URL}/books/1/checkpoints", 
                           headers={"X-Username": "alice"}, 
                           json={"chapter": 1, "note": "Great start!", "mood": "Excited"})
        assert resp.status_code == 200
        
        # Bob adds checkpoint to book 1 (chapter 2)
        resp = client.post(f"{BASE_URL}/books/1/checkpoints", 
                           headers={"X-Username": "bob"}, 
                           json={"chapter": 2, "note": "Interesting", "mood": "Curious"})
        assert resp.status_code == 200

        # Alice's journey
        resp = client.get(f"{BASE_URL}/my-journey", headers={"X-Username": "alice"})
        assert resp.status_code == 200
        assert len(resp.json()) == 1
        assert resp.json()[0]["title"] == "The Great Gatsby"

        # Book details for book 1
        resp = client.get(f"{BASE_URL}/books/1", headers={"X-Username": "alice"})
        data = resp.json()
        assert data["details"]["title"] == "The Great Gatsby"
        assert data["your_journey"]["count"] == 1
        assert len(data["reader_checkpoints"]) == 2
        assert data["reader_checkpoints"][0]["username"] == "alice"
        assert data["reader_checkpoints"][0]["is_mine"] is True
        assert data["reader_checkpoints"][1]["username"] == "bob"
        assert data["reader_checkpoints"][1]["is_mine"] is False

def test_checkpoint_validation():
    with httpx.Client() as client:
        client.post(f"{BASE_URL}/login", json={"username": "val_user"})
        
        # Invalid chapter (too high)
        resp = client.post(f"{BASE_URL}/books/1/checkpoints", 
                           headers={"X-Username": "val_user"}, 
                           json={"chapter": 100, "note": "Valid note"})
        assert resp.status_code == 400
        
        # Invalid note (too long)
        resp = client.post(f"{BASE_URL}/books/1/checkpoints", 
                           headers={"X-Username": "val_user"}, 
                           json={"chapter": 1, "note": "a" * 281})
        assert resp.status_code == 400
        
        # Invalid note (empty/whitespace)
        resp = client.post(f"{BASE_URL}/books/1/checkpoints", 
                           headers={"X-Username": "val_user"}, 
                           json={"chapter": 1, "note": "   "})
        assert resp.status_code == 400
        
        # Invalid mood
        resp = client.post(f"{BASE_URL}/books/1/checkpoints", 
                           headers={"X-Username": "val_user"}, 
                           json={"chapter": 1, "note": "Valid", "mood": "Angry"})
        assert resp.status_code == 400

if __name__ == "__main__":
    import pytest
    import sys
    sys.exit(pytest.main([__file__]))
