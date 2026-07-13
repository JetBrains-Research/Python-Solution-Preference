import requests
import json
import time
import sys
import subprocess
import os

BASE = "http://127.0.0.1:5001"
TOKENS = {}
USER_IDS = {}

def req(method, path, token=None, json_data=None, params=None):
    headers = {}
    if token:
        headers['Authorization'] = f'Bearer {token}'
    url = BASE + path
    if method == 'GET':
        r = requests.get(url, headers=headers, params=params, timeout=5)
    elif method == 'POST':
        r = requests.post(url, headers=headers, json=json_data, timeout=5)
    elif method == 'PATCH':
        r = requests.patch(url, headers=headers, json=json_data, timeout=5)
    elif method == 'DELETE':
        r = requests.delete(url, headers=headers, timeout=5)
    else:
        raise ValueError(method)
    return r

def register(email, password):
    r = req('POST', '/register', json_data={'email': email, 'password': password})
    if r.status_code != 201:
        print("Register failed for", email, r.status_code, r.text)
        sys.exit(1)
    d = r.json()
    TOKENS[email] = d['token']
    USER_IDS[email] = d['user_id']
    return d

def complete_profile(email, username, display_name, birth_date=None):
    return req('POST', '/profile', token=TOKENS[email], json_data={
        'username': username, 'display_name': display_name, 'birth_date': birth_date
    })

def login(email, password):
    r = req('POST', '/login', json_data={'email': email, 'password': password})
    if r.status_code == 200:
        d = r.json()
        TOKENS[email] = d['token']
        USER_IDS[email] = d['user_id']
    return r

def post(email, caption=None, images=None):
    return req('POST', '/posts', token=TOKENS[email], json_data={'caption': caption, 'images': images or []})

def get_feed(email):
    return req('GET', '/feed', token=TOKENS[email])

def search(email, q):
    return req('GET', '/search', token=TOKENS[email], params={'q': q})

def send_request(email, recipient_id, rel_type):
    return req('POST', '/relationships/request', token=TOKENS[email], json_data={'recipient_id': recipient_id, 'type': rel_type})

def accept_req(email, rel_id):
    return req('POST', f'/relationships/{rel_id}/accept', token=TOKENS[email])

def decline_req(email, rel_id):
    return req('POST', f'/relationships/{rel_id}/decline', token=TOKENS[email])

def cancel_req(email, rel_id):
    return req('POST', f'/relationships/{rel_id}/cancel', token=TOKENS[email])

def end_rel(email, rel_id):
    return req('POST', f'/relationships/{rel_id}/end', token=TOKENS[email])

def profile(email, user_id):
    return req('GET', f'/profile/{user_id}', token=TOKENS[email])

def active_rels(email):
    return req('GET', '/relationships/active', token=TOKENS[email])

def past_rels(email):
    return req('GET', '/relationships/past', token=TOKENS[email])

def delete_account(email):
    return req('DELETE', '/account', token=TOKENS[email])

errors = []

def assert_ok(r, msg):
    if r.status_code >= 400:
        print("FAIL", msg, r.status_code, r.text)
        errors.append(msg)
        return False
    return True

def assert_equal(a, b, msg):
    if a != b:
        print("FAIL", msg, ": expected", b, "got", a)
        errors.append(msg)
        return False
    return True

