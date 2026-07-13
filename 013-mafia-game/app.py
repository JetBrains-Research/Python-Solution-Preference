from flask import Flask, request, jsonify
import random
import re

app = Flask(__name__)

# ---- Game State ----

class GameState:
    def __init__(self):
        self.reset()

    def reset(self):
        self.phase = 'LOBBY'  # LOBBY, DAY, NIGHT, ENDED
        self.players = {}  # name -> {'role': 'CITIZEN'/'MAFIA', 'alive': bool, 'is_starter': bool}
        self.votes = {}    # voter_name -> target_name (or '__NO_ELIMINATION__')
        self.day_number = 0
        self.winner = None  # 'CITIZENS', 'MAFIA', or None

    def alive_players(self):
        return [n for n, p in self.players.items() if p['alive']]

    def mafia_count(self):
        return len([n for n, p in self.players.items() if p['alive'] and p['role'] == 'MAFIA'])

    def citizen_count(self):
        return len([n for n, p in self.players.items() if p['alive'] and p['role'] == 'CITIZEN'])

    def alive_mafia(self):
        return [n for n, p in self.players.items() if p['alive'] and p['role'] == 'MAFIA']

game = GameState()

# ---- Validation ----

def validate_name(name):
    if not isinstance(name, str):
        return False
    if len(name) < 3 or len(name) > 20:
        return False
    return bool(re.fullmatch(r'[A-Za-z0-9 _-]+', name))

def get_player_case_insensitive(name):
    for n in game.players:
        if n.lower() == name.lower():
            return n
    return None

# ---- Game Logic ----

