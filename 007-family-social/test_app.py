from app import app, users, email_index, username_index, relationships, posts

def reset():
    users.clear(); email_index.clear(); username_index.clear(); relationships.clear(); posts.clear()

def signup_and_complete(client, email, username, display_name):
    r = client.post('/api/signup', json={'email': email, 'password': 'password123'})
    assert r.status_code == 201, r.get_json()
    r = client.put('/api/profile', json={'username': username, 'display_name': display_name})
    assert r.status_code == 200, r.get_json()
    return r.get_json()

def test_full_flow():
    reset()
    alice = app.test_client()
    bob = app.test_client()
    a = signup_and_complete(alice, 'alice@x.com', 'alice', 'Alice')
    b = signup_and_complete(bob, 'bob@x.com', 'bob', 'Bob')
    r = alice.get('/api/search?q=bob')
    assert r.status_code == 200
    results = r.get_json()
    assert any(u['username'] == 'bob' for u in results)
    bob_id = b['id']
    r = alice.post('/api/relationships/requests', json={'user_id': bob_id, 'type': 'Parent'})
    assert r.status_code == 201, r.get_json()
    rel_id = r.get_json()['id']
    r = alice.post('/api/relationships/requests', json={'user_id': bob_id, 'type': 'Parent'})
    assert r.status_code == 400
    r = bob.get('/api/relationships')
    data = r.get_json()
    assert len(data['incoming']) == 1
    assert data['incoming'][0]['type'] == 'Parent'
    r = bob.post(f'/api/relationships/{rel_id}/accept')
    assert r.status_code == 200
    r = alice.post('/api/posts', json={'caption': 'hello', 'images': []})
    assert r.status_code == 201
    post_id = r.get_json()['id']
    r = bob.get('/api/feed')
    assert r.status_code == 200
    posts_ = r.get_json()
    assert any(p['id'] == post_id for p in posts_)
    r = bob.get(f'/api/posts/{post_id}')
    assert r.status_code == 200
    anon = app.test_client()
    r = anon.get(f'/api/posts/{post_id}')
    assert r.status_code == 403
    charlie = app.test_client()
    signup_and_complete(charlie, 'c@x.com', 'charlie', 'C')
    r = charlie.get(f'/api/posts/{post_id}')
    assert r.status_code == 403
    r = charlie.get('/api/feed')
    assert all(p['id'] != post_id for p in r.get_json())
    r = alice.post(f'/api/relationships/{rel_id}/end')
    assert r.status_code == 200
    r = bob.get(f'/api/posts/{post_id}')
    assert r.status_code == 403
    r = alice.post('/api/relationships/requests', json={'user_id': bob_id, 'type': 'Sibling'})
    assert r.status_code == 201
    r = alice.get('/api/relationships')
    data = r.get_json()
    assert any(p['past_status'] == 'Ended' for p in data['past'])
    print('full flow passed')

def test_signup_validation():
    reset()
    c = app.test_client()
    r = c.post('/api/signup', json={'email': 'a@b.com', 'password': 'short'})
    assert r.status_code == 400
    r = c.post('/api/signup', json={'email': 'noatsign', 'password': 'longenough'})
    assert r.status_code == 400
    r = c.post('/api/signup', json={'email': 'a@b.com', 'password': 'longenough'})
    assert r.status_code == 201
    c2 = app.test_client()
    r = c2.post('/api/signup', json={'email': 'A@B.COM', 'password': 'longenough'})
    assert r.status_code == 400
    r = c.get('/api/feed')
    assert r.status_code == 403
    c3 = app.test_client()
    r = c3.post('/api/login', json={'email': 'a@b.com', 'password': 'wrong123'})
    assert r.status_code == 401
    assert 'invalid credentials' in r.get_json()['error']
    r = c3.post('/api/login', json={'email': 'nobody@x.com', 'password': 'wrong123'})
    assert r.status_code == 401
    print('signup validation passed')