proc = subprocess.Popen([sys.executable, 'app.py'], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
time.sleep(1.5)

try:
    r = req('GET', '/health')
    assert assert_ok(r, 'health')

    register('alice@test.com', 'password123')
    register('bob@test.com', 'password123')
    register('charlie@test.com', 'password123')

    r = login('alice@test.com', 'wrongpassword')
    assert assert_equal(r.status_code, 401, 'login_wrong_password')

    r = req('GET', '/feed', token=TOKENS['alice@test.com'])
    assert assert_equal(r.status_code, 403, 'feed_before_profile')

    r = complete_profile('alice@test.com', 'alice_user', 'Alice', '1990-05-20')
    assert assert_ok(r, 'complete_alice')
    r = complete_profile('bob@test.com', 'bob_user', 'Bob')
    assert assert_ok(r, 'complete_bob')
    r = complete_profile('charlie@test.com', 'charlie_user', 'Charlie')
    assert assert_ok(r, 'complete_charlie')

    dup_data = register("dup@test.com", "password123")
    TOKENS['dup@test.com'] = dup_data['token']
    r = req('POST', '/profile', token=TOKENS['dup@test.com'], json_data={'username':'alice_user','display_name':'Dup'})
    assert assert_equal(r.status_code, 409, 'dup_username')

    r = req('POST', '/profile', token=TOKENS['dup@test.com'], json_data={'username':'dup_user','display_name':'Dup', 'birth_date':'2099-01-01'})
    assert assert_equal(r.status_code, 400, 'future_birth_date')

    r = send_request('alice@test.com', USER_IDS['bob@test.com'], 'Parent')
    rel_id = None
    if r.status_code == 201:
        rel_id = r.json().get('relationship_id')
    if not rel_id:
        inc = req('GET','/relationships/incoming',token=TOKENS['bob@test.com']).json()
        rel_id = inc[0]['id']
    assert assert_ok(r, 'send_request')

    r = req('GET','/relationships/incoming',token=TOKENS['bob@test.com'])
    inc = r.json()
    assert assert_equal(len(inc), 1, 'incoming_count')
    assert assert_equal(inc[0]['type'], 'Parent', 'incoming_type')
    assert assert_equal(inc[0]['reciprocal_type'], 'Child', 'incoming_reciprocal')

    r = send_request('alice@test.com', USER_IDS['bob@test.com'], 'Sibling')
    assert assert_equal(r.status_code, 409, 'duplicate_request')

    r = accept_req('bob@test.com', rel_id)
    assert assert_ok(r, 'accept')

    r = active_rels('alice@test.com')
    active = r.json()
    assert assert_equal(len(active.get('Parent', [])), 1, 'active_parent_count')
    assert assert_equal(active['Parent'][0]['username'], 'bob_user', 'active_username')

    r = search('alice@test.com', 'bo')
    sres = r.json()
    usernames = [x['username'] for x in sres]
    assert assert_equal('bob_user' in usernames, True, 'search_bob')
    assert assert_equal('charlie_user' in usernames, False, 'search_not_charlie')

    r = post('alice@test.com', caption='Hello world', images=['img1.png'])
    assert assert_ok(r, 'post_alice')
    post_id = r.json()['post_id']

    r = get_feed('bob@test.com')
    feed = r.json()
    assert assert_equal(len(feed), 1, 'feed_count')
    assert assert_equal(feed[0]['caption'], 'Hello world', 'feed_caption')

    r = profile('bob@test.com', USER_IDS['alice@test.com'])
    prof = r.json()
    assert assert_equal(prof.get('birth_date'), '1990-05-20', 'birth_date_visible')
    assert assert_equal(len(prof.get('posts', [])), 1, 'posts_visible')

    r = profile('charlie@test.com', USER_IDS['alice@test.com'])
    prof = r.json()
    assert assert_equal(prof.get('birth_date'), None, 'birth_date_hidden')
    posts = prof.get('posts')
    if posts is not None:
        assert assert_equal(len(posts), 0, 'posts_hidden')

    r = end_rel('bob@test.com', rel_id)
    assert assert_ok(r, 'end_rel')

    r = get_feed('bob@test.com')
    feed = r.json()
    assert assert_equal(len(feed), 0, 'feed_after_end')

    r = past_rels('bob@test.com')
    past = r.json()
    assert assert_equal(len(past), 1, 'past_count')
    assert assert_equal(past[0]['status'], 'Ended', 'past_status')
    assert assert_equal(past[0]['other_user_name'], 'alice_user', 'past_name')

    r = send_request('alice@test.com', USER_IDS['bob@test.com'], 'Spouse')
    assert assert_ok(r, 'new_request_after_end')

    inc = req('GET','/relationships/incoming',token=TOKENS['bob@test.com']).json()
    rel_id2 = inc[0]['id']
    r = decline_req('bob@test.com', rel_id2)
    assert assert_ok(r, 'decline')

    r = send_request('alice@test.com', USER_IDS['charlie@test.com'], 'Sibling')
    assert assert_ok(r, 'send_to_charlie')
    out = req('GET','/relationships/outgoing',token=TOKENS['alice@test.com']).json()
    rel_id3 = out[0]['id']
    r = cancel_req('alice@test.com', rel_id3)
    assert assert_ok(r, 'cancel')

    r = past_rels('charlie@test.com')
    past_charlie = r.json()
    assert assert_equal(len(past_charlie), 1, 'past_charlie_count')
    assert assert_equal(past_charlie[0]['status'], 'Canceled', 'charlie_past_status')

    r = post('alice@test.com', caption='Original', images=[])
    post_id2 = r.json()['post_id']
    r = req('PATCH', f'/posts/{post_id2}', token=TOKENS['alice@test.com'], json_data={'caption':'Updated'})
    assert assert_ok(r, 'edit_post')
    r = req('GET', f'/posts/{post_id2}', token=TOKENS['alice@test.com'])
    assert assert_equal(r.json()['caption'], 'Updated', 'edited_caption')

    r = req('DELETE', f'/posts/{post_id2}', token=TOKENS['alice@test.com'])
    assert assert_ok(r, 'delete_post')

    r = send_request('alice@test.com', USER_IDS['bob@test.com'], 'Spouse')
    assert assert_ok(r, 'readd_bob')
    inc = req('GET','/relationships/incoming',token=TOKENS['bob@test.com']).json()
    rel_id4 = inc[0]['id']
    r = accept_req('bob@test.com', rel_id4)
    assert assert_ok(r, 'reaccept_bob')

    r = delete_account('alice@test.com')
    assert assert_ok(r, 'delete_account')

    r = past_rels('bob@test.com')
    past = r.json()
    alice_past = [p for p in past if p['other_user_name'] == 'Deleted User']
    assert assert_equal(len(alice_past) >= 1, True, 'deleted_user_in_past')

    r = active_rels('bob@test.com')
    active = r.json()
    total = sum(len(v) for v in active.values())
    assert assert_equal(total, 0, 'active_after_delete')

    print("All tests passed!" if not errors else f"{len(errors)} tests failed.")
    sys.exit(0 if not errors else 1)

finally:
    proc.terminate()
    proc.wait()