def assign_roles(player_names, starter_name):
    n = len(player_names)
    mafia_count = max(1, n // 3)
    roles = ['MAFIA'] * mafia_count + ['CITIZEN'] * (n - mafia_count)
    random.shuffle(roles)
    game.players = {}
    for name, role in zip(player_names, roles):
        game.players[name] = {
            'role': role,
            'alive': True,
            'is_starter': (name == starter_name)
        }

def check_win_conditions():
    mafia = game.mafia_count()
    citizen = game.citizen_count()
    if mafia == 0:
        game.winner = 'CITIZENS'
        game.phase = 'ENDED'
        game.votes = {}
        return True
    if mafia >= citizen:
        game.winner = 'MAFIA'
        game.phase = 'ENDED'
        game.votes = {}
        return True
    return False

def transition_to_day():
    game.phase = 'DAY'
    game.votes = {}
    game.day_number += 1

def transition_to_night():
    game.phase = 'NIGHT'
    game.votes = {}

def resolve_day():
    alive = game.alive_players()
    tally = {}
    for target in game.votes.values():
        tally[target] = tally.get(target, 0) + 1
    
    majority = (len(alive) // 2) + 1
    eliminated = None
    
    for target, count in tally.items():
        if count >= majority:
            if target == '__NO_ELIMINATION__':
                eliminated = '__NO_ELIMINATION__'
            else:
                eliminated = target
            break
    
    if eliminated and eliminated != '__NO_ELIMINATION__':
        game.players[eliminated]['alive'] = False
    
    result = {
        'eliminated': eliminated if eliminated != '__NO_ELIMINATION__' else None,
        'no_elimination': eliminated == '__NO_ELIMINATION__',
        'tally': tally
    }
    
    if check_win_conditions():
        result['game_ended'] = True
        result['winner'] = game.winner
        result['all_roles'] = {n: p['role'] for n, p in game.players.items()}
    else:
        result['game_ended'] = False
        transition_to_night()
    
    return result

def resolve_night():
    alive_mafia = game.alive_mafia()
    tally = {}
    for voter, target in game.votes.items():
        if voter in alive_mafia:
            tally[target] = tally.get(target, 0) + 1
    
    majority = (len(alive_mafia) // 2) + 1
    killed = None
    
    for target, count in tally.items():
        if count >= majority:
            killed = target
            break
    
    if killed:
        game.players[killed]['alive'] = False
    
    result = {
        'killed': killed,
        'tally': tally
    }
    
    if check_win_conditions():
        result['game_ended'] = True
        result['winner'] = game.winner
        result['all_roles'] = {n: p['role'] for n, p in game.players.items()}
    else:
        result['game_ended'] = False
        transition_to_day()
    
    return result

def resolve_night_manual():
    alive_mafia = game.alive_mafia()
    tally = {}
    for voter, target in game.votes.items():
        if voter in alive_mafia:
            tally[target] = tally.get(target, 0) + 1
    
    if not tally:
        killed = None
    else:
        max_votes = max(tally.values())
        candidates = [t for t, c in tally.items() if c == max_votes]
        if len(candidates) > 1:
            killed = None
        else:
            killed = candidates[0]
            game.players[killed]['alive'] = False
    
    result = {
        'killed': killed,
        'tally': tally
    }
    
    if check_win_conditions():
        result['game_ended'] = True
        result['winner'] = game.winner
        result['all_roles'] = {n: p['role'] for n, p in game.players.items()}
    else:
        result['game_ended'] = False
        transition_to_day()
    
    return result

# ---- Endpoints ----

@app.route('/lobby', methods=['GET'])
def get_lobby():
    return jsonify({
        'phase': game.phase,
        'locked': game.phase not in ('LOBBY', 'ENDED'),
        'players': list(game.players.keys()) if game.phase in ('LOBBY', 'ENDED') else [],
        'can_start': len(game.players) >= 4 if game.phase in ('LOBBY', 'ENDED') else False
    }), 200

@app.route('/lobby/join', methods=['POST'])
def join_lobby():
    if game.phase not in ('LOBBY', 'ENDED'):
        return jsonify({'error': 'Game is in progress, lobby is locked'}), 403
    
    data = request.get_json(silent=True) or {}
    name = data.get('name', '').strip()
    
    if not validate_name(name):
        return jsonify({'error': 'Name must be 3-20 characters, letters/numbers/spaces/hyphens/underscores only'}), 400
    
    if game.phase == 'ENDED':
        game.reset()
    
    if get_player_case_insensitive(name):
        return jsonify({'error': 'Name already taken'}), 409
    
    game.players[name] = {'role': None, 'alive': True, 'is_starter': False}
    return jsonify({
        'name': name,
        'players': list(game.players.keys()),
        'can_start': len(game.players) >= 4
    }), 200

@app.route('/game/start', methods=['POST'])
def start_game():
    if game.phase not in ('LOBBY', 'ENDED'):
        return jsonify({'error': 'Game already in progress'}), 409
    
    data = request.get_json(silent=True) or {}
    starter = (data.get('starter', '') or '').strip()
    
    if game.phase == 'ENDED':
        game.reset()
    
    actual_starter = get_player_case_insensitive(starter)
    if not actual_starter or actual_starter not in game.players:
        return jsonify({'error': 'Starter must be a joined player'}), 400
    
    if len(game.players) < 4:
        return jsonify({'error': 'Need at least 4 players to start'}), 400
    
    player_names = list(game.players.keys())
    assign_roles(player_names, actual_starter)
    game.phase = 'DAY'
    game.day_number = 1
    game.votes = {}
    game.winner = None
    
    return jsonify({
        'started': True,
        'player_count': len(player_names),
        'day': game.day_number
    }), 200

@app.route('/game/state', methods=['GET'])
def get_game_state():
    if game.phase == 'LOBBY':
        return jsonify({
            'phase': 'LOBBY',
            'players': list(game.players.keys())
        }), 200
    
    state = {
        'phase': game.phase,
        'day': game.day_number,
        'players': {
            n: {
                'alive': p['alive'],
                'role': p['role'] if game.phase == 'ENDED' else None
            }
            for n, p in game.players.items()
        },
        'winner': game.winner
    }
    return jsonify(state), 200

@app.route('/player/<name>/role', methods=['GET'])
def get_role(name):
    actual_name = get_player_case_insensitive(name)
    if not actual_name:
        return jsonify({'error': 'Player not found'}), 404
    
    player = game.players[actual_name]
    role = player['role']
    
    response = {
        'name': actual_name,
        'role': role,
        'alive': player['alive']
    }
    
    if role == 'MAFIA':
        teammates = [n for n, p in game.players.items() if p['role'] == 'MAFIA']
        response['teammates'] = teammates
    
    return jsonify(response), 200

@app.route('/vote', methods=['POST'])
def cast_vote():
    data = request.get_json(silent=True) or {}
    voter = (data.get('voter', '') or '').strip()
    target = (data.get('target', '') or '').strip()
    
    actual_voter = get_player_case_insensitive(voter)
    if not actual_voter:
        return jsonify({'error': 'Voter not found'}), 404
    
    if not game.players[actual_voter]['alive']:
        return jsonify({'error': 'Dead players cannot vote'}), 403
    
    if game.phase == 'DAY':
        valid_targets = game.alive_players() + ['__NO_ELIMINATION__']
        actual_target = get_player_case_insensitive(target)
        if actual_target:
            target = actual_target
        if target not in valid_targets:
            return jsonify({'error': 'Invalid target for day vote'}), 400
        
        game.votes[actual_voter] = target
        
        alive = game.alive_players()
        tally = {}
        for v in game.votes.values():
            tally[v] = tally.get(v, 0) + 1
        
        majority = (len(alive) // 2) + 1
        for t, c in tally.items():
            if c >= majority:
                result = resolve_day()
                return jsonify({
                    'vote_recorded': True,
                    'phase_ended': True,
                    'result': result
                }), 200
        
        return jsonify({
            'vote_recorded': True,
            'phase_ended': False,
            'tally': tally,
            'majority': majority
        }), 200
    
    elif game.phase == 'NIGHT':
        if game.players[actual_voter]['role'] != 'MAFIA':
            return jsonify({'error': 'Only mafia can vote during night'}), 403
        
        valid_targets = [n for n, p in game.players.items() if p['alive'] and p['role'] == 'CITIZEN']
        actual_target = get_player_case_insensitive(target)
        if actual_target:
            target = actual_target
        if target not in valid_targets:
            return jsonify({'error': 'Night target must be an alive citizen'}), 400
        
        game.votes[actual_voter] = target
        
        alive_mafia = game.alive_mafia()
        tally = {}
        for m in alive_mafia:
            if m in game.votes:
                t = game.votes[m]
                tally[t] = tally.get(t, 0) + 1
        
        majority = (len(alive_mafia) // 2) + 1
        for t, c in tally.items():
            if c >= majority:
                result = resolve_night()
                return jsonify({
                    'vote_recorded': True,
                    'phase_ended': True,
                    'result': result
                }), 200
        
        return jsonify({
            'vote_recorded': True,
            'phase_ended': False,
            'tally': tally,
            'majority': majority
        }), 200
    
    else:
        return jsonify({'error': 'Cannot vote in current phase'}), 403

@app.route('/votes', methods=['GET'])
def get_votes():
    name = request.args.get('name', '').strip()
    
    if game.phase == 'LOBBY' or game.phase == 'ENDED':
        return jsonify({'votes': {}, 'tally': {}}), 200
    
    if game.phase == 'DAY':
        tally = {}
        for v in game.votes.values():
            tally[v] = tally.get(v, 0) + 1
        return jsonify({
            'votes': game.votes,
            'tally': tally,
            'majority': (len(game.alive_players()) // 2) + 1
        }), 200
    
    elif game.phase == 'NIGHT':
        actual_name = get_player_case_insensitive(name)
        if actual_name and game.players[actual_name]['role'] == 'MAFIA':
            alive_mafia = game.alive_mafia()
            tally = {}
            for m in alive_mafia:
                if m in game.votes:
                    t = game.votes[m]
                    tally[t] = tally.get(t, 0) + 1
            return jsonify({
                'votes': {},
                'tally': tally,
                'majority': (len(alive_mafia) // 2) + 1
            }), 200
        else:
            return jsonify({'votes': {}, 'tally': {}}), 200
    
    return jsonify({'votes': {}, 'tally': {}}), 200

@app.route('/advance', methods=['POST'])
def advance_phase():
    data = request.get_json(silent=True) or {}
    requester = (data.get('requester', '') or '').strip()
    
    actual_requester = get_player_case_insensitive(requester)
    if not actual_requester:
        return jsonify({'error': 'Requester not found'}), 404
    
    if not game.players[actual_requester]['is_starter']:
        return jsonify({'error': 'Only Game Starter can advance phase'}), 403
    
    if game.phase == 'DAY':
        result = resolve_day()
        return jsonify({
            'advanced': True,
            'from': 'DAY',
            'result': result
        }), 200
    
    elif game.phase == 'NIGHT':
        result = resolve_night_manual()
        return jsonify({
            'advanced': True,
            'from': 'NIGHT',
            'result': result
        }), 200
    
    else:
        return jsonify({'error': 'Cannot advance in current phase'}), 403

@app.route('/results', methods=['GET'])
def get_results():
    if game.phase != 'ENDED':
        return jsonify({'error': 'Game has not ended'}), 403
    
    return jsonify({
        'winner': game.winner,
        'players': {
            n: {
                'role': p['role'],
                'alive': p['alive']
            }
            for n, p in game.players.items()
        }
    }), 200

@app.route('/reset', methods=['POST'])
def reset_game():
    game.reset()
    return jsonify({'reset': True}), 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
