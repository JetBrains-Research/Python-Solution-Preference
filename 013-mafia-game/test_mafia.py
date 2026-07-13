"""End-to-end tests using Flask test client."""
import json
from app import app, state, reset_state, STATE_LOCK

def setup():
    with STATE_LOCK:
        reset_state(preserve_last_result=False)

def post(client, path, body):
    return client.post(path, data=json.dumps(body), content_type="application/json")

def join(c, name):
    r = post(c, "/lobby/join", {"name": name})
    assert r.status_code == 201, (name, r.status_code, r.get_json())
    return r.get_json()["player_id"]

def get_role(c, pid):
    return c.get(f"/game/role?player_id={pid}").get_json()

def vote_day(c, voter, target):
    r = post(c, "/game/day/vote", {"player_id": voter, "target": target})
    return r

def vote_night(c, voter, target):
    r = post(c, "/game/night/vote", {"player_id": voter, "target": target})
    return r

def test_name_validation():
    setup()
    c = app.test_client()
    r = post(c, "/lobby/join", {"name": "ab"}); assert r.status_code == 400
    r = post(c, "/lobby/join", {"name": "bad!name"}); assert r.status_code == 400
    r = post(c, "/lobby/join", {"name": "valid_1"}); assert r.status_code == 201
    r = post(c, "/lobby/join", {"name": "VALID_1"}); assert r.status_code == 409
    r = post(c, "/lobby/join", {"name": "another"}); assert r.status_code == 201
    r = post(c, "/lobby/join", {"name": "a" * 21}); assert r.status_code == 400
    print("test_name_validation PASSED")

def test_min_players():
    setup()
    c = app.test_client()
    ids = [join(c, f"pl{i:02d}") for i in range(3)]
    r = post(c, "/game/start", {"player_id": ids[0]}); assert r.status_code == 400
    ids.append(join(c, "pl03"))
    r = post(c, "/game/start", {"player_id": ids[0]}); assert r.status_code == 200
    print("test_min_players PASSED")

def test_full_game_citizens_win():
    setup()
    c = app.test_client()
    ids = [join(c, f"player{i}") for i in range(4)]
    r = post(c, "/game/start", {"player_id": ids[0]})
    assert r.get_json()["mafia_count"] == 1

    mafia_id = None
    for pid in ids:
        rd = get_role(c, pid)
        if rd["role"] == "mafia":
            mafia_id = pid
            assert "mafia_teammates" in rd
    assert mafia_id is not None

    final = None
    for pid in ids:
        r = vote_day(c, pid, mafia_id)
        rd = r.get_json()
        if rd.get("resolved"):
            final = rd
            break
    assert final is not None
    result = c.get("/game/result").get_json()
    assert result["winner"] == "citizens", result
    assert c.get("/lobby").get_json()["locked"] == False
    # Roles revealed in result
    for p in result["players"]:
        assert "role" in p
    print("test_full_game_citizens_win PASSED")

def test_mafia_wins_via_night():
    setup()
    c = app.test_client()
    ids = [join(c, f"plr{i:02d}") for i in range(6)]
    r = post(c, "/game/start", {"player_id": ids[0]})
    assert r.get_json()["mafia_count"] == 2

    mafia_ids, citizen_ids = [], []
    for pid in ids:
        rd = get_role(c, pid)
        (mafia_ids if rd["role"] == "mafia" else citizen_ids).append(pid)

    starter = ids[0]
    # Day 1: advance no elim
    post(c, "/game/advance", {"player_id": starter})
    st = c.get("/game/state").get_json(); assert st["phase"] == "night"

    # Night 1: kill citizen 0
    for m in mafia_ids:
        r = vote_night(c, m, citizen_ids[0])
    # Now: 2 mafia, 3 citizens; still day
    st = c.get("/game/state").get_json()
    assert st["phase"] == "day", st

    # Day 2: advance
    post(c, "/game/advance", {"player_id": starter})
    # Night 2: kill citizen 1 -> 2 mafia vs 2 citizens => mafia win
    for m in mafia_ids:
        r = vote_night(c, m, citizen_ids[1])
    result = c.get("/game/result").get_json()
    assert result["winner"] == "mafia", result
    assert c.get("/lobby").get_json()["locked"] == False
    print("test_mafia_wins_via_night PASSED")

def test_night_starter_advance_tie_and_unique():
    setup()
    c = app.test_client()
    ids = [join(c, f"nn{i:02d}") for i in range(9)]
    r = post(c, "/game/start", {"player_id": ids[0]})
    assert r.get_json()["mafia_count"] == 3

    mafia_ids, citizen_ids = [], []
    for pid in ids:
        rd = get_role(c, pid)
        (mafia_ids if rd["role"] == "mafia" else citizen_ids).append(pid)

    starter = ids[0]
    post(c, "/game/advance", {"player_id": starter})

    # 3 mafia; make it 1-1-1 tie
    vote_night(c, mafia_ids[0], citizen_ids[0])
    vote_night(c, mafia_ids[1], citizen_ids[1])
    vote_night(c, mafia_ids[2], citizen_ids[2])
    r = post(c, "/game/advance", {"player_id": starter})
    d = r.get_json()
    assert d["resolution"] == "no_kill" and d["reason"] == "tie", d

    # Day 2 advance (from day back to night)
    post(c, "/game/advance", {"player_id": starter})
    # Now night; 2 votes on same, resolves automatically at threshold=2
    vote_night(c, mafia_ids[0], citizen_ids[0])
    r = vote_night(c, mafia_ids[1], citizen_ids[0])
    st = c.get("/game/state").get_json()
    assert st["phase"] == "day"
    dead = [p for p in st["players"] if not p["alive"]]
    assert len(dead) == 1 and dead[0]["id"] == citizen_ids[0]
    print("test_night_starter_advance_tie_and_unique PASSED")

