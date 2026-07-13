import json
import sys
sys.path.insert(0, '.')
from app import app, game

cli = app.test_client()

def reset():
    game.reset()

def join(name):
    resp = cli.post('/lobby/join', data=json.dumps({'name': name}), content_type='application/json')
    return json.loads(resp.data), resp.status_code

def start(starter):
    resp = cli.post('/game/start', data=json.dumps({'starter': starter}), content_type='application/json')
    return json.loads(resp.data), resp.status_code

def get_role(name):
    resp = cli.get(f'/player/{name}/role')
    return json.loads(resp.data), resp.status_code

def vote(voter, target):
    resp = cli.post('/vote', data=json.dumps({'voter': voter, 'target': target}), content_type='application/json')
    return json.loads(resp.data), resp.status_code

def advance(requester):
    resp = cli.post('/advance', data=json.dumps({'requester': requester}), content_type='application/json')
    return json.loads(resp.data), resp.status_code

def get_state():
    return json.loads(cli.get('/game/state').data)

def get_results():
    return json.loads(cli.get('/results').data)

# === Test 1: Citizens win ===
print("=== Test 1: Citizens win ===")
reset()
for name in ['Alice', 'Bob', 'Carol', 'Dave']:
    r, s = join(name)
    assert s == 200, f"Join {name} failed: {s} {r}"

r, s = start('Alice')
assert s == 200, f"Start failed: {s} {r}"

roles = {}
for name in ['Alice', 'Bob', 'Carol', 'Dave']:
    r, s = get_role(name)
    assert s == 200, f"Get role {name} failed: {s} {r}"
    roles[name] = r['role']

print(f"Roles: {roles}")
mafia_players = [n for n, r in roles.items() if r == 'MAFIA']
citizens = [n for n, r in roles.items() if r == 'CITIZEN']

for name in citizens:
    vote(name, mafia_players[0])

state = get_state()
assert state['phase'] == 'ENDED'
assert state['winner'] == 'CITIZENS'
print("Test 1 PASSED")

# === Test 2: Mafia win via parity ===
print("\n=== Test 2: Mafia win via parity ===")
reset()
names = ['Alpha', 'Beta', 'Gamma', 'Delta', 'Epsilon', 'Zeta']
for name in names:
    r, s = join(name)
    assert s == 200, f"Join {name} failed: {s} {r}"

r, s = start('Alpha')
assert s == 200, f"Start failed: {s} {r}"

roles = {}
for name in names:
    r, s = get_role(name)
    assert s == 200, f"Get role {name} failed: {s} {r}"
    roles[name] = r['role']

print(f"Roles: {roles}")
mafia_players = [n for n, r in roles.items() if r == 'MAFIA']
citizens = [n for n, r in roles.items() if r == 'CITIZEN']

for name in names:
    r, s = vote(name, '__NO_ELIMINATION__')
    assert s == 200, f"Vote {name} failed: {s} {r}"
    if r.get('phase_ended'):
        break

state = get_state()
assert state['phase'] == 'NIGHT', f"Expected NIGHT, got {state}"

for m in mafia_players:
    r, s = vote(m, citizens[0])
    assert s == 200, f"Mafia vote {m} failed: {s} {r}"
    if r.get('phase_ended'):
        break

state = get_state()
assert state['phase'] == 'DAY', f"Expected DAY, got {state}"
assert state['day'] == 2

for name in names:
    if game.players[name]['alive']:
        r, s = vote(name, '__NO_ELIMINATION__')
        assert s == 200, f"Vote {name} failed: {s} {r}"
        if r.get('phase_ended'):
            break

state = get_state()
assert state['phase'] == 'NIGHT', f"Expected NIGHT, got {state}"

remaining_citizens = [n for n in game.players if game.players[n]['alive'] and game.players[n]['role'] == 'CITIZEN']
for m in mafia_players:
    if game.players[m]['alive']:
        r, s = vote(m, remaining_citizens[0])
        assert s == 200, f"Mafia vote {m} failed: {s} {r}"
        if r.get('phase_ended'):
            break

state = get_state()
print(f"Final: phase={state['phase']}, winner={state.get('winner')}, mafia={game.mafia_count()}, citizens={game.citizen_count()}")
assert state['phase'] == 'ENDED', f"Expected ENDED, got {state} with mafia={game.mafia_count()}, citizens={game.citizen_count()}"
assert state['winner'] == 'MAFIA'
print("Test 2 PASSED")

# === Test 3: Manual advance day (no majority) ===
print("\n=== Test 3: Manual advance day ===")
reset()
for name in ['Alice', 'Bob', 'Carol', 'Dave']:
    r, s = join(name)
    assert s == 200

