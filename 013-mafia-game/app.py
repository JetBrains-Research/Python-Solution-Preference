"""Mafia Game MVP - single-room Mafia game HTTP API."""
import re
import uuid
import random
import threading
from flask import Flask, request, jsonify

app = Flask(__name__)

STATE_LOCK = threading.RLock()

NAME_RE = re.compile(r'^[A-Za-z0-9 _-]{3,20}$')
NO_ELIM = "no_elimination"

state = {
    "phase": "lobby",       # lobby | day | night
    "day_number": 0,
    "game_active": False,
    "players": {},           # player_id -> {name, alive, role, id}
    "join_order": [],
    "starter_id": None,
    "day_votes": {},         # voter_id -> target
    "night_votes": {},       # voter_id -> target
    "eliminations": [],
    "last_result": None,     # final reveal from the previous game
}


def reset_state(preserve_last_result=True):
    prev = state.get("last_result") if preserve_last_result else None
    state.update({
        "phase": "lobby",
        "day_number": 0,
        "game_active": False,
        "players": {},
        "join_order": [],
        "starter_id": None,
        "day_votes": {},
        "night_votes": {},
        "eliminations": [],
        "last_result": prev,
    })


def name_taken(name):
    lower = name.lower()
    for pid in state["join_order"]:
        if state["players"][pid]["name"].lower() == lower:
            return True
    return False


def get_alive_players():
    return [p for p in state["players"].values() if p["alive"]]


def get_alive_mafia():
    return [p for p in state["players"].values() if p["alive"] and p["role"] == "mafia"]


def get_alive_citizens():
    return [p for p in state["players"].values() if p["alive"] and p["role"] == "citizen"]


def public_player_view():
    return [
        {
            "id": pid,
            "name": state["players"][pid]["name"],
            "alive": state["players"][pid]["alive"],
        }
        for pid in state["join_order"]
    ]


def player_view_with_dead_reveal():
    result = []
    for pid in state["join_order"]:
        p = state["players"][pid]
        entry = {"id": pid, "name": p["name"], "alive": p["alive"]}
        if not p["alive"]:
            entry["role"] = p["role"]
        result.append(entry)
    return result


def day_vote_tally():
    tally = {}
    for target in state["day_votes"].values():
        tally[target] = tally.get(target, 0) + 1
    return tally


def night_vote_tally():
    tally = {}
    for target in state["night_votes"].values():
        tally[target] = tally.get(target, 0) + 1
    return tally


def check_win_conditions():
    mafia_alive = len(get_alive_mafia())
    citizens_alive = len(get_alive_citizens())
    if mafia_alive == 0:
        return "citizens"
    if mafia_alive >= citizens_alive:
        return "mafia"
    return None


def finalize_result(winner):
    state["last_result"] = {
        "winner": winner,
        "players": [
            {
                "id": pid,
                "name": state["players"][pid]["name"],
                "role": state["players"][pid]["role"],
                "alive": state["players"][pid]["alive"],
            }
            for pid in state["join_order"]
        ],
        "eliminations": list(state["eliminations"]),
        "starter_id": state["starter_id"],
    }


def end_game(winner):
    finalize_result(winner)
    # Release lobby lock: reset lobby state, keep last_result
    reset_state(preserve_last_result=True)


def resolve_day_elimination(target):
    if target == NO_ELIM:
        state["eliminations"].append({
            "phase": "day",
            "day": state["day_number"],
            "player_id": None,
            "name": None,
            "role": None,
            "no_elimination": True,
        })
    else:
        p = state["players"][target]
        p["alive"] = False
        state["eliminations"].append({
            "phase": "day",
            "day": state["day_number"],
            "player_id": target,
            "name": p["name"],
            "role": p["role"],
            "no_elimination": False,
        })
    state["day_votes"] = {}
    winner = check_win_conditions()
    if winner:
        end_game(winner)
    else:
        state["phase"] = "night"


def resolve_night_kill(target):
    if target is None:
        state["eliminations"].append({
            "phase": "night",
            "day": state["day_number"],
            "player_id": None,
            "name": None,
            "role": None,
            "no_kill": True,
        })
    else:
        p = state["players"][target]
        p["alive"] = False
        state["eliminations"].append({
            "phase": "night",
            "day": state["day_number"],
            "player_id": target,
            "name": p["name"],
            "role": p["role"],
            "no_kill": False,
        })
    state["night_votes"] = {}
    winner = check_win_conditions()
    if winner:
        end_game(winner)
    else:
        state["day_number"] += 1
        state["phase"] = "day"


def err(msg, code=400):
    return jsonify({"error": msg}), code


# ============== LOBBY ==============

