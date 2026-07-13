import os
import json
from typing import List, Optional, Dict
from enum import Enum

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

app = FastAPI()

# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

class SpaceType(str, Enum):
    GO = "GO"
    PROPERTY = "PROPERTY"
    JAIL = "JAIL"
    TAX = "TAX"
    FREE_PARKING = "FREE_PARKING"

class PlayerStatus(str, Enum):
    ACTIVE = "Active"
    ELIMINATED = "Eliminated"

class BoardSpace(BaseModel):
    index: int
    type: SpaceType
    payout: Optional[int] = None
    amount: Optional[int] = None
    propertyId: Optional[int] = None

class PropertyInfo(BaseModel):
    id: int
    name: str
    price: int
    rent: int

class PlayerState(BaseModel):
    name: str
    cash: int
    position: int
    status: PlayerStatus
    skip_next_turn: bool
    properties: List[int]

class GameState(BaseModel):
    started: bool
    game_over: bool
    winner: Optional[str] = None
    current_player_index: int
    players: List[PlayerState]
    board: List[BoardSpace]
    properties: Dict[int, PropertyInfo]
    dice_sequence: List[int]
    dice_index: int
    turn_pending_action: Optional[str] = None
    turn_rolled: bool = False

# ---------------------------------------------------------------------------
# Global game state (in-memory, single game)
# ---------------------------------------------------------------------------

game: Optional[dict] = None

# ---------------------------------------------------------------------------
# Helper: load env data
# ---------------------------------------------------------------------------

def load_board_data() -> List[dict]:
    raw = os.environ.get("BOARD_DATA", "[]")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        raise HTTPException(status_code=500, detail="Invalid BOARD_DATA JSON")
    if not isinstance(data, list) or len(data) < 10 or len(data) > 20:
        raise HTTPException(status_code=500, detail="BOARD_DATA must be a JSON array of 10-20 spaces")
    for i, space in enumerate(data):
        if space.get("index") != i:
            raise HTTPException(status_code=500, detail=f"Space at index {i} has wrong index field")
        if space.get("type") not in [e.value for e in SpaceType]:
            raise HTTPException(status_code=500, detail=f"Invalid space type at index {i}")
    return data

def load_properties_data() -> Dict[int, dict]:
    raw = os.environ.get("PROPERTIES_DATA", "[]")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        raise HTTPException(status_code=500, detail="Invalid PROPERTIES_DATA JSON")
    if not isinstance(data, list):
        raise HTTPException(status_code=500, detail="PROPERTIES_DATA must be a JSON array")
    props = {}
    for prop in data:
        if "id" not in prop or "name" not in prop or "price" not in prop or "rent" not in prop:
            raise HTTPException(status_code=500, detail="Each property must have id, name, price, rent")
        props[prop["id"]] = prop
    return props

def load_dice_sequence() -> List[int]:
    raw = os.environ.get("DICE_MOVES", "")
    if not raw:
        return []
    parts = raw.split(",")
    seq = []
    for p in parts:
        p = p.strip()
        if not p:
            continue
        try:
            val = int(p)
        except ValueError:
            raise HTTPException(status_code=500, detail=f"Invalid dice value: {p}")
        if val < 1 or val > 6:
            raise HTTPException(status_code=500, detail=f"Dice value {val} out of range 1-6")
        seq.append(val)
    return seq

# ---------------------------------------------------------------------------
# Game logic helpers
# ---------------------------------------------------------------------------

def find_go_index(board: List[dict]) -> int:
    for space in board:
        if space["type"] == SpaceType.GO.value:
            return space["index"]
    raise HTTPException(status_code=500, detail="Board has no GO space")

def get_active_players(game_state: dict) -> List[dict]:
    return [p for p in game_state["players"] if p["status"] == PlayerStatus.ACTIVE.value]

def next_player_index(game_state: dict) -> int:
    n = len(game_state["players"])
    idx = (game_state["current_player_index"] + 1) % n
    for _ in range(n):
        if game_state["players"][idx]["status"] == PlayerStatus.ACTIVE.value:
            return idx
        idx = (idx + 1) % n
    return game_state["current_player_index"]

def next_dice(game_state: dict) -> int:
    if not game_state["dice_sequence"]:
        raise HTTPException(status_code=400, detail="No dice sequence configured")
    val = game_state["dice_sequence"][game_state["dice_index"]]
    game_state["dice_index"] = (game_state["dice_index"] + 1) % len(game_state["dice_sequence"])
    return val

def check_game_over(game_state: dict):
    active = get_active_players(game_state)
    if len(active) == 1:
        game_state["game_over"] = True
        game_state["winner"] = active[0]["name"]
    elif len(active) == 0:
        game_state["game_over"] = True
        game_state["winner"] = None

