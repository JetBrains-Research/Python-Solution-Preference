from flask import Flask, request, jsonify
import os
import json

app = Flask(__name__)

# Game state
game_state = {
    'initialized': False,
    'players': [],
    'current_turn_index': 0,
    'dice_index': 0,
    'board': [],
    'properties': {},
    'dice_moves': []
}

def load_config():
    """Load configuration from environment variables"""
    board_data = os.environ.get('BOARD_DATA', '[]')
    properties_data = os.environ.get('PROPERTIES_DATA', '[]')
    dice_moves = os.environ.get('DICE_MOVES', '')
    
    game_state['board'] = json.loads(board_data)
    game_state['properties'] = {p['id']: p for p in json.loads(properties_data)}
    game_state['dice_moves'] = [int(x.strip()) for x in dice_moves.split(',') if x.strip()]

def get_next_dice():
    """Get next dice value, cycling through the sequence"""
    if not game_state['dice_moves']:
        return 1
    dice_value = game_state['dice_moves'][game_state['dice_index']]
    game_state['dice_index'] = (game_state['dice_index'] + 1) % len(game_state['dice_moves'])
    return dice_value

def get_active_players():
    """Get list of active players"""
    return [p for p in game_state['players'] if p['status'] == 'Active']

def get_next_player_index():
    """Get index of next active player"""
    active_players = get_active_players()
    if not active_players:
        return 0
    
    current_idx = game_state['current_turn_index']
    players = game_state['players']
    
    # Find next active player
    for i in range(len(players)):
        idx = (current_idx + i) % len(players)
        if players[idx]['status'] == 'Active':
            return idx
    return current_idx

def handle_bankruptcy(player):
    """Handle player bankruptcy"""
    player['status'] = 'Eliminated'
    player['cash'] = 0
    # Unown all properties
    for prop_id in player.get('properties', []):
        for space in game_state['board']:
            if space['type'] == 'PROPERTY' and space.get('propertyId') == prop_id:
                space['owner'] = None
    player['properties'] = []

def check_game_over():
    """Check if game is over (only one active player remains)"""
    active = get_active_players()
    return len(active) <= 1

@app.route('/health', methods=['GET'])
def health():
    return jsonify({'status': 'ok'})

@app.route('/game/init', methods=['POST'])
def init_game():
    """Initialize a new game with player names"""
    data = request.get_json()
    
    if not data or 'players' not in data:
        return jsonify({'error': 'Players list required'}), 400
    
    players = data['players']
    
    # Validate players
    if not isinstance(players, list):
        return jsonify({'error': 'Players must be a list'}), 400
    
    if len(players) < 2 or len(players) > 4:
        return jsonify({'error': 'Must have 2-4 players'}), 400
    
    # Check for unique, non-empty names
    names = set()
    for p in players:
        if not p or not isinstance(p, str) or not p.strip():
            return jsonify({'error': 'Player names must be non-empty strings'}), 400
        if p in names:
            return jsonify({'error': 'Player names must be unique'}), 400
        names.add(p)
    
    # Load configuration
    load_config()
    
    # Initialize game state
    game_state['players'] = []
    for name in players:
        game_state['players'].append({
            'name': name,
            'cash': 500,
            'position': 0,
            'status': 'Active',
            'properties': [],
            'skip_next_turn': False
        })
    
    # Reset board ownership
    for space in game_state['board']:
        if space['type'] == 'PROPERTY':
            space['owner'] = None
    
    game_state['current_turn_index'] = 0
    game_state['dice_index'] = 0
    game_state['initialized'] = True
    
    return jsonify({'message': 'Game initialized', 'players': [p['name'] for p in game_state['players']]})

@app.route('/game/state', methods=['GET'])
def get_game_state():
    """Get current game state"""
    if not game_state['initialized']:
        return jsonify({'error': 'Game not initialized'}), 400
    
    active_players = get_active_players()
    if not active_players:
        return jsonify({'error': 'No active players'}), 400
    
    current_player = active_players[0]
    
    return jsonify({
        'players': [{
            'name': p['name'],
            'cash': p['cash'],
            'position': p['position'],
            'status': p['status'],
            'properties': p['properties']
        } for p in game_state['players']],
        'currentTurn': current_player['name'],
        'gameOver': check_game_over()
    })

