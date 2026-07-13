with open('test_game.py', 'r') as f:
    content = f.read()

# Fix the jail test to handle pending action
old_jail = '''def test_jail():
    print("=== Test: Jail Mechanics ===")
    restart_with_config("4,1,1,1,1", default_board(), default_props())
    
    resp = post_json(f"{BASE_URL}/game/new", {"players": ["P1", "P2"]})
    assert resp.status_code == 200
    
    resp = requests.post(f"{BASE_URL}/game/roll")
    data = resp.json()
    print(f"P1 roll: {data['message']}")
    p1 = [p for p in data["state"]["players"] if p["name"] == "P1"][0]
    assert p1["position"] == 4
    assert p1["skip_next_turn"] == True
    
    resp = requests.post(f"{BASE_URL}/game/roll")
    data = resp.json()
    print(f"P2 roll: {data['message']}")
    
    resp = requests.post(f"{BASE_URL}/game/roll")
    data = resp.json()
    print(f"P1 second turn: {data['message']}")
    assert "skipped" in data['message'].lower()
    print("PASSED\\n")'''

new_jail = '''def test_jail():
    print("=== Test: Jail Mechanics ===")
    restart_with_config("4,1,1,1,1", default_board(), default_props())
    
    resp = post_json(f"{BASE_URL}/game/new", {"players": ["P1", "P2"]})
    assert resp.status_code == 200
    
    resp = requests.post(f"{BASE_URL}/game/roll")
    data = resp.json()
    print(f"P1 roll: {data['message']}")
    p1 = [p for p in data["state"]["players"] if p["name"] == "P1"][0]
    assert p1["position"] == 4
    assert p1["skip_next_turn"] == True
    
    resp = requests.post(f"{BASE_URL}/game/roll")
    data = resp.json()
    print(f"P2 roll: {data['message']}")
    # P2 may have landed on a property, resolve it
    if data["state"]["turn_pending_action"] == "buy_or_pass":
        resp = requests.post(f"{BASE_URL}/game/pass")
        data = resp.json()
    
    resp = requests.post(f"{BASE_URL}/game/roll")
    data = resp.json()
    print(f"P1 second turn: {data['message']}")
    assert "skipped" in data['message'].lower()
    print("PASSED\\n")'''

content = content.replace(old_jail, new_jail)

with open('test_game.py', 'w') as f:
    f.write(content)

print("Fixed")
