# Mafia Game API

A single-room Mafia game backend service with HTTP API.

## Endpoints

### Health Check
- `GET /health` - Returns service status

### Lobby
- `GET /lobby` - Get lobby status and players
- `POST /lobby/join` - Join the lobby (requires JSON body with `name`)
- `POST /lobby/leave` - Leave the lobby (requires JSON body with `name`)

### Game
- `POST /game/start` - Start a new game (requires JSON body with `name` of game starter)
- `GET /game/role?name=<name>` - Get player's role (private)
- `GET /game/status` - Get current game status
- `POST /game/day/vote` - Cast a day vote (requires JSON body with `name` and `target` or `"no_elimination"`)
- `GET /game/day/votes` - Get current day vote tally
- `POST /game/night/vote` - Cast a night vote (mafia only, requires JSON body with `name` and `target`)
- `GET /game/night/votes?name=<name>` - Get night vote tally (mafia only)
- `POST /game/advance` - Advance phase (game starter only, requires JSON body with `name`)
- `GET /game/reveal` - Reveal all roles (game ended only)

## Rules

### Player Names
- 3-20 characters
- Letters, numbers, spaces, hyphens, underscores only
- Unique within lobby (case-insensitive)

### Game Rules
- 4-16 players required to start
- Mafia count = max(1, floor(N/3))
- Day majority threshold = floor(alive_players / 2) + 1
- Night majority threshold = floor(alive_mafia / 2) + 1
- Citizens win when all mafia eliminated
- Mafia win when mafia count >= citizen count
