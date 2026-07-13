import requests
import json

BASE_URL = 'http://127.0.0.1:8080'

def test_chat():
    session = requests.Session()

    # 1. Test Login
    print("Testing Login...")
    resp = session.post(f'{BASE_URL}/login', json={'username': 'alice', 'password': 'password123'})
    assert resp.status_code == 200, "Login failed"
    print("Login successful")

    # 2. Test Sending message to #general
    print("Testing #general message...")
    resp = session.post(f'{BASE_URL}/messages', json={'channel_id': 'general', 'text': 'Hello everyone!'})
    assert resp.status_code == 201, "Failed to send to #general"
    print("Sent to #general")

    # 3. Test User Search for Bob
    print("Testing User Search...")
    resp = session.get(f'{BASE_URL}/users/search', params={'q': 'Bob'})
    users = resp.json()
    assert len(users) > 0, "Bob not found"
    bob_username = users[0]['username']
    print(f"Found Bob: {bob_username}")

    # 4. Test Starting a DM with Bob
    # We need to determine the DM ID. The app uses 'dm_' + sorted usernames.
    dm_id = 'dm_' + '_'.join(sorted(['alice', bob_username]))
    print(f"Sending DM to Bob (Channel: {dm_id})...")
    resp = session.post(f'{BASE_URL}/messages', json={'channel_id': dm_id, 'text': 'Hi Bob, this is a secret!'})
    assert resp.status_code == 201, "Failed to send DM"
    print("Sent DM")

    # 5. Test listing channels
    print("Testing channel list...")
    resp = session.get(f'{BASE_URL}/channels')
    channels = resp.json()
    assert any(c['id'] == 'general' for c in channels), "General channel missing"
    assert any(c['id'] == dm_id for c in channels), "DM channel missing"
    print("Channels listed correctly")

    # 6. Test global search
    print("Testing global search...")
    resp = session.get(f'{BASE_URL}/search', params={'q': 'secret'})
    results = resp.json()
    assert len(results) == 1, "Search failed to find secret message"
    assert results[0]['channel_id'] == dm_id, "Search result in wrong channel"
    print("Global search successful")

    # 7. Test whitespace-only message
    print("Testing whitespace-only message...")
    resp = session.post(f'{BASE_URL}/messages', json={'channel_id': 'general', 'text': '   '})
    assert resp.status_code == 400, "Whitespace message should be rejected"
    print("Whitespace rejected")

    # 8. Test unauthorized access to other DM
    # Create a DM between Bob and Charlie
    other_dm_id = 'dm_' + '_'.join(sorted(['bob', 'charlie']))
    print(f"Testing unauthorized access to {other_dm_id}...")
    resp = session.get(f'{BASE_URL}/messages/{other_dm_id}')
    assert resp.status_code == 403, "Alice should not access Bob and Charlie's DM"
    print("Unauthorized access rejected")

    print("\nALL TESTS PASSED")

if __name__ == '__main__':
    test_chat()
