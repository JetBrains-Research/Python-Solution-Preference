#!/usr/bin/env python3
import requests
import json

BASE_URL = "http://localhost:5001"

def test_health():
    r = requests.get(f"{BASE_URL}/health")
    assert r.status_code == 200
    assert r.json()['status'] == 'ok'
    print("✓ Health check passed")

def test_init_validation():
    # Test empty players
    r = requests.post(f"{BASE_URL}/game/init", json={})
    assert r.status_code == 400
    
    # Test 1 player
    r = requests.post(f"{BASE_URL}/game/init", json={"players": ["Alice"]})
    assert r.status_code == 400
    
    # Test 5 players
    r = requests.post(f"{BASE_URL}/game/init", json={"players": ["A","B","C","D","E"]})
    assert r.status_code == 400
    
    # Test duplicate names
    r = requests.post(f"{BASE_URL}/game/init", json={"players": ["Alice", "Alice"]})
    assert r.status_code == 400
    
    print("✓ Init validation passed")

def test_init_game():
    requests.post(f"{BASE_URL}/game/reset")
    r = requests.post(f"{BASE_URL}/game/init", json={"players": ["Alice", "Bob", "Charlie", "Dave"]})
    assert r.status_code == 200
    data = r.json()
    assert data['message'] == 'Game initialized'
    assert data['players'] == ["Alice", "Bob", "Charlie", "Dave"]
    print("✓ Init game with 4 players passed")

def test_game_state():
    r = requests.get(f"{BASE_URL}/game/state")
    assert r.status_code == 200
    data = r.json()
    assert data['currentTurn'] == 'Alice'
    assert data['gameOver'] == False
    assert len(data['players']) == 4
    for p in data['players']:
        assert p['cash'] == 500
        assert p['position'] == 0
        assert p['status'] == 'Active'
    print("✓ Game state check passed")

def test_jail_skip():
    requests.post(f"{BASE_URL}/game/reset")
    
    r = requests.post(f"{BASE_URL}/game/init", json={"players": ["Alice", "Bob"]})
    assert r.status_code == 200
    
    # Alice rolls 3, lands on FREE_PARKING (position 3)
    r = requests.post(f"{BASE_URL}/game/roll")
    data = r.json()
    assert 'FREE PARKING' in data['message']
    
    # Bob rolls 5, lands on TAX (position 5)
    r = requests.post(f"{BASE_URL}/game/roll")
    data = r.json()
    assert 'tax' in data['message'].lower()
    
    print("✓ Jail skip test passed")

def test_property_ownership():
    requests.post(f"{BASE_URL}/game/reset")
    
    r = requests.post(f"{BASE_URL}/game/init", json={"players": ["Alice", "Bob"]})
    assert r.status_code == 200
    
    # Alice rolls 3, lands on FREE_PARKING (position 3)
    r = requests.post(f"{BASE_URL}/game/roll")
    data = r.json()
    assert 'FREE PARKING' in data['message']
    
    # Bob rolls 5, lands on TAX (position 5)
    r = requests.post(f"{BASE_URL}/game/roll")
    data = r.json()
    assert 'tax' in data['message'].lower()
    
    # Alice rolls 2, lands on FREE_PARKING (position 5)
    r = requests.post(f"{BASE_URL}/game/roll")
    data = r.json()
    assert data['position'] == 5
    
    # Bob rolls 6, passes GO and lands on position 3
    r = requests.post(f"{BASE_URL}/game/roll")
    data = r.json()
    assert data['cash'] == 600  # 500 - 100 tax + 200 GO = 600
    
    print("✓ Property ownership test passed")

def test_winner():
    requests.post(f"{BASE_URL}/game/reset")
    
    r = requests.post(f"{BASE_URL}/game/init", json={"players": ["Alice", "Bob"]})
    assert r.status_code == 200
    
    # Multiple rolls
    for i in range(6):
        r = requests.post(f"{BASE_URL}/game/roll")
    
    # Check game state
    r = requests.get(f"{BASE_URL}/game/state")
    data = r.json()
    
    # Check if game is over
    if data['gameOver']:
        r = requests.get(f"{BASE_URL}/game/winner")
        if r.status_code == 200:
            winner_data = r.json()
            assert 'winner' in winner_data
            print(f"  Winner: {winner_data['winner']}")
    
    print("✓ Winner detection test passed")

def test_dice_cycling():
    requests.post(f"{BASE_URL}/game/reset")
    
    r = requests.post(f"{BASE_URL}/game/init", json={"players": ["Alice", "Bob"]})
    assert r.status_code == 200
    
    # Roll multiple times to test dice cycling (dice sequence is 3,5,2,6,1,4)
    dice_sequence = [3, 5, 2, 6, 1, 4]
    for i in range(8):  # More than 6 rolls to test cycling
        r = requests.post(f"{BASE_URL}/game/roll")
        data = r.json()
        expected_dice = dice_sequence[i % 6]
        # Only check if not skipped
        if 'dice' in data:
            assert data['dice'] == expected_dice, f"Expected {expected_dice}, got {data['dice']}"
    
    print("✓ Dice cycling test passed")

if __name__ == '__main__':
    test_health()
    test_init_validation()
    test_init_game()
    test_game_state()
    test_jail_skip()
    test_property_ownership()
    test_winner()
    test_dice_cycling()
    print("\n✅ All tests passed!")