def eliminate_player(game_state: dict, player_idx: int):
    p = game_state["players"][player_idx]
    p["status"] = PlayerStatus.ELIMINATED.value
    for prop_id in p["properties"]:
        if prop_id in game_state["property_owners"]:
            if game_state["property_owners"][prop_id] == p["name"]:
                game_state["property_owners"][prop_id] = None
    p["properties"] = []
    p["cash"] = 0
    check_game_over(game_state)

def passed_go(old_pos: int, new_pos: int, go_idx: int, board_size: int) -> bool:
    if old_pos < go_idx <= new_pos:
        return True
    if old_pos > new_pos:
        if old_pos < go_idx or go_idx <= new_pos:
            return True
    return False

def handle_landing(game_state: dict, player_idx: int):
    p = game_state["players"][player_idx]
    board = game_state["board"]
    space = board[p["position"]]
    stype = space["type"]
    
    if stype == SpaceType.JAIL.value:
        p["skip_next_turn"] = True
        
    elif stype == SpaceType.TAX.value:
        amount = space["amount"]
        if p["cash"] < amount:
            p["cash"] = 0
            eliminate_player(game_state, player_idx)
        else:
            p["cash"] -= amount
            
    elif stype == SpaceType.PROPERTY.value:
        prop_id = space["propertyId"]
        owner = game_state["property_owners"].get(prop_id)
        if owner is None:
            game_state["turn_pending_action"] = "buy_or_pass"
            return
        elif owner == p["name"]:
            pass
        else:
            prop = game_state["properties"].get(prop_id)
            if prop:
                rent = prop["rent"]
                if p["cash"] < rent:
                    p["cash"] = 0
                    eliminate_player(game_state, player_idx)
                else:
                    p["cash"] -= rent
                    for op in game_state["players"]:
                        if op["name"] == owner:
                            op["cash"] += rent
                            break
    
    elif stype == SpaceType.FREE_PARKING.value:
        pass
    elif stype == SpaceType.GO.value:
        pass

def advance_turn(game_state: dict):
    game_state["turn_pending_action"] = None
    game_state["turn_rolled"] = False
    if game_state["game_over"]:
        return
    nxt = next_player_index(game_state)
    game_state["current_player_index"] = nxt

def build_game_state_response(game_state: dict) -> dict:
    return {
        "started": game_state["started"],
        "game_over": game_state["game_over"],
        "winner": game_state["winner"],
        "current_player_index": game_state["current_player_index"],
        "current_player": game_state["players"][game_state["current_player_index"]]["name"] if not game_state.get("game_over") else None,
        "players": [
            {
                "name": p["name"],
                "cash": p["cash"],
                "position": p["position"],
                "status": p["status"],
                "skip_next_turn": p["skip_next_turn"],
                "properties": p["properties"],
            }
            for p in game_state["players"]
        ],
        "turn_pending_action": game_state.get("turn_pending_action"),
    }

# ---------------------------------------------------------------------------
# API Endpoints
# ---------------------------------------------------------------------------

class NewGameRequest(BaseModel):
    players: List[str]

@app.post("/game/new")
def new_game(req: NewGameRequest):
    global game
    
    names = req.players
    if len(names) < 2 or len(names) > 4:
        raise HTTPException(status_code=400, detail="Need 2-4 players")
    if len(set(names)) != len(names):
        raise HTTPException(status_code=400, detail="Player names must be unique")
    for n in names:
        if not n or not n.strip():
            raise HTTPException(status_code=400, detail="Player names must be non-empty")
    
    try:
        board_data = load_board_data()
        properties = load_properties_data()
        dice_seq = load_dice_sequence()
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    
    if not dice_seq:
        raise HTTPException(status_code=400, detail="DICE_MOVES environment variable must be set")
    
    board = []
    for space in board_data:
        board.append(space)
    
    go_idx = find_go_index(board)
    property_owners = {prop_id: None for prop_id in properties}
    
    players = []
    for name in names:
        players.append({
            "name": name,
            "cash": 500,
            "position": go_idx,
            "status": PlayerStatus.ACTIVE.value,
            "skip_next_turn": False,
            "properties": [],
        })
    
    game = {
        "started": True,
        "game_over": False,
        "winner": None,
        "current_player_index": 0,
        "players": players,
        "board": board,
        "properties": properties,
        "property_owners": property_owners,
        "dice_sequence": dice_seq,
        "dice_index": 0,
        "turn_pending_action": None,
        "turn_rolled": False,
        "go_index": go_idx,
    }
    
    return {"message": "Game started", "state": build_game_state_response(game)}

