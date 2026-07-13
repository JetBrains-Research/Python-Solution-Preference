# Mafia Game (MVP) - HTTP API

Single-room Mafia game managed via a Flask HTTP API. No timers, no UI, no chat.
Phases advance on majority votes or manual advancement by the Game Starter.

## Run

    pip install flask
    python app.py

Server listens on 0.0.0.0:5000.

## Endpoints

### Lobby
- GET  /lobby -> {locked, phase, players:[{id,name}], can_start}
- POST /lobby/join  body {name} -> {player_id, name} (201)
    Name: 3-20 chars, letters/numbers/spaces/hyphens/underscores. Case-insensitive uniqueness.
- POST /lobby/reset -> resets state (only when no game active). Utility endpoint.

### Game start
- POST /game/start  body {player_id} -> starts game (any joined player can start).
    Requires 4-16 players. Roles: mafia_count = max(1, floor(N/3)); rest are citizens.
    Caller becomes the Game Starter. Phase becomes day, day = 1.

### State & roles
- GET /game/state -> phase, day, players (dead have role revealed), eliminations, day tally.
- GET /game/role?player_id=X -> {role, mafia_teammates?} (only mafia see teammates).
- GET /game/result -> final result (winner, roles, eliminations) from the most recent finished game.

### Day
- POST /game/day/vote  body {player_id, target}. target is a player id or the string no_elimination.
    Alive players only. Self-votes allowed. Response includes current tally, threshold, resolved flag.
    Reaching floor(alive/2)+1 votes on a single option ends the day immediately.

### Night
- POST /game/night/vote  body {player_id, target}. Only alive mafia; target must be alive citizen.
- GET  /game/night/state?player_id=X -> mafia-only aggregated tally.
- Threshold: floor(aliveMafia/2)+1.

### Advance (Game Starter only)
- POST /game/advance  body {player_id}
    Day: ends day as No Elimination.
    Night: unique highest -> kill; tie or no votes -> no kill.

## Win conditions
- Citizens win when all mafia eliminated.
- Mafia win when mafia count >= citizen count.
- Checked after each day elimination and night resolution.
- On game end: roles revealed via /game/result, lobby unlocked, state reset (last_result preserved).

## Tests

    python test_mafia.py