r, s = start('Alice')
assert s == 200

r, s = vote('Alice', 'Bob')
assert s == 200

r, s = advance('Alice')
assert s == 200, f"Advance failed: {s} {r}"
assert r['result']['eliminated'] is None
state = get_state()
assert state['phase'] == 'NIGHT'
print("Test 3 PASSED")

# === Test 4: Manual advance night (no votes) ===
print("\n=== Test 4: Manual advance night no votes ===")
reset()
for name in ['Alice', 'Bob', 'Carol', 'Dave']:
    r, s = join(name)
    assert s == 200

r, s = start('Alice')
assert s == 200

r, s = advance('Alice')
assert s == 200

r, s = advance('Alice')
assert s == 200, f"Advance night failed: {s} {r}"
assert r['result']['killed'] is None
state = get_state()
assert state['phase'] == 'DAY'
assert state['day'] == 2
print("Test 4 PASSED")

# === Test 5: Lobby lock and reopen ===
print("\n=== Test 5: Lobby lock and reopen ===")
reset()
for name in ['Alice', 'Bob', 'Carol', 'Dave']:
    r, s = join(name)
    assert s == 200

r, s = start('Alice')
assert s == 200

lobby = json.loads(cli.get('/lobby').data)
assert lobby['locked'] == True, f"Expected locked: {lobby}"

roles = {}
for name in ['Alice', 'Bob', 'Carol', 'Dave']:
    r, s = get_role(name)
    assert s == 200
    roles[name] = r['role']

mafia_players = [n for n, r in roles.items() if r == 'MAFIA']
citizens = [n for n, r in roles.items() if r == 'CITIZEN']
for c in citizens:
    r, s = vote(c, mafia_players[0])
    if r.get('phase_ended'):
        break

lobby = json.loads(cli.get('/lobby').data)
assert lobby['locked'] == False, f"Expected reopened: {lobby}"
print("Test 5 PASSED")

# === Test 6: Night vote visibility ===
print("\n=== Test 6: Night vote visibility ===")
reset()
# Use 7 players for 2 mafia so votes dont immediately end night
names = ['Alice', 'Bob', 'Carol', 'Dave', 'Eve', 'Frank', 'Grace']
for name in names:
    r, s = join(name)
    assert s == 200

r, s = start('Alice')
assert s == 200

roles = {}
for name in names:
    r, s = get_role(name)
    assert s == 200
    roles[name] = r['role']

# Advance to night
for name in names:
    r, s = vote(name, '__NO_ELIMINATION__')
    if r.get('phase_ended'):
        break

state = get_state()
assert state['phase'] == 'NIGHT'

mafia_players = [n for n, r in roles.items() if r == 'MAFIA']
citizens = [n for n, r in roles.items() if r == 'CITIZEN']
print(f"Mafia: {mafia_players}")

# One mafia votes - should NOT end night because need floor(2/2)+1 = 2 votes
r, s = vote(mafia_players[0], citizens[0])
assert s == 200
assert r['phase_ended'] == False, f"Night should not end yet: {r}"

# Now check vote visibility DURING night
vc = json.loads(cli.get(f'/votes?name={citizens[0]}').data)
print(f"Citizen sees votes: {vc}")
assert vc['tally'] == {}, f"Citizen saw votes: {vc}"

vm = json.loads(cli.get(f'/votes?name={mafia_players[0]}').data)
print(f"Mafia sees votes: {vm}")
assert vm['tally'] != {}, f"Mafia saw no votes: {vm}"
assert citizens[0] in vm['tally']

# Second mafia votes - ends night
r, s = vote(mafia_players[1], citizens[0])
assert s == 200
assert r['phase_ended'] == True

print("Test 6 PASSED")

# === Test 7: Case insensitive names ===
print("\n=== Test 7: Case insensitive ===")
reset()
r, s = join('Alice')
assert s == 200

r, s = join('alice')
assert r == {'error': 'Name already taken'}

r, s = join('ALICE')
assert r == {'error': 'Name already taken'}

for name in ['Bob', 'Carol', 'Dave']:
    r, s = join(name)
    assert s == 200

r, s = start('dave')
assert s == 200
assert r['started'] == True

r, s = get_role('BOB')
assert s == 200
assert r['name'] == 'Bob'

r, s = get_role('NonExistent')
assert s == 404
print("Test 7 PASSED")

# === Test 8: Dead player cannot vote ===
print("\n=== Test 8: Dead player cannot vote ===")
reset()
for name in ['Alice', 'Bob', 'Carol', 'Dave']:
    r, s = join(name)
    assert s == 200

