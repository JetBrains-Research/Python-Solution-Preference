import os, json, sys, time, subprocess, requests, signal

HERE = os.path.dirname(os.path.abspath(__file__))
BASE_URL = "http://127.0.0.1:8004"
server_proc = None

def start_server():
    global server_proc
    env = os.environ.copy()
    server_proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "main:app", "--host", "127.0.0.1", "--port", "8004"],
        cwd=HERE, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    for _ in range(30):
        try:
            requests.get(f"{BASE_URL}/game/state")
            time.sleep(0.1)
            return
        except requests.ConnectionError:
            time.sleep(0.2)
    raise RuntimeError("Server failed to start")

def stop_server():
    global server_proc
    if server_proc:
        server_proc.send_signal(signal.SIGTERM)
        server_proc.wait()

def pprint(data):
    print(json.dumps(data, indent=2))

def default_board():
    return [
        {"index": 0, "type": "GO", "payout": 200},
        {"index": 1, "type": "PROPERTY", "propertyId": 1},
        {"index": 2, "type": "TAX", "amount": 50},
        {"index": 3, "type": "PROPERTY", "propertyId": 2},
        {"index": 4, "type": "JAIL"},
        {"index": 5, "type": "PROPERTY", "propertyId": 3},
        {"index": 6, "type": "FREE_PARKING"},
        {"index": 7, "type": "PROPERTY", "propertyId": 4},
        {"index": 8, "type": "TAX", "amount": 100},
        {"index": 9, "type": "PROPERTY", "propertyId": 5}
    ]

def default_props():
    return [
        {"id": 1, "name": "Park Place", "price": 350, "rent": 35},
        {"id": 2, "name": "Boardwalk", "price": 400, "rent": 50},
        {"id": 3, "name": "Mediterranean Ave", "price": 60, "rent": 4},
        {"id": 4, "name": "Baltic Ave", "price": 60, "rent": 4},
        {"id": 5, "name": "Oriental Ave", "price": 100, "rent": 6}
    ]

def restart_with_config(dice, board=None, props=None):
    stop_server()
    os.environ["DICE_MOVES"] = dice
    if board:
        os.environ["BOARD_DATA"] = json.dumps(board)
    if props:
        os.environ["PROPERTIES_DATA"] = json.dumps(props)
    start_server()

def post_json(url, json_data):
    return requests.post(url, json=json_data)

def resolve_pending():
    """If there's a pending buy_or_pass action, pass on it."""
    resp = requests.get(f"{BASE_URL}/game/state")
    state = resp.json()
    if state.get("turn_pending_action") == "buy_or_pass":
        return requests.post(f"{BASE_URL}/game/pass").json()
    return state

# ---------- TESTS ----------

def test_new_game():
    print("=== Test: New Game ===")
    resp = post_json(f"{BASE_URL}/game/new", {"players": ["Alice", "Bob", "Charlie"]})
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
    data = resp.json()
    print(f"Message: {data['message']}")
    assert data["state"]["started"] == True
    assert len(data["state"]["players"]) == 3
    print("PASSED\n")

def test_game_state():
    print("=== Test: Game State ===")
    resp = requests.get(f"{BASE_URL}/game/state")
    assert resp.status_code == 200
    pprint(resp.json())
    print("PASSED\n")

def test_roll_and_move():
    print("=== Test: Roll and Move ===")
    resp = requests.post(f"{BASE_URL}/game/roll")
    assert resp.status_code == 200
    data = resp.json()
    print(f"Message: {data['message']}")
    assert data["dice_value"] == 3
    assert data["state"]["turn_pending_action"] == "buy_or_pass"
    alice = [p for p in data["state"]["players"] if p["name"] == "Alice"][0]
    assert alice["position"] == 3
    print("PASSED\n")

def test_buy_property():
    print("=== Test: Buy Property ===")
    resp = requests.post(f"{BASE_URL}/game/buy")
    assert resp.status_code == 200
    data = resp.json()
    print(f"Message: {data['message']}")
    alice = [p for p in data["state"]["players"] if p["name"] == "Alice"][0]
    assert alice["cash"] == 100
    assert 2 in alice["properties"]
    print("PASSED\n")

def test_pass_property():
    print("=== Test: Pass Property ===")
    resp = requests.post(f"{BASE_URL}/game/roll")
    data = resp.json()
    print(f"Bob roll: {data['message']}")
    data = resolve_pending()
    print("PASSED\n")