@app.route('/game/roll', methods=['POST'])
def roll_dice():
    """Current player rolls dice and moves"""
    if not game_state['initialized']:
        return jsonify({'error': 'Game not initialized'}), 400
    
    active_players = get_active_players()
    if not active_players:
        return jsonify({'error': 'No active players'}), 400
    
    current_player_idx = get_next_player_index()
    current_player = game_state['players'][current_player_idx]
    
    # Check skip flag
    if current_player['skip_next_turn']:
        current_player['skip_next_turn'] = False
        game_state['current_turn_index'] = (current_player_idx + 1) % len(game_state['players'])
        return jsonify({
            'message': f"{current_player['name']} skipped turn",
            'position': current_player['position']
        })
    
    # Roll dice
    dice_value = get_next_dice()
    
    # Move player
    old_position = current_player['position']
    board_size = len(game_state['board'])
    new_position = (old_position + dice_value) % board_size
    
    # Check if passed GO
    passed_go = new_position <= old_position and dice_value > 0
    landed_on_go = new_position == 0
    
    current_player['position'] = new_position
    
    # Handle GO payout
    if passed_go or landed_on_go:
        go_space = game_state['board'][0]
        payout = go_space.get('payout', 200)
        current_player['cash'] += payout
    
    # Resolve space effect
    space = game_state['board'][new_position]
    space_type = space['type']
    message = f"{current_player['name']} rolled {dice_value}, moved to {space_type}"
    
    if space_type == 'GO':
        pass  # Already handled payout
    
    elif space_type == 'PROPERTY':
        prop_id = space.get('propertyId')
        prop = game_state['properties'].get(prop_id)
        
        if space['owner'] is None:
            # Unowned - player can buy or pass (auto-buy for MVP)
            if current_player['cash'] >= prop['price']:
                current_player['cash'] -= prop['price']
                current_player['properties'].append(prop_id)
                space['owner'] = current_player['name']
                message = f"{current_player['name']} bought {prop['name']} for ${prop['price']}"
            else:
                message = f"{current_player['name']} passed on {prop['name']}"
        elif space['owner'] == current_player['name']:
            message = f"{current_player['name']} landed on own property {prop['name']}"
        else:
            # Pay rent
            rent = prop['rent']
            if current_player['cash'] < rent:
                handle_bankruptcy(current_player)
                message = f"{current_player['name']} went bankrupt!"
            else:
                current_player['cash'] -= rent
                # Find owner and give rent
                for p in game_state['players']:
                    if p['name'] == space['owner']:
                        p['cash'] += rent
                        break
                message = f"{current_player['name']} paid ${rent} rent to {space['owner']}"
    
    elif space_type == 'JAIL':
        current_player['skip_next_turn'] = True
        message = f"{current_player['name']} sent to JAIL, will skip next turn"
    
    elif space_type == 'TAX':
        tax_amount = space.get('amount', 0)
        if current_player['cash'] < tax_amount:
            handle_bankruptcy(current_player)
            message = f"{current_player['name']} went bankrupt from ${tax_amount} tax!"
        else:
            current_player['cash'] -= tax_amount
            message = f"{current_player['name']} paid ${tax_amount} tax"
    
    elif space_type == 'FREE_PARKING':
        message = f"{current_player['name']} landed on FREE PARKING"
    
    # Check if eliminated
    if current_player['status'] == 'Eliminated':
        game_state['current_turn_index'] = (current_player_idx + 1) % len(game_state['players'])
        return jsonify({
            'message': message,
            'position': current_player['position'],
            'dice': dice_value,
            'eliminated': True
        })
    
    # Move to next player
    game_state['current_turn_index'] = (current_player_idx + 1) % len(game_state['players'])
    
    return jsonify({
        'message': message,
        'position': current_player['position'],
        'dice': dice_value,
        'cash': current_player['cash']
    })

@app.route('/game/buy', methods=['POST'])
def buy_property():
    """Player attempts to buy current property"""
    if not game_state['initialized']:
        return jsonify({'error': 'Game not initialized'}), 400
    
    active_players = get_active_players()
    if not active_players:
        return jsonify({'error': 'No active players'}), 400
    
    current_player_idx = get_next_player_index()
    current_player = game_state['players'][current_player_idx]
    
    space = game_state['board'][current_player['position']]
    
    if space['type'] != 'PROPERTY':
        return jsonify({'error': 'Not on a property space'}), 400
    
    if space['owner'] is not None:
        return jsonify({'error': 'Property already owned'}), 400
    
    prop_id = space.get('propertyId')
    prop = game_state['properties'].get(prop_id)
    
    if current_player['cash'] < prop['price']:
        return jsonify({'error': 'Insufficient funds'}), 400
    
    current_player['cash'] -= prop['price']
    current_player['properties'].append(prop_id)
    space['owner'] = current_player['name']
    
    return jsonify({
        'message': f"{current_player['name']} bought {prop['name']}",
        'cash': current_player['cash']
    })

@app.route('/game/pass', methods=['POST'])
def pass_turn():
    """Player passes on buying property"""
    if not game_state['initialized']:
        return jsonify({'error': 'Game not initialized'}), 400
    
    active_players = get_active_players()
    if not active_players:
        return jsonify({'error': 'No active players'}), 400
    
    current_player_idx = get_next_player_index()
    current_player = game_state['players'][current_player_idx]
    
    space = game_state['board'][current_player['position']]
    
    if space['type'] != 'PROPERTY' or space['owner'] is not None:
        return jsonify({'error': 'Cannot pass - no property to pass on'}), 400
    
    return jsonify({
        'message': f"{current_player['name']} passed on buying property",
        'position': current_player['position']
    })

@app.route('/game/winner', methods=['GET'])
def get_winner():
    """Get game winner and final standings"""
    if not game_state['initialized']:
        return jsonify({'error': 'Game not initialized'}), 400
    
    active_players = get_active_players()
    
    if len(active_players) > 1:
        return jsonify({'error': 'Game not over'}), 400
    
    if len(active_players) == 1:
        winner = active_players[0]
        return jsonify({
            'winner': winner['name'],
            'standings': [{
                'name': p['name'],
                'cash': p['cash'],
                'properties': p['properties'],
                'status': p['status']
            } for p in game_state['players']]
        })
    
    return jsonify({'error': 'No players remain'}), 400

@app.route('/game/reset', methods=['POST'])
def reset_game():
    """Reset game state"""
    game_state['initialized'] = False
    game_state['players'] = []
    game_state['current_turn_index'] = 0
    game_state['dice_index'] = 0
    
    return jsonify({'message': 'Game reset'})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001, debug=False)