r, s = start('Alice')
assert s == 200

roles = {}
for name in ['Alice', 'Bob', 'Carol', 'Dave']:
    r, s = get_role(name)
    assert s == 200
    roles[name] = r['role']

mafia_players = [n for n, r in roles.items() if r == 'MAFIA']
citizens = [n for n, r in roles.items() if r == 'CITIZEN']

for c in citizens:
    if c != 'Bob':
        r, s = vote(c, mafia_players[0])
        assert s == 200

vote(mafia_players[0], 'Bob')
vote(citizens[0], 'Bob')
vote(citizens[1], 'Bob')

r, s = vote('Bob', 'Alice')
assert r == {'error': 'Dead players cannot vote'}
print("Test 8 PASSED")

# === Test 9: Self-vote ===
print("\n=== Test 9: Self-vote ===")
reset()
for name in ['Alice', 'Bob', 'Carol', 'Dave']:
    r, s = join(name)
    assert s == 200

r, s = start('Alice')
assert s == 200

r, s = vote('Alice', 'Alice')
assert s == 200
assert r['vote_recorded'] == True
print("Test 9 PASSED")

# === Test 10: Night tie ===
print("\n=== Test 10: Night tie ===")
reset()
for name in ['Alice', 'Bob', 'Carol', 'Dave', 'Eve', 'Frank']:
    r, s = join(name)
    assert s == 200

r, s = start('Alice')
assert s == 200

roles = {}
for name in ['Alice', 'Bob', 'Carol', 'Dave', 'Eve', 'Frank']:
    r, s = get_role(name)
    assert s == 200
    roles[name] = r['role']

# No elimination day
for name in ['Alice', 'Bob', 'Carol', 'Dave', 'Eve', 'Frank']:
    r, s = vote(name, '__NO_ELIMINATION__')
    assert s == 200
    if r.get('phase_ended'):
        break

state = get_state()
assert state['phase'] == 'NIGHT'

current_mafia = [n for n in game.players if game.players[n]['alive'] and game.players[n]['role'] == 'MAFIA']
current_citizens = [n for n in game.players if game.players[n]['alive'] and game.players[n]['role'] == 'CITIZEN']
print(f"Mafia: {current_mafia}")

if len(current_mafia) >= 2:
    vote(current_mafia[0], current_citizens[0])
    vote(current_mafia[1], current_citizens[1])

# Let any alive mafia to vote too
for m in current_mafia:
    if game.players[m]['alive']:
        r, s = vote(m, current_citizens[0])
        if r.get('phase_ended'):
            break

r, s = advance('Alice')
assert s == 200

state = get_state()
if state['phase'] == 'NIGHT':
    r, s = advance('Alice')
    assert s == 200
    assert r['result']['killed'] is None

state = get_state()
assert state['phase'] == 'DAY'
print("Test 10 PASSED")

# === Test 11: Role assignment ===
print("\n=== Test 11: Role assignment ===")
reset()
names = ['P01', 'P02', 'P03', 'P04', 'P05', 'P06', 'P07', 'P08', 'P09']
for name in names:
    r, s = join(name)
    assert s == 200

r, s = start('P01')
assert s == 200

roles = {}
for name in names:
    r, s = get_role(name)
    assert s == 200
    roles[name] = r['role']

mafia_count = sum(1 for r in roles.values() if r == 'MAFIA')
assert mafia_count == 3, f"Expected 3 mafia, got {mafia_count}"
print("Test 11 PASSED")

# === Test 12: No Elimination majority ===
print("\n=== Test 12: No Elimination majority ===")
reset()
for name in ['Alice', 'Bob', 'Carol', 'Dave']:
    r, s = join(name)
    assert s == 200

r, s = start('Alice')
assert s == 200

r, s = vote('Alice', '__NO_ELIMINATION__')
assert s == 200
r, s = vote('Bob', '__NO_ELIMINATION__')
assert s == 200
r, s = vote('Carol', '__NO_ELIMINATION__')
assert s == 200
assert r['phase_ended'] == True
assert r['result']['no_elimination'] == True
assert r['result']['eliminated'] is None
state = get_state()
assert state['phase'] == 'NIGHT'
print("Test 12 PASSED")

# === Test 13: Invalid names ===
print("\n=== Test 13: Invalid names ===")
reset()
r, s = join('AB')
assert s == 400
assert 'error' in r
r, s = join('A' * 21)
assert s == 400
r, s = join('A@lice')
assert s == 400
r, s = join('Valid Name-123_456')
assert s == 200
assert r.get('name') == 'Valid Name-123_456'
print("Test 13 PASSED")

print("\n=== ALL TESTS PASSED ===")