def test_mafia_cannot_target_mafia():
    setup()
    c = app.test_client()
    ids = [join(c, f"mm{i:02d}") for i in range(6)]
    post(c, "/game/start", {"player_id": ids[0]})
    mafia_ids = [pid for pid in ids if get_role(c, pid)["role"] == "mafia"]
    post(c, "/game/advance", {"player_id": ids[0]})
    r = vote_night(c, mafia_ids[0], mafia_ids[1])
    assert r.status_code == 400
    print("test_mafia_cannot_target_mafia PASSED")

def test_join_locked_during_game():
    setup()
    c = app.test_client()
    ids = [join(c, f"jj{i:02d}") for i in range(4)]
    post(c, "/game/start", {"player_id": ids[0]})
    r = post(c, "/lobby/join", {"name": "latecomer1"})
    assert r.status_code == 409
    assert c.get("/lobby").get_json()["locked"] == True
    print("test_join_locked_during_game PASSED")

def test_non_starter_cannot_advance():
    setup()
    c = app.test_client()
    ids = [join(c, f"ss{i:02d}") for i in range(4)]
    post(c, "/game/start", {"player_id": ids[0]})
    r = post(c, "/game/advance", {"player_id": ids[1]})
    assert r.status_code == 403
    print("test_non_starter_cannot_advance PASSED")

def test_no_elimination_option():
    setup()
    c = app.test_client()
    ids = [join(c, f"ee{i:02d}") for i in range(4)]
    post(c, "/game/start", {"player_id": ids[0]})
    # threshold = 3
    final = None
    for pid in ids[:3]:
        r = vote_day(c, pid, "no_elimination")
        rd = r.get_json()
        if rd.get("resolved"):
            final = rd
    assert final and final["resolution_target"] == "no_elimination"
    assert c.get("/game/state").get_json()["phase"] == "night"
    print("test_no_elimination_option PASSED")

def test_non_lobby_player_cannot_start():
    setup()
    c = app.test_client()
    ids = [join(c, f"xx{i:02d}") for i in range(4)]
    r = post(c, "/game/start", {"player_id": "not-a-real-id"})
    assert r.status_code == 403
    print("test_non_lobby_player_cannot_start PASSED")

def test_non_mafia_cannot_night_vote():
    setup()
    c = app.test_client()
    ids = [join(c, f"cc{i:02d}") for i in range(4)]
    post(c, "/game/start", {"player_id": ids[0]})
    citizen = [pid for pid in ids if get_role(c, pid)["role"] == "citizen"][0]
    mafia = [pid for pid in ids if get_role(c, pid)["role"] == "mafia"][0]
    post(c, "/game/advance", {"player_id": ids[0]})  # to night
    r = vote_night(c, citizen, mafia)
    assert r.status_code == 403
    print("test_non_mafia_cannot_night_vote PASSED")

def test_citizen_cannot_see_night_state():
    setup()
    c = app.test_client()
    ids = [join(c, f"zz{i:02d}") for i in range(4)]
    post(c, "/game/start", {"player_id": ids[0]})
    citizen = [pid for pid in ids if get_role(c, pid)["role"] == "citizen"][0]
    post(c, "/game/advance", {"player_id": ids[0]})
    r = c.get(f"/game/night/state?player_id={citizen}")
    assert r.status_code == 403
    print("test_citizen_cannot_see_night_state PASSED")

def test_max_players():
    setup()
    c = app.test_client()
    for i in range(16):
        join(c, f"mx{i:02d}")
    r = post(c, "/lobby/join", {"name": "extra1"})
    assert r.status_code == 409
    print("test_max_players PASSED")

def test_mafia_count_formula():
    # Verify max(1, floor(N/3))
    for n in range(4, 17):
        setup()
        c = app.test_client()
        for i in range(n):
            join(c, f"z{i:02d}a")
        ids = [state["join_order"][i] for i in range(n)]
        r = post(c, "/game/start", {"player_id": ids[0]})
        expected = max(1, n // 3)
        assert r.get_json()["mafia_count"] == expected, (n, r.get_json())
    print("test_mafia_count_formula PASSED")

if __name__ == "__main__":
    test_name_validation()
    test_min_players()
    test_full_game_citizens_win()
    test_mafia_wins_via_night()
    test_night_starter_advance_tie_and_unique()
    test_mafia_cannot_target_mafia()
    test_join_locked_during_game()
    test_non_starter_cannot_advance()
    test_no_elimination_option()
    test_non_lobby_player_cannot_start()
    test_non_mafia_cannot_night_vote()
    test_citizen_cannot_see_night_state()
    test_max_players()
    test_mafia_count_formula()
    print("\nAll tests PASSED")