@app.post("/game/roll")
def roll_dice():
    global game
    if game is None or not game.get("started"):
        raise HTTPException(status_code=400, detail="No game in progress")
    if game["game_over"]:
        raise HTTPException(status_code=400, detail="Game is over")
    if game.get("turn_rolled"):
        raise HTTPException(status_code=400, detail="Already rolled this turn")
    if game.get("turn_pending_action"):
        raise HTTPException(status_code=400, detail="Must resolve property decision first (buy or pass)")
    
    pidx = game["current_player_index"]
    player = game["players"][pidx]
    
    if player["skip_next_turn"]:
        player["skip_next_turn"] = False
        advance_turn(game)
        return {"message": f"{player['name']} skipped turn (was in jail)", "state": build_game_state_response(game)}
    
    dice_val = next_dice(game)
    game["turn_rolled"] = True
    
    board_size = len(game["board"])
    old_pos = player["position"]
    new_pos = (old_pos + dice_val) % board_size
    go_idx = game["go_index"]
    
    go_payout = 0
    go_space = None
    for s in game["board"]:
        if s["index"] == go_idx:
            go_space = s
            break
    
    if passed_go(old_pos, new_pos, go_idx, board_size):
        go_payout = go_space.get("payout", 0) if go_space else 0
        player["cash"] += go_payout
    
    player["position"] = new_pos
    
    handle_landing(game, pidx)
    
    if game.get("turn_pending_action") == "buy_or_pass":
        return {
            "message": f"{player['name']} rolled {dice_val} and landed on an unowned property. Choose buy or pass.",
            "dice_value": dice_val,
            "state": build_game_state_response(game)
        }
    
    advance_turn(game)
    
    return {
        "message": f"{player['name']} rolled {dice_val}",
        "dice_value": dice_val,
        "state": build_game_state_response(game)
    }

@app.post("/game/buy")
def buy_property():
    global game
    if game is None or not game.get("started"):
        raise HTTPException(status_code=400, detail="No game in progress")
    if game["game_over"]:
        raise HTTPException(status_code=400, detail="Game is over")
    if game.get("turn_pending_action") != "buy_or_pass":
        raise HTTPException(status_code=400, detail="No pending property decision")
    if not game.get("turn_rolled"):
        raise HTTPException(status_code=400, detail="Must roll first")
    
    pidx = game["current_player_index"]
    player = game["players"][pidx]
    space = game["board"][player["position"]]
    
    if space["type"] != SpaceType.PROPERTY.value:
        raise HTTPException(status_code=400, detail="Not on a property space")
    
    prop_id = space["propertyId"]
    if game["property_owners"].get(prop_id) is not None:
        raise HTTPException(status_code=400, detail="Property is already owned")
    
    prop = game["properties"].get(prop_id)
    if not prop:
        raise HTTPException(status_code=400, detail="Unknown property")
    
    if player["cash"] < prop["price"]:
        raise HTTPException(status_code=400, detail="Not enough cash to buy")
    
    player["cash"] -= prop["price"]
    player["properties"].append(prop_id)
    game["property_owners"][prop_id] = player["name"]
    
    game["turn_pending_action"] = None
    advance_turn(game)
    
    return {"message": f"{player['name']} bought {prop['name']}", "state": build_game_state_response(game)}

@app.post("/game/pass")
def pass_property():
    global game
    if game is None or not game.get("started"):
        raise HTTPException(status_code=400, detail="No game in progress")
    if game["game_over"]:
        raise HTTPException(status_code=400, detail="Game is over")
    if game.get("turn_pending_action") != "buy_or_pass":
        raise HTTPException(status_code=400, detail="No pending property decision")
    if not game.get("turn_rolled"):
        raise HTTPException(status_code=400, detail="Must roll first")
    
    game["turn_pending_action"] = None
    advance_turn(game)
    
    return {"message": "Passed on buying property", "state": build_game_state_response(game)}

@app.get("/game/state")
def get_game_state():
    global game
    if game is None or not game.get("started"):
        raise HTTPException(status_code=400, detail="No game in progress")
    return build_game_state_response(game)

@app.get("/game/players")
def get_players():
    global game
    if game is None or not game.get("started"):
        raise HTTPException(status_code=400, detail="No game in progress")
    return {"players": build_game_state_response(game)["players"]}

@app.get("/game/board")
def get_board():
    global game
    if game is None or not game.get("started"):
        raise HTTPException(status_code=400, detail="No game in progress")
    return {"board": game["board"], "properties": game["properties"]}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