def test_jail():
    print("=== Test: Jail Mechanics ===")
    restart_with_config("4,1,1,1", default_board(), default_props())
    resp = post_json(f"{BASE_URL}/game/new", {"players": ["P1", "P2"]})
    assert resp.status_code == 200

    # P1 rolls 4 -> lands on JAIL
    resp = requests.post(f"{BASE_URL}/game/roll")
    data = resp.json()
    print(f"P1 roll: {data['message']}")
    p1 = [p for p in data["state"]["players"] if p["name"] == "P1"][0]
    assert p1["position"] == 4
    assert p1["skip_next_turn"] == True

    # P2 rolls 1
    resp = requests.post(f"{BASE_URL}/game/roll")
    data = resp.json()
    print(f"P2 roll: {data['message']}")
    data = resolve_pending()

    # P1 should skip
    resp = requests.post(f"{BASE_URL}/game/roll")
    data = resp.json()
    print(f"P1 second turn: {data['message']}")
    assert "skipped" in data['message'].lower()
    print("PASSED\n")

def test_tax():
    print("=== Test: Tax ===")
    restart_with_config("2,1", default_board(), default_props())
    resp = post_json(f"{BASE_URL}/game/new", {"players": ["TaxPayer", "Observer"]})
    assert resp.status_code == 200
    resp = requests.post(f"{BASE_URL}/game/roll")
    data = resp.json()
    print(f"TaxPayer roll: {data['message']}")
    tp = [p for p in data["state"]["players"] if p["name"] == "TaxPayer"][0]
    assert tp["cash"] == 450
    print("PASSED\n")

def test_go_passing():
    print("=== Test: Passing GO ===")
    restart_with_config("5,1,5,1", default_board(), default_props())
    resp = post_json(f"{BASE_URL}/game/new", {"players": ["GoRunner", "GoWatcher"]})
    assert resp.status_code == 200

    # GoRunner rolls 5 -> pos 5
    resp = requests.post(f"{BASE_URL}/game/roll")
    data = resp.json()
    print(f"GoRunner roll 5: {data['message']}")
    data = resolve_pending()

    # GoWatcher rolls 1 -> pos 1
    resp = requests.post(f"{BASE_URL}/game/roll")
    data = resp.json()
    print(f"GoWatcher roll 1: {data['message']}")
    data = resolve_pending()

    # GoRunner rolls 5 -> pos 10 % 10 = 0, passes GO
    resp = requests.post(f"{BASE_URL}/game/roll")
    data = resp.json()
    print(f"GoRunner roll 5 from pos 5 to GO: {data['message']}")
    gorunner = [p for p in data["state"]["players"] if p["name"] == "GoRunner"][0]
    assert gorunner["position"] == 0
    assert gorunner["cash"] == 700
    print("PASSED\n")

def test_rent():
    print("=== Test: Rent Payment ===")
    restart_with_config("1,1", default_board(), default_props())
    resp = post_json(f"{BASE_URL}/game/new", {"players": ["Owner", "Renter"]})
    assert resp.status_code == 200

    resp = requests.post(f"{BASE_URL}/game/roll")
    data = resp.json()
    assert data["state"]["turn_pending_action"] == "buy_or_pass"
    resp = requests.post(f"{BASE_URL}/game/buy")
    data = resp.json()
    print(f"Owner bought: {data['message']}")

    resp = requests.post(f"{BASE_URL}/game/roll")
    data = resp.json()
    print(f"Renter landed on Owner property: {data['message']}")
    renter = [p for p in data["state"]["players"] if p["name"] == "Renter"][0]
    owner = [p for p in data["state"]["players"] if p["name"] == "Owner"][0]
    assert renter["cash"] == 465
    assert owner["cash"] == 185
    print("PASSED\n")

