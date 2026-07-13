import requests
import json

BASE_URL = "http://127.0.0.1:5000"
HEADERS = {"X-User-Name": "TestUser", "Content-Type": "application/json"}

def test_user_identity():
    print("Testing User Identity...")
    # Request without header should fail
    resp = requests.get(f"{BASE_URL}/board")
    assert resp.status_code == 400
    print("OK: Request without identity rejected")

def test_create_cards():
    print("Testing Create Cards...")
    # Valid card
    payload = {"column": "Backlog", "title": "Task 1", "description": "Desc 1", "story_points": 3}
    resp = requests.post(f"{BASE_URL}/cards", json=payload, headers=HEADERS)
    assert resp.status_code == 201
    card_id = resp.json()['id']
    
    # Card with only title
    payload = {"column": "In Progress", "title": "Task 2"}
    resp = requests.post(f"{BASE_URL}/cards", json=payload, headers=HEADERS)
    assert resp.status_code == 201
    card_id_2 = resp.json()['id']

    # Invalid: No title
    payload = {"column": "Backlog", "description": "No title"}
    resp = requests.post(f"{BASE_URL}/cards", json=payload, headers=HEADERS)
    assert resp.status_code == 400
    
    # Invalid: Wrong story points
    payload = {"column": "Backlog", "title": "Task 3", "story_points": 4}
    resp = requests.post(f"{BASE_URL}/cards", json=payload, headers=HEADERS)
    assert resp.status_code == 400
    print("OK: Card creation and validation working")
    return card_id, card_id_2

def test_get_board(card_id, card_id_2):
    print("Testing Get Board...")
    resp = requests.get(f"{BASE_URL}/board", headers=HEADERS)
    assert resp.status_code == 200
    board = resp.json()
    assert "Backlog" in board and "In Progress" in board
    # Verify card 1 is in Backlog
    assert any(c['id'] == card_id for c in board['Backlog'])
    # Verify card 2 is in In Progress
    assert any(c['id'] == card_id_2 for c in board['In Progress'])
    print("OK: Board retrieval working")

def test_edit_and_move_card(card_id):
    print("Testing Edit and Move Card...")
    # Update title and move to Review
    payload = {"title": "Updated Task 1", "status": "Review", "story_points": 5}
    resp = requests.put(f"{BASE_URL}/cards/{card_id}", json=payload, headers=HEADERS)
    assert resp.status_code == 200
    assert resp.json()['title'] == "Updated Task 1"
    assert resp.json()['status'] == "Review"
    
    # Verify board reflects move
    resp = requests.get(f"{BASE_URL}/board", headers=HEADERS)
    board = resp.json()
    assert any(c['id'] == card_id for c in board['Review'])
    assert not any(c['id'] == card_id for c in board['Backlog'])
    print("OK: Card editing and moving working")

def test_delete_card(card_id):
    print("Testing Delete Card...")
    resp = requests.delete(f"{BASE_URL}/cards/{card_id}", headers=HEADERS)
    assert resp.status_code == 204
    
    resp = requests.get(f"{BASE_URL}/board", headers=HEADERS)
    board = resp.json()
    for col in board:
        assert not any(c['id'] == card_id for c in board[col])
    print("OK: Card deletion working")

def test_clear_done():
    print("Testing Clear Done...")
    # Create a card in Done
    payload = {"column": "Done", "title": "Done Task"}
    resp = requests.post(f"{BASE_URL}/cards", json=payload, headers=HEADERS)
    card_id = resp.json()['id']
    
    # Create a card in Backlog
    payload = {"column": "Backlog", "title": "Backlog Task"}
    resp = requests.post(f"{BASE_URL}/cards", json=payload, headers=HEADERS)
    backlog_id = resp.json()['id']
    
    # Clear Done
    resp = requests.delete(f"{BASE_URL}/board/done", headers=HEADERS)
    assert resp.status_code == 204
    
    # Verify
    resp = requests.get(f"{BASE_URL}/board", headers=HEADERS)
    board = resp.json()
    assert len(board['Done']) == 0
    assert any(c['id'] == backlog_id for c in board['Backlog'])
    print("OK: Clear Done working")

if __name__ == "__main__":
    try:
        test_user_identity()
        c1, c2 = test_create_cards()
        test_get_board(c1, c2)
        test_edit_and_move_card(c1)
        test_delete_card(c2) # deleting c2
        test_clear_done()
        print("\nALL TESTS PASSED!")
    except Exception as e:
        print(f"\nTEST FAILED: {e}")
        exit(1)
