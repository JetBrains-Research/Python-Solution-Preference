with open('test_game.py', 'r') as f:
    lines = f.readlines()

# Find the test_go_passing function and replace it
new_lines = []
in_go_func = False
skip_until_pass = False
go_func_lines = []
i = 0
while i < len(lines):
    line = lines[i]
    if 'def test_go_passing():' in line:
        # Start collecting but will replace
        go_func_lines.append(line)
        # Find the end of the function (next def)
        j = i + 1
        while j < len(lines) and not lines[j].startswith('def '):
            go_func_lines.append(lines[j])
            j += 1
        # Replace with new function
        new_func = '''def test_go_passing():
    print("=== Test: Passing GO ===")
    # Dice: 5,1,5,1,1 (GoRunner gets to pos 5, then rolls 5 to land on GO)
    restart_with_config("5,1,5,1,1", default_board(), default_props())
    
    resp = post_json(f"{BASE_URL}/game/new", {"players": ["GoRunner", "GoWatcher"]})
    
    # GoRunner rolls 5 -> from pos 0 to pos 5
    resp = requests.post(f"{BASE_URL}/game/roll")
    data = resp.json()
    print(f"GoRunner roll 5: {data['message']}")
    gorunner = [p for p in data["state"]["players"] if p["name"] == "GoRunner"][0]
    assert gorunner["position"] == 5
    if data["state"]["turn_pending_action"] == "buy_or_pass":
        resp = requests.post(f"{BASE_URL}/game/pass")
        data = resp.json()
    
    # GoWatcher rolls 1 -> from pos 0 to pos 1
    resp = requests.post(f"{BASE_URL}/game/roll")
    data = resp.json()
    print(f"GoWatcher roll 1: {data['message']}")
    if data["state"]["turn_pending_action"] == "buy_or_pass":
        resp = requests.post(f"{BASE_URL}/game/pass")
        data = resp.json()
    
    # GoRunner rolls 5 -> from pos 5 to pos 0 (lands exactly on GO, passes GO since it wraps)
    resp = requests.post(f"{BASE_URL}/game/roll")
    data = resp.json()
    print(f"GoRunner roll 5 from pos 5 to GO: {data['message']}")
    gorunner = [p for p in data["state"]["players"] if p["name"] == "GoRunner"][0]
    assert gorunner["position"] == 0
    # Started 500, no expenses, passed GO getting +200 = 700
    assert gorunner["cash"] == 700
    print("PASSED\\n")
'''
        new_lines.extend(new_func.split('\n'))
        i = j
        continue
    new_lines.append(line)
    i += 1

with open('test_game.py', 'w') as f:
    f.write('\n'.join(new_lines) + '\n')

print("Fixed")