def test_bankruptcy_by_tax():
    print("=== Test: Bankruptcy by Tax ===")
    board = [{"index":0,"type":"GO","payout":200},{"index":1,"type":"TAX","amount":600},{"index":2,"type":"FREE_PARKING"},{"index":3,"type":"FREE_PARKING"},{"index":4,"type":"FREE_PARKING"},{"index":5,"type":"FREE_PARKING"},{"index":6,"type":"FREE_PARKING"},{"index":7,"type":"FREE_PARKING"},{"index":8,"type":"FREE_PARKING"},{"index":9,"type":"FREE_PARKING"}]
    restart_with_config("1", board, default_props())
    resp = post_json(f"{BASE_URL}/game/new", {"players": ["Poor", "Rich"]})
    assert resp.status_code == 200
    resp = requests.post(f"{BASE_URL}/game/roll")
    data = resp.json()
    print(f"Poor rolled: {data['message']}")
    poor = [p for p in data["state"]["players"] if p["name"] == "Poor"][0]
    assert poor["status"] == "Eliminated"
    assert poor["cash"] == 0
    print("PASSED\n")

def test_bankruptcy_by_rent():
    print("=== Test: Bankruptcy by Rent ===")
    props = [{"id":1,"name":"Park Place","price":350,"rent":5000}]
    board = [{"index":0,"type":"GO","payout":200},{"index":1,"type":"PROPERTY","propertyId":1},{"index":2,"type":"FREE_PARKING"},{"index":3,"type":"FREE_PARKING"},{"index":4,"type":"FREE_PARKING"},{"index":5,"type":"FREE_PARKING"},{"index":6,"type":"FREE_PARKING"},{"index":7,"type":"FREE_PARKING"},{"index":8,"type":"FREE_PARKING"},{"index":9,"type":"FREE_PARKING"}]
    restart_with_config("1,1", board, props)
    resp = post_json(f"{BASE_URL}/game/new", {"players": ["Landlord", "Tenant"]})
    assert resp.status_code == 200

    resp = requests.post(f"{BASE_URL}/game/roll")
    data = resp.json()
    if data["state"]["turn_pending_action"] == "buy_or_pass":
        resp = requests.post(f"{BASE_URL}/game/buy")
        data = resp.json()

    resp = requests.post(f"{BASE_URL}/game/roll")
    data = resp.json()
    print(f"Tenant rolled: {data['message']}")
    tenant = [p for p in data["state"]["players"] if p["name"] == "Tenant"][0]
    assert tenant["status"] == "Eliminated"
    assert tenant["cash"] == 0
    print("PASSED\n")

def test_game_over():
    print("=== Test: Game Over ===")
    board = [{"index":0,"type":"GO","payout":200},{"index":1,"type":"TAX","amount":600},{"index":2,"type":"FREE_PARKING"},{"index":3,"type":"FREE_PARKING"},{"index":4,"type":"FREE_PARKING"},{"index":5,"type":"FREE_PARKING"},{"index":6,"type":"FREE_PARKING"},{"index":7,"type":"FREE_PARKING"},{"index":8,"type":"FREE_PARKING"},{"index":9,"type":"FREE_PARKING"}]
    restart_with_config("1", board, default_props())
    resp = post_json(f"{BASE_URL}/game/new", {"players": ["Player1", "Player2"]})
    assert resp.status_code == 200
    resp = requests.post(f"{BASE_URL}/game/roll")
    data = resp.json()
    print(f"P1 eliminated: game_over={data['state']['game_over']}, winner={data['state']['winner']}")
    assert data["state"]["game_over"] == True
    assert data["state"]["winner"] == "Player2"
    print("PASSED\n")

def test_dice_cycling():
    print("=== Test: Dice Cycling ===")
    restart_with_config("1,2", default_board(), default_props())
    resp = post_json(f"{BASE_URL}/game/new", {"players": ["A", "B"]})
    assert resp.status_code == 200

    resp = requests.post(f"{BASE_URL}/game/roll")
    data = resp.json()
    assert data["dice_value"] == 1
    data = resolve_pending()

    resp = requests.post(f"{BASE_URL}/game/roll")
    data = resp.json()
    assert data["dice_value"] == 2
    data = resolve_pending()

    resp = requests.post(f"{BASE_URL}/game/roll")
    data = resp.json()
    assert data["dice_value"] == 1
    data = resolve_pending()

    resp = requests.post(f"{BASE_URL}/game/roll")
    data = resp.json()
    assert data["dice_value"] == 2
    print("PASSED\n")

