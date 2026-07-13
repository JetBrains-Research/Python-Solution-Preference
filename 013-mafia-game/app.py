from flask import Flask, jsonify, request
import re
import math
from enum import Enum
from typing import Dict, List, Optional, Set

app = Flask(__name__)

# Game state
class GameState(Enum):
    LOBBY = "lobby"
    DAY = "day"
    NIGHT = "night"
    ENDED = "ended"

class PlayerRole(Enum):
    CITIZEN = "citizen"
    MAFIA = "mafia"

class Player:
    def __init__(self, name: str):
        self.name = name
        self.role: Optional[PlayerRole] = None
        self.is_alive = True
        self.has_retrieved_role = False
    
    def to_dict(self, include_role: bool = False, include_mafia_teammates: bool = False) -> dict:
        result = {
            "name": self.name,
            "alive": self.is_alive
        }
        if include_role:
            result["role"] = self.role.value if self.role else None
        return result

# Global game state
game_state = GameState.LOBBY
players: Dict[str, Player] = {}  # name -> Player (case-insensitive key)
game_starter: Optional[str] = None
day_number = 1
day_votes: Dict[str, str] = {}  # voter_name -> target_name or "no_elimination"
night_votes: Dict[str, str] = {}  # mafia_voter_name -> target_name
winner: Optional[str] = None  # "citizens" or "mafia" or None

# Lobby lock
lobby_locked = False