def test_self_request():
    reset()
    c = app.test_client()
    u = signup_and_complete(c, 'a@x.com', 'aaa1', 'A1')
    r = c.post('/api/relationships/requests', json={'user_id': u['id'], 'type': 'Sibling'})
    assert r.status_code == 400
    print('self request blocked')

def test_post_constraints():
    reset()
    c = app.test_client()
    signup_and_complete(c, 'a@x.com', 'aaa1', 'A1')
    r = c.post('/api/posts', json={'caption': '', 'images': []})
    assert r.status_code == 400
    r = c.post('/api/posts', json={'caption': '', 'images': ['a','b','c','d','e']})
    assert r.status_code == 400
    r = c.post('/api/posts', json={'caption': 'hi', 'images': ['a']})
    assert r.status_code == 201
    pid = r.get_json()['id']
    r = c.put(f'/api/posts/{pid}', json={'caption': 'edited'})
    assert r.status_code == 200
    assert r.get_json()['caption'] == 'edited'
    r = c.delete(f'/api/posts/{pid}')
    assert r.status_code == 200
    print('post constraints passed')

def test_deleted_user():
    reset()
    alice = app.test_client()
    bob = app.test_client()
    signup_and_complete(alice, 'a@x.com', 'alice', 'A')
    b = signup_and_complete(bob, 'b@x.com', 'bob', 'B')
    r = alice.post('/api/relationships/requests', json={'user_id': b['id'], 'type': 'Sibling'})
    rid = r.get_json()['id']
    bob.post(f'/api/relationships/{rid}/accept')
    r = bob.delete('/api/account')
    assert r.status_code == 200
    r = alice.get('/api/relationships')
    data = r.get_json()
    assert any(p['other_display_name'] == 'Deleted User' for p in data['past']), data
    print('deleted user passed')

def test_reciprocal_type_view():
    reset()
    alice = app.test_client()
    bob = app.test_client()
    signup_and_complete(alice, 'a@x.com', 'alice', 'A')
    b = signup_and_complete(bob, 'b@x.com', 'bob', 'B')
    # Alice says Bob is her parent
    r = alice.post('/api/relationships/requests', json={'user_id': b['id'], 'type': 'Parent'})
    rid = r.get_json()['id']
    bob.post(f'/api/relationships/{rid}/accept')
    r = alice.get('/api/relationships')
    active = r.get_json()['active']
    assert active[0]['type'] == 'Parent'
    r = bob.get('/api/relationships')
    active = r.get_json()['active']
    assert active[0]['type'] == 'Child'
    print('reciprocal type view passed')

def test_birthdate_visibility():
    reset()
    alice = app.test_client()
    bob = app.test_client()
    a = signup_and_complete(alice, 'a@x.com', 'alice', 'A')
    b = signup_and_complete(bob, 'b@x.com', 'bob', 'B')
    alice.put('/api/profile', json={'birth_date': '1990-01-01'})
    # Bob (no rel) cannot see birth_date
    r = bob.get(f"/api/users/{a['id']}")
    assert 'birth_date' not in r.get_json()
    # Add relationship
    r = alice.post('/api/relationships/requests', json={'user_id': b['id'], 'type': 'Sibling'})
    rid = r.get_json()['id']
    bob.post(f'/api/relationships/{rid}/accept')
    r = bob.get(f"/api/users/{a['id']}")
    assert r.get_json().get('birth_date') == '1990-01-01'
    # Future birth date rejected
    r = alice.put('/api/profile', json={'birth_date': '2999-01-01'})
    assert r.status_code == 400
    print('birthdate visibility passed')

if __name__ == '__main__':
    test_full_flow()
    test_signup_validation()
    test_self_request()
    test_post_constraints()
    test_deleted_user()
    test_reciprocal_type_view()
    test_birthdate_visibility()
    print('ALL OK')