@app.route("/lobby", methods=["GET"])
def get_lobby():
    with STATE_LOCK:
        return jsonify({
            "locked": state["game_active"],
            "phase": state["phase"],
            "players": [
                {"id": pid, "name": state["players"][pid]["name"]}
                for pid in state["join_order"]
            ],
            "can_start": (not state["game_active"]) and len(state["join_order"]) >= 4,
        })


@app.route("/lobby/join", methods=["POST"])
def join_lobby():
    with STATE_LOCK:
        data = request.get_json(silent=True) or {}
        name = data.get("name", "")
        if not isinstance(name, str):
            return err("name must be a string")
        name = name.strip()
        if not NAME_RE.match(name):
            return err("Invalid name. Must be 3-20 chars: letters, numbers, spaces, hyphens, underscores.")
        if state["game_active"]:
            return err("Lobby is locked; a game is in progress.", 409)
        if len(state["join_order"]) >= 16:
            return err("Lobby is full (max 16 players).", 409)
        if name_taken(name):
            return err("Name already taken.", 409)
        pid = uuid.uuid4().hex
        state["players"][pid] = {"id": pid, "name": name, "alive": True, "role": None}
        state["join_order"].append(pid)
        return jsonify({"player_id": pid, "name": name}), 201


# ============== GAME START ==============