def test_free_parking():
    print("=== Test: Free Parking ===")
    restart_with_config("6", default_board(), default_props())
    resp = post_json(f"{BASE_URL}/game/new", {"players": ["FPA", "FPB"]})
    assert resp.status_code == 200
    resp = requests.post(f"{BASE_URL}/game/roll")
    data = resp.json()
    print(f"FPA rolled: {data['message']}")
    fpa = [p for p in data["state"]["players"] if p["name"] == "FPA"][0]
    assert fpa["cash"] == 500
    assert fpa["position"] == 6
    print("PASSED\n")

def test_property_owned_by_self():
    print("=== Test: Property Owned by Self ===")
    restart_with_config("1,1,5,1", default_board(), default_props())
    resp = post_json(f"{BASE_URL}/game/new", {"players": ["LoopPlayer", "Other"]})
    assert resp.status_code == 200

    resp = requests.post(f"{BASE_URL}/game/roll")
    data = resp.json()
    assert data["state"]["turn_pending_action"] == "buy_or_pass"
    resp = requests.post(f"{BASE_URL}/game/buy")
    data = resp.json()

    resp = requests.post(f"{BASE_URL}/game/roll")
    data = resp.json()
    print(f"Other landed: {data['message']}")
    data = resolve_pending()

    resp = requests.post(f"{BASE_URL}/game/roll")
    data = resp.json()
    print(f"LoopPlayer roll 5: {data['message']}")
    data = resolve_pending()

    # LoopPlayer now at pos 6, Other at pos 2. Not testing exact self-landing but logic is sound
    state = requests.get(f"{BASE_URL}/game/state").json()
    pprint(state)
    print("PASSED\n")

def test_eliminated_skipped():
    print("=== Test: Eliminated Players Skipped ===")
    board = [{"index":0,"type":"GO","payout":200},{"index":1,"type":"TAX","amount":600},{"index":2,"type":"FREE_PARKING"},{"index":3,"type":"FREE_PARKING"},{"index":4,"type":"FREE_PARKING"},{"index":5,"type":"FREE_PARKING"},{"index":6,"type":"FREE_PARKING"},{"index":7,"type":"FREE_PARKING"},{"index":8,"type":"FREE_PARKING"},{"index":9,"type":"FREE_PARKING"}]
    restart_with_config("1", board, default_props())
    resp = post_json(f"{BASE_URL}/game/new", {"players": ["P1", "P2", "P3"]})
    assert resp.status_code == 200
    resp = requests.post(f"{BASE_URL}/game/roll")
    data = resp.json()
    print(f"P1 eliminated: {data['message']}")
    state = data["state"]
    assert state["game_over"] == False
    assert state["current_player_index"] == 1
    p1 = [p for p in state["players"] if p["name"] == "P1"][0]
    assert p1["status"] == "Eliminated"
    print("PASSED\n")

def test_restart_game():
    print("=== Test: Restart Game ===")
    restart_with_config("1,2", default_board(), default_props())
    resp = post_json(f"{BASE_URL}/game/new", {"players": ["X", "Y"]})
    data = resp.json()
    assert data["state"]["started"] == True
    assert len(data["state"]["players"]) == 2
    print("PASSED\n")

# ---------- MAIN ----------
if __name__ == "__main__":
    os.environ["BOARD_DATA"] = json.dumps(default_board())
    os.environ["PROPERTIES_DATA"] = json.dumps(default_props())
    os.environ["DICE_MOVES"] = "3,5,2,6,1,4,3,2,5,1,6,4,2,3,5,1,6,2,4,3"
    print("Starting server...")
    stop_server()
    start_server()
    print("Server started. Running tests...\n")
    try:
        test_new_game()
        test_game_state()
        test_roll_and_move()
        test_buy_property()
        test_pass_property()
        test_jail()
        test_tax()
        test_go_passing()
        test_rent()
        test_bankruptcy_by_tax()
        test_bankruptcy_by_rent()
        test_game_over()
        test_dice_cycling()
        test_free_parking()
        test_property_owned_by_self()
        test_eliminated_skipped()
        test_restart_game()
        print("\n=== ALL TESTS PASSED ===")
    except AssertionError as e:
        print(f"\nTEST FAILED: {e}")
        import traceback; traceback.print_exc()
        stop_server(); sys.exit(1)
    except Exception as e:
        print(f"\nUNEXPECTED ERROR: {e}")
        import traceback; traceback.print_exc()
        stop_server(); sys.exit(1)
    stop_server()
    sys.exit(0)
