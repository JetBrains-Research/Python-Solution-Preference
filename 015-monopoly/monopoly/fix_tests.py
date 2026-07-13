import re

with open('test_game.py', 'r') as f:
    content = f.read()

# Fix the helper function name
content = content.replace('def post(url, json_data):', 'def post_json(url, json_data):')

# Fix all the calls to post( that are meant for json posts
# We need to replace post(f".../game/new", ...) style calls with post_json
# But we also need to fix calls that use post without json data (like /game/roll, /game/buy, /game/pass)
# Those should be requests.post without json

lines = content.split('\n')
new_lines = []
for line in lines:
    # Replace calls like: resp = post_json(f"{BASE_URL}/game/roll")
    # But we need those to be: resp = requests.post(f"{BASE_URL}/game/roll")
    # Actually post_json is for json posts, so /game/new should use post_json
    # /game/roll, /game/buy, /game/pass have no body, use requests.post
    
    # Replace post_json calls that should be requests.post (no body)
    if 'post_json(f"{BASE_URL}/game/roll")' in line:
        line = line.replace('post_json(f"{BASE_URL}/game/roll")', 'requests.post(f"{BASE_URL}/game/roll")')
    elif 'post_json(f"{BASE_URL}/game/buy")' in line:
        line = line.replace('post_json(f"{BASE_URL}/game/buy")', 'requests.post(f"{BASE_URL}/game/buy")')
    elif 'post_json(f"{BASE_URL}/game/pass")' in line:
        line = line.replace('post_json(f"{BASE_URL}/game/pass")', 'requests.post(f"{BASE_URL}/game/pass")')
    
    new_lines.append(line)

with open('test_game.py', 'w') as f:
    f.write('\n'.join(new_lines))

print("Fixed")