@app.route("/game/start", methods=["POST"])
def start_game():
    with STATE_LOCK:
        data = request.get_json(silent=True) or {}
        pid = data.get("player_id")
        if state["game_active"]:
            return err("Game already in progress.", 409)
        if pid not in state["players"]:
            return err("Unknown player_id. Only lobby-joined players may start.", 403)
        n = len(state["join_order"])
        if n < 4:
            return err("Need at least 4 players to start.", 400)
        if n > 16:
            return err("Too many players (max 16).", 400)

        state["starter_id"] = pid
        mafia_count = max(1, n // 3)
        ids = list(state["join_order"])
        random.shuffle(ids)
        mafia_ids = set(ids[:mafia_count])
        for p_id in state["join_order"]:
            state["players"][p_id]["role"] = "mafia" if p_id in mafia_ids else "citizen"
            state["players"][p_id]["alive"] = True
        state["game_active"] = True
        state["phase"] = "day"
        state["day_number"] = 1
        state["day_votes"] = {}
        state["night_votes"] = {}
        state["eliminations"] = []
        return jsonify({
            "started": True,
            "starter_id": pid,
            "phase": "day",
            "day": 1,
            "player_count": n,
            "mafia_count": mafia_count,
        })


# ============== GAME STATE ==============

@app.route("/game/state", methods=["GET"])
def get_game_state():
    with STATE_LOCK:
        resp = {
            "phase": state["phase"],
            "day": state["day_number"],
            "game_active": state["game_active"],
            "starter_id": state["starter_id"],
            "players": player_view_with_dead_reveal() if state["game_active"] else [],
            "eliminations": list(state["eliminations"]),
        }
        if state["phase"] == "day" and state["game_active"]:
            alive = len(get_alive_players())
            resp["day_votes"] = day_vote_tally()
            resp["alive_count"] = alive
            resp["majority_threshold"] = alive // 2 + 1
        if state["phase"] == "night" and state["game_active"]:
            resp["alive_count"] = len(get_alive_players())
        return jsonify(resp)


@app.route("/game/result", methods=["GET"])
def game_result():
    with STATE_LOCK:
        if not state["last_result"]:
            return err("No completed game to report.", 404)
        return jsonify(state["last_result"])


# ============== ROLE ==============

@app.route("/game/role", methods=["GET"])
def get_role():
    with STATE_LOCK:
        pid = request.args.get("player_id")
        if not pid or pid not in state["players"]:
            return err("Unknown player_id", 403)
        if not state["game_active"]:
            return err("No active game.", 409)
        p = state["players"][pid]
        resp = {"player_id": pid, "role": p["role"]}
        if p["role"] == "mafia":
            resp["mafia_teammates"] = [
                {"id": q["id"], "name": q["name"], "alive": q["alive"]}
                for q in state["players"].values() if q["role"] == "mafia"
            ]
        return jsonify(resp)


# ============== DAY VOTE ==============

@app.route("/game/day/vote", methods=["POST"])
def day_vote():
    with STATE_LOCK:
        if not state["game_active"] or state["phase"] != "day":
            return err("Not in day phase.", 409)
        data = request.get_json(silent=True) or {}
        voter = data.get("player_id")
        target = data.get("target")
        if voter not in state["players"]:
            return err("Unknown voter.", 403)
        if not state["players"][voter]["alive"]:
            return err("Dead players cannot vote.", 403)
        if target != NO_ELIM:
            if target not in state["players"]:
                return err("Unknown target.", 400)
            if not state["players"][target]["alive"]:
                return err("Target is not alive.", 400)
        state["day_votes"][voter] = target

        alive_count = len(get_alive_players())
        threshold = alive_count // 2 + 1
        tally = day_vote_tally()
        resolved_target = None
        for t, c in tally.items():
            if c >= threshold:
                resolved_target = t
                break
        response = {
            "recorded": True,
            "votes": tally,
            "threshold": threshold,
            "alive_count": alive_count,
        }
        if resolved_target is not None:
            resolve_day_elimination(resolved_target)
            response["resolved"] = True
            response["resolution_target"] = resolved_target
            response["phase"] = state["phase"]
            response["game_active"] = state["game_active"]
        else:
            response["resolved"] = False
        return jsonify(response)


# ============== NIGHT VOTE ==============

@app.route("/game/night/vote", methods=["POST"])
def night_vote():
    with STATE_LOCK:
        if not state["game_active"] or state["phase"] != "night":
            return err("Not in night phase.", 409)
        data = request.get_json(silent=True) or {}
        voter = data.get("player_id")
        target = data.get("target")
        if voter not in state["players"]:
            return err("Unknown voter.", 403)
        v = state["players"][voter]
        if v["role"] != "mafia":
            return err("Only mafia can vote at night.", 403)
        if not v["alive"]:
            return err("Dead players cannot vote.", 403)
        if target not in state["players"]:
            return err("Unknown target.", 400)
        t = state["players"][target]
        if not t["alive"]:
            return err("Target is not alive.", 400)
        if t["role"] == "mafia":
            return err("Mafia cannot target mafia.", 400)
        state["night_votes"][voter] = target

        alive_mafia_count = len(get_alive_mafia())
        threshold = alive_mafia_count // 2 + 1
        tally = night_vote_tally()
        resolved_target = None
        for tgt, c in tally.items():
            if c >= threshold:
                resolved_target = tgt
                break
        response = {
            "recorded": True,
            "votes": tally,
            "threshold": threshold,
            "mafia_alive": alive_mafia_count,
        }
        if resolved_target is not None:
            resolve_night_kill(resolved_target)
            response["resolved"] = True
            response["resolution_target"] = resolved_target
            response["phase"] = state["phase"]
            response["game_active"] = state["game_active"]
        else:
            response["resolved"] = False
        return jsonify(response)


# ============== NIGHT STATE (mafia-only aggregated votes) ==============

@app.route("/game/night/state", methods=["GET"])
def get_night_state():
    with STATE_LOCK:
        pid = request.args.get("player_id")
        if not pid or pid not in state["players"]:
            return err("Unknown player_id.", 403)
        if state["phase"] != "night" or not state["game_active"]:
            return err("Not in night phase.", 409)
        p = state["players"][pid]
        if p["role"] != "mafia":
            return err("Only mafia can view night state.", 403)
        alive_mafia_count = len(get_alive_mafia())
        return jsonify({
            "votes": night_vote_tally(),
            "threshold": alive_mafia_count // 2 + 1,
            "mafia_alive": alive_mafia_count,
        })


# ============== ADVANCE PHASE (Game Starter) ==============

@app.route("/game/advance", methods=["POST"])
def advance_phase():
    with STATE_LOCK:
        data = request.get_json(silent=True) or {}
        pid = data.get("player_id")
        if not state["game_active"]:
            return err("No active game.", 409)
        if pid != state["starter_id"]:
            return err("Only the Game Starter may advance phases.", 403)
        if state["phase"] == "day":
            resolve_day_elimination(NO_ELIM)
            return jsonify({
                "advanced": True,
                "resolution": "no_elimination",
                "phase": state["phase"],
                "game_active": state["game_active"],
            })
        elif state["phase"] == "night":
            tally = night_vote_tally()
            if not tally:
                resolve_night_kill(None)
                return jsonify({
                    "advanced": True,
                    "resolution": "no_kill",
                    "reason": "no_votes",
                    "phase": state["phase"],
                    "game_active": state["game_active"],
                })
            max_count = max(tally.values())
            top = [t for t, c in tally.items() if c == max_count]
            if len(top) == 1:
                target = top[0]
                resolve_night_kill(target)
                return jsonify({
                    "advanced": True,
                    "resolution": "kill",
                    "target": target,
                    "phase": state["phase"],
                    "game_active": state["game_active"],
                })
            else:
                resolve_night_kill(None)
                return jsonify({
                    "advanced": True,
                    "resolution": "no_kill",
                    "reason": "tie",
                    "phase": state["phase"],
                    "game_active": state["game_active"],
                })
        else:
            return err("Cannot advance in current phase.", 409)


# ============== RESET (helper) ==============

@app.route("/lobby/reset", methods=["POST"])
def reset_endpoint():
    with STATE_LOCK:
        if state["game_active"]:
            return err("Cannot reset while game is active.", 409)
        reset_state(preserve_last_result=False)
        return jsonify({"reset": True})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