def get_mafia_count(num_players: int) -> int:
    return max(1, num_players // 3)

def get_alive_players() -> List[Player]:
    return [p for p in players.values() if p.is_alive]

def get_alive_mafia() -> List[Player]:
    return [p for p in players.values() if p.is_alive and p.role == PlayerRole.MAFIA]

def get_alive_citizens() -> List[Player]:
    return [p for p in players.values() if p.is_alive and p.role == PlayerRole.CITIZEN]

def check_win_conditions() -> Optional[str]:
    """Returns 'citizens', 'mafia', or None if game continues"""
    alive_mafia = get_alive_mafia()
    alive_citizens = get_alive_citizens()
    
    if len(alive_mafia) == 0:
        return "citizens"
    if len(alive_mafia) >= len(alive_citizens):
        return "mafia"
    return None

def end_game(winner_type: str):
    global game_state, winner, lobby_locked
    winner = winner_type
    game_state = GameState.ENDED
    lobby_locked = False

def validate_name(name: str) -> tuple:
    """Returns (is_valid, error_message)"""
    if not name:
        return False, "Name is required"
    if len(name) < 3 or len(name) > 20:
        return False, "Name must be 3-20 characters"
    if not re.match(r'^[a-zA-Z0-9 _-]+$', name):
        return False, "Name can only contain letters, numbers, spaces, hyphens, and underscores"
    return True, ""

@app.route('/health', methods=['GET'])
def health():
    return jsonify({"status": "ok"})

@app.route('/lobby', methods=['GET'])
def get_lobby():
    if lobby_locked:
        return jsonify({
            "locked": True,
            "message": "Game is in progress",
            "players": []
        })
    
    player_list = [{"name": p.name} for p in players.values()]
    return jsonify({
        "locked": False,
        "players": player_list,
        "can_start": len(players) >= 4
    })

@app.route('/lobby/join', methods=['POST'])
def join_lobby():
    global lobby_locked
    
    if lobby_locked:
        return jsonify({"error": "Game is in progress, lobby is locked"}), 400
    
    data = request.get_json()
    if not data or 'name' not in data:
        return jsonify({"error": "Name is required"}), 400
    
    name = data['name']
    is_valid, error = validate_name(name)
    if not is_valid:
        return jsonify({"error": error}), 400
    
    # Case-insensitive uniqueness check
    name_lower = name.lower()
    for existing_name in players.keys():
        if existing_name.lower() == name_lower:
            return jsonify({"error": f"Name '{name}' is already taken"}), 400
    
    players[name] = Player(name)
    return jsonify({"message": f"Joined as {name}", "name": name})

@app.route('/lobby/leave', methods=['POST'])
def leave_lobby():
    global lobby_locked
    
    if lobby_locked:
        return jsonify({"error": "Cannot leave during game"}), 400
    
    data = request.get_json()
    if not data or 'name' not in data:
        return jsonify({"error": "Name is required"}), 400
    
    name = data['name']
    name_lower = name.lower()
    
    # Find the player with matching name (case-insensitive)
    actual_name = None
    for existing_name in players.keys():
        if existing_name.lower() == name_lower:
            actual_name = existing_name
            break
    
    if actual_name is None:
        return jsonify({"error": "Player not found in lobby"}), 404
    
    del players[actual_name]
    return jsonify({"message": f"{actual_name} left the lobby"})

@app.route('/game/start', methods=['POST'])
def start_game():
    global game_state, lobby_locked, game_starter, day_number, day_votes, night_votes, winner
    
    if game_state not in [GameState.LOBBY, GameState.ENDED]:
        return jsonify({"error": "Game is already in progress"}), 400
    
    if len(players) < 4:
        return jsonify({"error": "Need at least 4 players to start"}), 400
    
    data = request.get_json()
    if not data or 'name' not in data:
        return jsonify({"error": "Name is required"}), 400
    
    name = data['name']
    name_lower = name.lower()
    
    # Find the player with matching name (case-insensitive)
    actual_name = None
    for existing_name in players.keys():
        if existing_name.lower() == name_lower:
            actual_name = existing_name
            break
    
    if actual_name is None:
        return jsonify({"error": "Player not found in lobby"}), 404
    
    # Reset game state
    game_state = GameState.DAY
    day_number = 1
    day_votes = {}
    night_votes = {}
    winner = None
    
    # Assign roles
    num_players = len(players)
    mafia_count = get_mafia_count(num_players)
    
    player_list = list(players.values())
    # Shuffle players for random role assignment
    import random
    random.shuffle(player_list)
    
    # Assign mafia roles
    for i, player in enumerate(player_list):
        if i < mafia_count:
            player.role = PlayerRole.MAFIA
        else:
            player.role = PlayerRole.CITIZEN
    
    # Set game starter
    game_starter = actual_name
    lobby_locked = True
    
    return jsonify({
        "message": "Game started",
        "day": day_number,
        "phase": "day"
    })

@app.route('/game/role', methods=['GET'])
def get_role():
    global game_state
    
    if game_state == GameState.LOBBY:
        return jsonify({"error": "Game has not started"}), 400
    
    if game_state == GameState.ENDED:
        return jsonify({"error": "Game has ended"}), 400
    
    name = request.args.get('name')
    if not name:
        return jsonify({"error": "Name is required"}), 400
    
    name_lower = name.lower()
    actual_name = None
    for existing_name in players.keys():
        if existing_name.lower() == name_lower:
            actual_name = existing_name
            break
    
    if actual_name is None:
        return jsonify({"error": "Player not found"}), 404
    
    player = players[actual_name]
    
    # Get mafia teammates for mafia players
    mafia_teammates = []
    if player.role == PlayerRole.MAFIA:
        for p in players.values():
            if p.role == PlayerRole.MAFIA and p.name != actual_name:
                mafia_teammates.append(p.name)
    
    result = {
        "name": actual_name,
        "role": player.role.value,
        "mafia_teammates": mafia_teammates
    }
    
    return jsonify(result)

@app.route('/game/status', methods=['GET'])
def get_game_status():
    global game_state, day_number, winner
    
    if game_state == GameState.LOBBY:
        return jsonify({"error": "Game has not started"}), 400
    
    player_list = []
    for p in players.values():
        player_list.append({
            "name": p.name,
            "alive": p.is_alive
        })
    
    result = {
        "phase": game_state.value,
        "day": day_number,
        "players": player_list
    }
    
    if game_state == GameState.ENDED:
        result["winner"] = winner
    
    return jsonify(result)

@app.route('/game/day/vote', methods=['POST'])
def day_vote():
    global game_state, day_votes
    
    if game_state != GameState.DAY:
        return jsonify({"error": "Not in day phase"}), 400
    
    data = request.get_json()
    if not data:
        return jsonify({"error": "Missing data"}), 400
    
    voter_name = data.get('name')
    target = data.get('target')
    
    if not voter_name:
        return jsonify({"error": "Name is required"}), 400
    
    # Find player
    name_lower = voter_name.lower()
    actual_voter_name = None
    for existing_name in players.keys():
        if existing_name.lower() == name_lower:
            actual_voter_name = existing_name
            break
    
    if actual_voter_name is None:
        return jsonify({"error": "Player not found"}), 404
    
    voter = players[actual_voter_name]
    
    if not voter.is_alive:
        return jsonify({"error": "Dead players cannot vote"}), 400
    
    # Validate target
    if target == "no_elimination":
        day_votes[actual_voter_name] = "no_elimination"
    else:
        if not target:
            return jsonify({"error": "Target is required"}), 400
        
        target_lower = target.lower()
        actual_target_name = None
        for existing_name in players.keys():
            if existing_name.lower() == target_lower:
                actual_target_name = existing_name
                break
        
        if actual_target_name is None:
            return jsonify({"error": "Target not found"}), 404
        
        target_player = players[actual_target_name]
        if not target_player.is_alive:
            return jsonify({"error": "Cannot vote for dead player"}), 400
        
        day_votes[actual_voter_name] = actual_target_name
    
    return jsonify({"message": "Vote recorded"})

@app.route('/game/day/votes', methods=['GET'])
def get_day_votes():
    global game_state
    
    if game_state != GameState.DAY:
        return jsonify({"error": "Not in day phase"}), 400
    
    # Count votes
    vote_counts = {}
    alive_players = get_alive_players()
    
    for target in [p.name for p in alive_players]:
        vote_counts[target] = 0
    vote_counts["no_elimination"] = 0
    
    for voter, target in day_votes.items():
        vote_counts[target] = vote_counts.get(target, 0) + 1
    
    # Check for majority
    majority_threshold = math.floor(len(alive_players) / 2) + 1
    
    result = {
        "votes": vote_counts,
        "majority_threshold": majority_threshold,
        "alive_count": len(alive_players)
    }
    
    return jsonify(result)

@app.route('/game/night/vote', methods=['POST'])
def night_vote():
    global game_state, night_votes
    
    if game_state != GameState.NIGHT:
        return jsonify({"error": "Not in night phase"}), 400
    
    data = request.get_json()
    if not data:
        return jsonify({"error": "Missing data"}), 400
    
    voter_name = data.get('name')
    target = data.get('target')
    
    if not voter_name:
        return jsonify({"error": "Name is required"}), 400
    
    # Find player
    name_lower = voter_name.lower()
    actual_voter_name = None
    for existing_name in players.keys():
        if existing_name.lower() == name_lower:
            actual_voter_name = existing_name
            break
    
    if actual_voter_name is None:
        return jsonify({"error": "Player not found"}), 404
    
    voter = players[actual_voter_name]
    
    if not voter.is_alive:
        return jsonify({"error": "Dead players cannot vote"}), 400
    
    if voter.role != PlayerRole.MAFIA:
        return jsonify({"error": "Only mafia can vote at night"}), 400
    
    # Validate target - must be alive citizen
    if not target:
        return jsonify({"error": "Target is required"}), 400
    
    target_lower = target.lower()
    actual_target_name = None
    for existing_name in players.keys():
        if existing_name.lower() == target_lower:
            actual_target_name = existing_name
            break
    
    if actual_target_name is None:
        return jsonify({"error": "Target not found"}), 404
    
    target_player = players[actual_target_name]
    if not target_player.is_alive:
        return jsonify({"error": "Cannot target dead player"}), 400
    
    if target_player.role != PlayerRole.CITIZEN:
        return jsonify({"error": "Mafia can only target citizens"}), 400
    
    night_votes[actual_voter_name] = actual_target_name
    
    return jsonify({"message": "Vote recorded"})

@app.route('/game/night/votes', methods=['GET'])
def get_night_votes():
    global game_state
    
    if game_state != GameState.NIGHT:
        return jsonify({"error": "Not in night phase"}), 400
    
    name = request.args.get('name')
    if not name:
        return jsonify({"error": "Name is required"}), 400
    
    # Find player
    name_lower = name.lower()
    actual_name = None
    for existing_name in players.keys():
        if existing_name.lower() == name_lower:
            actual_name = existing_name
            break
    
    if actual_name is None:
        return jsonify({"error": "Player not found"}), 404
    
    player = players[actual_name]
    
    if player.role != PlayerRole.MAFIA:
        return jsonify({"error": "Only mafia can see night votes"}), 400
    
    # Count votes
    vote_counts = {}
    alive_citizens = get_alive_citizens()
    
    for target in [p.name for p in alive_citizens]:
        vote_counts[target] = 0
    
    for voter, target in night_votes.items():
        vote_counts[target] = vote_counts.get(target, 0) + 1
    
    alive_mafia = get_alive_mafia()
    majority_threshold = math.floor(len(alive_mafia) / 2) + 1
    
    result = {
        "votes": vote_counts,
        "majority_threshold": majority_threshold,
        "alive_mafia_count": len(alive_mafia)
    }
    
    return jsonify(result)

@app.route('/game/advance', methods=['POST'])
def advance_phase():
    global game_state, day_number, day_votes, night_votes, winner
    
    data = request.get_json()
    if not data or 'name' not in data:
        return jsonify({"error": "Name is required"}), 400
    
    name = data['name']
    name_lower = name.lower()
    
    # Find player
    actual_name = None
    for existing_name in players.keys():
        if existing_name.lower() == name_lower:
            actual_name = existing_name
            break
    
    if actual_name is None:
        return jsonify({"error": "Player not found"}), 404
    
    if actual_name != game_starter:
        return jsonify({"error": "Only the game starter can advance phases"}), 400
    
    if game_state == GameState.DAY:
        # Check if there's already a majority
        alive_players = get_alive_players()
        majority_threshold = math.floor(len(alive_players) / 2) + 1
        
        vote_counts = {}
        for target in [p.name for p in alive_players]:
            vote_counts[target] = 0
        vote_counts["no_elimination"] = 0
        
        for voter, target in day_votes.items():
            vote_counts[target] = vote_counts.get(target, 0) + 1
        
        # Check for majority
        eliminated = None
        for target, count in vote_counts.items():
            if count >= majority_threshold:
                if target == "no_elimination":
                    eliminated = None
                else:
                    eliminated = target
                break
        
        if eliminated:
            # Eliminate the player
            players[eliminated].is_alive = False
            eliminated_role = players[eliminated].role.value
            check_result = check_win_conditions()
            if check_result:
                end_game(check_result)
                return jsonify({
                    "message": f"{eliminated} was eliminated (was {eliminated_role})",
                    "winner": check_result,
                    "phase": "ended"
                })
            else:
                game_state = GameState.NIGHT
                night_votes = {}
                return jsonify({
                    "message": f"{eliminated} was eliminated (was {eliminated_role})",
                    "phase": "night"
                })
        else:
            # No majority, no elimination
            check_result = check_win_conditions()
            if check_result:
                end_game(check_result)
                return jsonify({
                    "message": "No elimination, game ended",
                    "winner": check_result,
                    "phase": "ended"
                })
            else:
                game_state = GameState.NIGHT
                night_votes = {}
                return jsonify({
                    "message": "No elimination",
                    "phase": "night"
                })
    
    elif game_state == GameState.NIGHT:
        # Check for mafia majority
        alive_mafia = get_alive_mafia()
        if len(alive_mafia) == 0:
            check_result = check_win_conditions()
            if check_result:
                end_game(check_result)
                return jsonify({
                    "message": "Night ended, game ended",
                    "winner": check_result,
                    "phase": "ended"
                })
            else:
                day_number += 1
                game_state = GameState.DAY
                day_votes = {}
                return jsonify({
                    "message": "Night ended",
                    "day": day_number,
                    "phase": "day"
                })
        
        majority_threshold = math.floor(len(alive_mafia) / 2) + 1
        
        vote_counts = {}
        alive_citizens = get_alive_citizens()
        for target in [p.name for p in alive_citizens]:
            vote_counts[target] = 0
        
        for voter, target in night_votes.items():
            vote_counts[target] = vote_counts.get(target, 0) + 1
        
        # Check for majority
        killed = None
        for target, count in vote_counts.items():
            if count >= majority_threshold:
                killed = target
                break
        
        if killed:
            players[killed].is_alive = False
            killed_role = players[killed].role.value
            check_result = check_win_conditions()
            if check_result:
                end_game(check_result)
                return jsonify({
                    "message": f"{killed} was killed (was {killed_role})",
                    "winner": check_result,
                    "phase": "ended"
                })
            else:
                day_number += 1
                game_state = GameState.DAY
                day_votes = {}
                return jsonify({
                    "message": f"{killed} was killed (was {killed_role})",
                    "day": day_number,
                    "phase": "day"
                })
        else:
            # No majority, check for unique highest vote
            max_votes = max(vote_counts.values()) if vote_counts else 0
            if max_votes > 0:
                highest_voted = [t for t, c in vote_counts.items() if c == max_votes]
                if len(highest_voted) == 1:
                    killed = highest_voted[0]
                    players[killed].is_alive = False
                    killed_role = players[killed].role.value
                    check_result = check_win_conditions()
                    if check_result:
                        end_game(check_result)
                        return jsonify({
                            "message": f"{killed} was killed (was {killed_role})",
                            "winner": check_result,
                            "phase": "ended"
                        })
                    else:
                        day_number += 1
                        game_state = GameState.DAY
                        day_votes = {}
                        return jsonify({
                            "message": f"{killed} was killed (was {killed_role})",
                            "day": day_number,
                            "phase": "day"
                        })
            
            # No kill
            check_result = check_win_conditions()
            if check_result:
                end_game(check_result)
                return jsonify({
                    "message": "No kill, game ended",
                    "winner": check_result,
                    "phase": "ended"
                })
            else:
                day_number += 1
                game_state = GameState.DAY
                day_votes = {}
                return jsonify({
                    "message": "No kill",
                    "day": day_number,
                    "phase": "day"
                })
    
    return jsonify({"error": "Invalid phase to advance"}), 400

@app.route('/game/reveal', methods=['GET'])
def reveal_all_roles():
    global game_state
    
    if game_state != GameState.ENDED:
        return jsonify({"error": "Game has not ended"}), 400
    
    player_list = []
    for p in players.values():
        player_list.append({
            "name": p.name,
            "role": p.role.value,
            "alive": p.is_alive
        })
    
    return jsonify({
        "winner": winner,
        "players": player_list
    })

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001, debug=False)
