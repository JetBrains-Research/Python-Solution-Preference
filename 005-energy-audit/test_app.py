import io, json, os
from app import app, db, Job, ChecklistItem, Photo, User

def run_tests():
    os.remove('energy_audit.db') if os.path.exists('energy_audit.db') else None
    with app.app_context():
        db.create_all()

    client = app.test_client()

    # 1. Register
    r = client.post('/auth/register', json={
        "name": "Auditor One", "email": "a@example.com", "password": "secret123"
    })
    assert r.status_code == 201
    me = client.get('/auth/me')
    assert me.status_code == 200
    assert me.get_json()['email'] == 'a@example.com'

    # 2. Logout + login
    client.post('/auth/logout')
    assert client.get('/auth/me').status_code == 401
    r = client.post('/auth/login', json={"email": "a@example.com", "password": "secret123"})
    assert r.status_code == 200

    # 3. Create job
    job_data = {
        "address": {"street": "123 Main St", "city": "Albany", "state": "NY", "zip": "12203"},
        "builder_name": "Builder Bob",
        "scheduled_date": "2025-01-15",
        "house_volume": 20000.0,
        "conditioned_floor_area": 2500.0,
        "num_stories": 2
    }
    r = client.post('/jobs', json=job_data)
    assert r.status_code == 201
    job_id = r.get_json()['id']

    # 4. List jobs
    r = client.get('/jobs')
    assert len(r.get_json()) == 1
    assert r.get_json()[0]['status'] == 'Pending'

    # 5. Job details
    r = client.get(f'/jobs/{job_id}')
    j = r.get_json()
    assert j['status'] == 'Pending'
    assert len(j['checklist']['items']) == 10
    assert j['checklist']['complete'] is False

    # 6. Update checklist
    updates = [{"item_number": i+1, "status": "Passed" if i < 8 else "N/A"} for i in range(10)]
    r = client.put(f'/jobs/{job_id}/checklist', json={"items": updates})
    r = client.get(f'/jobs/{job_id}')
    j = r.get_json()
    assert j['checklist']['summary'] == "8/8 Passed (100%)"
    assert j['status'] == 'In Progress'

    # 7. Blower door points
    points = [
        {"house_pressure": 50, "fan_pressure": 25, "ring_config": "Ring A"},
        {"house_pressure": 45, "fan_pressure": 20, "ring_config": "Ring A"},
        {"house_pressure": 40, "fan_pressure": 16, "ring_config": "Ring A"},
        {"house_pressure": 35, "fan_pressure": 12, "ring_config": "Ring A"},
        {"house_pressure": 30, "fan_pressure": 9, "ring_config": "Ring A"},
        {"house_pressure": 25, "fan_pressure": 6, "ring_config": "Ring A"},
        {"house_pressure": 20, "fan_pressure": 4, "ring_config": "Ring A"}
    ]
    r = client.post(f'/jobs/{job_id}/blower-door/points', json={"points": points})
    assert r.status_code == 201

    # Blower door calculate
    r = client.post(f'/jobs/{job_id}/blower-door/calculate')
    assert r.status_code == 200
    bd = r.get_json()
    assert 'ach50' in bd
    assert 'cfm50' in bd
    assert 'r_squared' in bd
    assert any('low' in s.lower() or 'correlation' in s.lower() for s in bd['warnings']) == (bd['r_squared'] < 0.98)

    # 8. Duct leakage
    r = client.post(f'/jobs/{job_id}/duct-leakage', json={"test_type_selected": "Both"})
    assert r.status_code == 200

    # choose fan pressures that give low values to pass
    # C for ringA = 635, n=0.5
    # tdl cfm25 = 635 * 4**0.5 = 1270; per100 = (1270*100)/2500 = 50.8 > 4 => fail
    # choose lower fan pressure: 635 * 0.01**0.5 ~63.5; per100 ~2.54 => pass
    dl_data = {
        "tdl": {"ring_config": "Ring A", "fan_pressure": 0.01},
        "dlo": {"house_pressure": -25, "ring_config": "Ring A", "fan_pressure": 0.01}
    }
    r = client.post(f'/jobs/{job_id}/duct-leakage/calculate', json=dl_data)
    assert r.status_code == 200
    dl = r.get_json()
    assert dl['tdl']['compliance'] == 'Pass'
    assert dl['dlo']['compliance'] == 'Pass'
    assert dl['overall_compliance'] == 'Pass'
    assert dl.get('dlo', {}).get('warning') is None

    # DLO with house pressure outside range
    dl_data2 = {
        "tdl": {"ring_config": "Ring A", "fan_pressure": 0.01},
        "dlo": {"house_pressure": -20, "ring_config": "Ring A", "fan_pressure": 0.01}
    }
    r = client.post(f'/jobs/{job_id}/duct-leakage/calculate', json=dl_data2)
    assert r.status_code == 200
    dl2 = r.get_json()
    assert any('house pressure outside' in s.lower() for s in dl2.get('warnings', []))

    # Job should be Completed
    r = client.get(f'/jobs/{job_id}')
    assert r.get_json()['status'] == 'Completed'

    # 9. Photos
    for i in range(11):
        content = bytes([255, 216, 255] + [0]*100)  # minimal jpeg-like header
        r = client.post(f'/jobs/{job_id}/photos',
                        data={'file': (io.BytesIO(content), f'img{i}.jpg', 'image/jpeg')},
                        content_type='multipart/form-data')
        if i < 10:
            assert r.status_code == 201
        else:
            assert r.status_code == 400  # max reached

    r = client.get(f'/jobs/{job_id}/photos')
    assert len(r.get_json()) == 10

    first_photo = r.get_json()[0]
    r = client.get(f'/jobs/{job_id}/photos/{first_photo["id"]}')
    assert r.status_code == 200
    assert r.content_type == 'image/jpeg'

    r = client.delete(f'/jobs/{job_id}/photos/{first_photo["id"]}')
    assert r.status_code == 200
    r = client.get(f'/jobs/{job_id}/photos')
    assert len(r.get_json()) == 9

    # Edge: photo retrieval after delete
    assert client.get(f'/jobs/{job_id}/photos/{first_photo["id"]}').status_code == 404

    print("All tests passed.")

if __name__ == '__main__':
    run_tests()
