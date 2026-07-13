import os
import json

# Set environment variables before importing the Flask app
os.environ['BOARD_DATA'] = json.dumps([
    {"index": 0, "type": "GO", "payout": 200},
    {"index": 1, "type": "PROPERTY", "propertyId": 1},
    {"index": 2, "type": "TAX", "amount": 100},
    {"index": 3, "type": "JAIL"},
    {"index": 4, "type": "FREE_PARKING"},
    {"index": 5, "type": "PROPERTY", "propertyId": 2}
])

os.environ['PROPERTIES_DATA'] = json.dumps([
    {"id": 1, "name": "Mediterranean Avenue", "price": 60, "rent": 2},
    {"id": 2, "name": "Baltic Avenue", "price": 60, "rent": 4}
])

os.environ['DICE_MOVES'] = "3,4,2,5,6,1"

# Now import the Flask app and game instance
from app import app, game

# Reinitialize the game after setting env vars (game is None at import)
if game is None:
    # The start endpoint will create the Game instance, so no need to call __init__ here
    pass

client = app.test_client()

# Start a new game with two players
resp = client.post('/game/start', json={"players": ["Alice", "Bob"]})
print('Start response:', resp.json)

# Perform first turn (Alice)
resp = client.post('/game/turn')
print('Turn 1 response:', resp.json)

# Perform second turn (Bob)
resp = client.post('/game/turn')
print('Turn 2 response:', resp.json)

# Get current game state
resp = client.get('/game/state')
print('Current state:', json.dumps(resp.json, indent=2))
