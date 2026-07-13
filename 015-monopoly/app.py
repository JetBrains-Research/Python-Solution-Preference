import os
import json
from flask import Flask, request, jsonify

app = Flask(__name__)

class Game:
    def __init__(self):
        # Load board layout
        board_data = os.getenv('BOARD_DATA')
        if not board_data:
            raise RuntimeError('BOARD_DATA env var not set')
        self.board = json.loads(board_data)
        self.board_len = len(self.board)

        # Load properties
        prop_data = os.getenv('PROPERTIES_DATA')
        if not prop_data:
            raise RuntimeError('PROPERTIES_DATA env var not set')
        prop_list = json.loads(prop_data)
        self.properties = {}
        for p in prop_list:
            p['owner'] = None
            self.properties[p['id']] = p

        # Load dice sequence
        dice_seq = os.getenv('DICE_MOVES')
        if not dice_seq:
            raise RuntimeError('DICE_MOVES env var not set')
        self.dice_moves = [int(x) for x in dice_seq.split(',') if x.strip()]
        if not self.dice_moves:
            raise RuntimeError('DICE_MOVES must contain at least one value')
        self.dice_index = 0

        # Game state
        self.players = {}          # name -> dict
        self.turn_order = []       # list of player names
        self.current_turn_idx = 0
        self.game_started = False
        self.game_over = False
        self.winner = None

        # Find GO payout (assumes at least one GO)
        self.go_payout = 0
        for space in self.board:
            if space.get('type') == 'GO':
                self.go_payout = space.get('payout', 0)
                break

    def start(self, player_names):
        if not (2 <= len(player_names) <= 4):
            raise ValueError('Player count must be between 2 and 4')
        if len(set(player_names)) != len(player_names):
            raise ValueError('Player names must be unique')
        self.players = {}
        for name in player_names:
            self.players[name] = {
                'cash': 500,
                'position': 0,   # start on GO (index 0)
                'status': 'Active',
                'skip': False,
                'properties': []
            }
        self.turn_order = player_names[:]
        self.current_turn_idx = 0
        self.game_started = True
        self.game_over = False
        self.winner = None

    def _current_player_name(self):
        if not self.turn_order:
            return None
        return self.turn_order[self.current_turn_idx]

    def _advance_turn(self):
        if not self.turn_order:
            return
        start_idx = self.current_turn_idx
        while True:
            self.current_turn_idx = (self.current_turn_idx + 1) % len(self.turn_order)
            pname = self.turn_order[self.current_turn_idx]
            if self.players[pname]['status'] == 'Active':
                break
            if self.current_turn_idx == start_idx:
                # No active players left
                break

    def _consume_dice(self):
        val = self.dice_moves[self.dice_index]
        self.dice_index = (self.dice_index + 1) % len(self.dice_moves)
        return val

    def _handle_bankruptcy(self, pname):
        player = self.players[pname]
        # Release properties
        for pid in player['properties']:
            if pid in self.properties:
                self.properties[pid]['owner'] = None
        player['properties'] = []
        player['cash'] = 0
        player['status'] = 'Eliminated'
        player['skip'] = False

    def _check_game_over(self):
        active = [p for p in self.players.values() if p['status'] == 'Active']
        if len(active) == 1:
            self.game_over = True
            self.winner = [name for name, info in self.players.items() if info['status'] == 'Active'][0]

    def turn(self):
        if not self.game_started or self.game_over:
            return {'error': 'Game not started or already finished'}

        pname = self._current_player_name()
        player = self.players[pname]

        # Skip eliminated players automatically
        if player['status'] != 'Active':
            self._advance_turn()
            return {'message': f'Player {pname} is eliminated, turn passed'}

        # Handle skip flag
        if player['skip']:
            player['skip'] = False
            self._advance_turn()
            return {'player': pname, 'action': 'skip_turn'}

        # Roll dice
        dice = self._consume_dice()
        old_pos = player['position']
        new_pos = (old_pos + dice) % self.board_len
        passed_go = (old_pos + dice) >= self.board_len

        # Apply GO payout if passed or landed
        if passed_go or self.board[new_pos].get('type') == 'GO':
            player['cash'] += self.go_payout

        player['position'] = new_pos
        landed_space = self.board[new_pos]
        action_details = {'player': pname, 'rolled': dice, 'moved_to': new_pos, 'space': landed_space}

        # Resolve space effects
        stype = landed_space.get('type')
        if stype == 'GO':
            # Already gave payout above
            pass
        elif stype == 'PROPERTY':
            pid = landed_space.get('propertyId')
            prop = self.properties.get(pid)
            if prop:
                owner = prop.get('owner')
                if owner is None:
                    # Auto-buy if affordable
                    if player['cash'] >= prop['price']:
                        player['cash'] -= prop['price']
                        prop['owner'] = pname
                        player['properties'].append(pid)
                        action_details['property_action'] = f'bought {pid}'
                elif owner != pname:
                    rent = prop.get('rent', 0)
                    if player['cash'] >= rent:
                        player['cash'] -= rent
                        self.players[owner]['cash'] += rent
                        action_details['property_action'] = f'paid rent {rent} to {owner}'
                    else:
                        # Bankruptcy
                        self._handle_bankruptcy(pname)
                        action_details['bankruptcy'] = True
        elif stype == 'JAIL':
            player['skip'] = True
            action_details['jail'] = 'skip_next_turn_set'
        elif stype == 'TAX':
            amount = landed_space.get('amount', 0)
            if player['cash'] >= amount:
                player['cash'] -= amount
                action_details['tax'] = f'paid {amount}'
            else:
                self._handle_bankruptcy(pname)
                action_details['bankruptcy'] = True
        elif stype == 'FREE_PARKING':
            pass  # nothing

        # After processing, check for game over
        self._check_game_over()

        # Advance turn if player still active
        if player['status'] == 'Active':
            self._advance_turn()

        # Include game status
        action_details['game_over'] = self.game_over
        if self.game_over:
            action_details['winner'] = self.winner

        return action_details

    def get_state(self):
        state = {
            'players': self.players,
            'turn': self._current_player_name(),
            'game_over': self.game_over,
            'winner': self.winner
        }
        return state

# Global game instance
game = None


@app.route('/game/start', methods=['POST'])
def start():
    data = request.get_json()
    if not data or 'players' not in data:
        return jsonify({'error': 'players list required'}), 400
    global game
    if game is None:
        try:
            game = Game()
        except Exception as e:
            return jsonify({'error': str(e)}), 400
    try:
        game.start(data['players'])
    except Exception as e:
        return jsonify({'error': str(e)}), 400
    return jsonify({'status': 'game_started'})

@app.route('/game/state', methods=['GET'])
def state():
    if game is None:
        return jsonify({'error': 'Game not initialized'}), 400
    return jsonify(game.get_state())

@app.route('/game/turn', methods=['POST'])
def turn():
    if game is None:
        return jsonify({'error': 'Game not initialized'}), 400
    result = game.turn()
    if 'error' in result:
        return jsonify(result), 400
    return jsonify(result)