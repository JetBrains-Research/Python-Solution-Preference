import os
import json
import hashlib
import secrets
import math
from datetime import datetime, timezone
from flask import Flask, request, jsonify, session
from functools import wraps
import base64

app = Flask(__name__)
app.secret_key = secrets.token_hex(32)

# Load seed data
with open('assets/mvp-seed-data.json', 'r') as f:
    SEED_DATA = json.load(f)

# In-memory storage
USERS = {}
JOBS = {}
SESSIONS = {}
PHOTOS = {}

# Photo storage directory
PHOTO_DIR = 'uploads'
os.makedirs(PHOTO_DIR, exist_ok=True)


def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()


def get_current_utc():
    return datetime.now(timezone.utc).isoformat()


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            return jsonify({'error': 'Authentication required'}), 401
        return f(*args, **kwargs)
    return decorated


def round_half_up(value):
    return int(math.floor(value + 0.5))


def calculate_regression(x_values, y_values):
    """Calculate log-log regression: y = a * x^n
    Returns: CFM50, n-factor, R-squared
    """
    n_points = len(x_values)
    if n_points < 2:
        return None, None, None
    
    # Log-log transformation
    log_x = [math.log(p) for p in x_values]
    log_y = [math.log(cfm) for cfm in y_values]
    
    # Linear regression on log-log data
    sum_x = sum(log_x)
    sum_y = sum(log_y)
    sum_xy = sum(log_x[i] * log_y[i] for i in range(n_points))
    sum_xx = sum(px * px for px in log_x)
    
    denominator = n_points * sum_xx - sum_x * sum_x
    if denominator == 0:
        return None, None, None
    
    n_factor = (n_points * sum_xy - sum_x * sum_y) / denominator
    intercept = (sum_y - n_factor * sum_x) / n_points
    
    # Calculate CFM50
    cfm50 = math.exp(intercept + n_factor * math.log(50))
    
    # Calculate R-squared
    mean_y = sum_y / n_points
    ss_tot = sum((ly - mean_y) ** 2 for ly in log_y)
    y_pred = [intercept + n_factor * lx for lx in log_x]
    ss_res = sum((log_y[i] - y_pred[i]) ** 2 for i in range(n_points))
    
    if ss_tot == 0:
        r_squared = 1.0
    else:
        r_squared = 1 - (ss_res / ss_tot)
    
    return cfm50, n_factor, r_squared


# ==================== USER ACCOUNT ====================

@app.route('/api/register', methods=['POST'])
def register():
    data = request.get_json()
    
    if not data:
        return jsonify({'error': 'Invalid request'}), 400
    
    name = data.get('name')
    email = data.get('email')
    password = data.get('password')
    
    if not all([name, email, password]):
        return jsonify({'error': 'Missing required fields'}), 400
    
    if email in USERS:
        return jsonify({'error': 'Email already registered'}), 409
    
    user_id = secrets.token_hex(16)
    USERS[email] = {
        'id': user_id,
        'name': name,
        'email': email,
        'password': hash_password(password)
    }
    
    # Auto-login
    session['user_id'] = user_id
    session['email'] = email
    
    return jsonify({
        'message': 'Registration successful',
        'user': {
            'id': user_id,
            'name': name,
            'email': email
        }
    }), 201


@app.route('/api/login', methods=['POST'])
def login():
    data = request.get_json()
    
    if not data:
        return jsonify({'error': 'Invalid request'}), 400
    
    email = data.get('email')
    password = data.get('password')
    
    if not all([email, password]):
        return jsonify({'error': 'Missing required fields'}), 400
    
    if email not in USERS:
        return jsonify({'error': 'Invalid credentials'}), 401
    
    user = USERS[email]
    if user['password'] != hash_password(password):
        return jsonify({'error': 'Invalid credentials'}), 401
    
    session['user_id'] = user['id']
    session['email'] = email
    
    return jsonify({
        'message': 'Login successful',
        'user': {
            'id': user['id'],
            'name': user['name'],
            'email': user['email']
        }
    })


@app.route('/api/logout', methods=['POST'])
def logout():
    session.clear()
    return jsonify({'message': 'Logout successful'})


@app.route('/api/user', methods=['GET'])
@login_required
def get_user():
    email = session.get('email')
    user = USERS.get(email)
    return jsonify({
        'id': user['id'],
        'name': user['name'],
        'email': user['email']
    })


# ==================== JOB MANAGEMENT ====================

@app.route('/api/jobs', methods=['POST'])
@login_required
def create_job():
    data = request.get_json()
    
    if not data:
        return jsonify({'error': 'Invalid request'}), 400
    
    address = data.get('address')
    builder = data.get('builder')
    scheduled_date = data.get('scheduledDate')
    house_volume = data.get('houseVolume')
    conditioned_area = data.get('conditionedArea')
    
    if not all([address, builder, scheduled_date, house_volume, conditioned_area]):
        return jsonify({'error': 'Missing required fields'}), 400
    
    job_id = secrets.token_hex(16)
    email = session.get('email')
    
    job = {
        'id': job_id,
        'userId': USERS[email]['id'],
        'address': address,
        'builder': builder,
        'scheduledDate': scheduled_date,
        'houseVolume': house_volume,
        'conditionedArea': conditioned_area,
        'numStories': data.get('numStories'),
        'surfaceArea': data.get('surfaceArea'),
        'status': 'Pending',
        'createdAt': get_current_utc(),
        'checklist': {
            'items': []
        },
        'blowerDoor': {
            'ringConfiguration': {},
            'testPoints': [],
            'results': None
        },
        'ductLeakage': {
            'tests': []
        },
        'photos': []
    }
    
    # Initialize checklist items from template
    for item in SEED_DATA['checklistTemplate']['items']:
        job['checklist']['items'].append({
            'itemNumber': item['itemNumber'],
            'title': item['title'],
            'status': 'Not Started'
        })
    
    JOBS[job_id] = job
    
    return jsonify({
        'message': 'Job created successfully',
        'job': job
    }), 201


@app.route('/api/jobs', methods=['GET'])
@login_required
def list_jobs():
    email = session.get('email')
    user_id = USERS[email]['id']
    
    user_jobs = [job for job in JOBS.values() if job['userId'] == user_id]
    # Sort by creation date, most recent first
    user_jobs.sort(key=lambda x: x['createdAt'], reverse=True)
    
    result = []
    for job in user_jobs:
        result.append({
            'id': job['id'],
            'address': job['address'],
            'builder': job['builder'],
            'scheduledDate': job['scheduledDate'],
            'status': job['status']
        })
    
    return jsonify({'jobs': result})


def update_job_status(job):
    """Update job status based on completion criteria."""
    checklist = job.get('checklist', {})
    blower_door = job.get('blowerDoor', {})
    duct_leakage = job.get('ductLeakage', {})
    
    # Check checklist completion
    checklist_items = checklist.get('items', [])
    checklist_complete = all(
        item.get('status') != 'Not Started' 
        for item in checklist_items
    )
    
    # Check blower door completion
    test_points = blower_door.get('testPoints', [])
    results = blower_door.get('results')
    blower_complete = len(test_points) >= 5 and results is not None
    
    # Check duct leakage completion
    tests = duct_leakage.get('tests', [])
    duct_complete = any(test.get('calculated') for test in tests)
    
    if checklist_complete and blower_complete and duct_complete:
        job['status'] = 'Completed'
    elif checklist_complete or blower_complete or duct_complete:
        job['status'] = 'In Progress'
    else:
        job['status'] = 'Pending'


@app.route('/api/jobs/<job_id>', methods=['GET'])
@login_required
def get_job(job_id):
    if job_id not in JOBS:
        return jsonify({'error': 'Job not found'}), 404
    
    job = JOBS[job_id]
    email = session.get('email')
    if job['userId'] != USERS[email]['id']:
        return jsonify({'error': 'Access denied'}), 403
    
    # Calculate checklist summary
    checklist_items = job['checklist']['items']
    passed = sum(1 for item in checklist_items if item['status'] == 'Passed')
    applicable = sum(1 for item in checklist_items if item['status'] != 'N/A')
    
    if applicable > 0:
        pass_rate = round_half_up((passed / applicable) * 100)
    else:
        pass_rate = 0
    
    job['checklist']['summary'] = {
        'passed': passed,
        'applicable': applicable,
        'passRate': pass_rate
    }
    
    return jsonify(job)


# ==================== CHECKLIST ====================

@app.route('/api/jobs/<job_id>/checklist', methods=['GET'])
@login_required
def get_checklist(job_id):
    if job_id not in JOBS:
        return jsonify({'error': 'Job not found'}), 404
    
    job = JOBS[job_id]
    email = session.get('email')
    if job['userId'] != USERS[email]['id']:
        return jsonify({'error': 'Access denied'}), 403
    
    return jsonify(job['checklist'])


@app.route('/api/jobs/<job_id>/checklist', methods=['PUT'])
@login_required
def update_checklist(job_id):
    if job_id not in JOBS:
        return jsonify({'error': 'Job not found'}), 404
    
    job = JOBS[job_id]
    email = session.get('email')
    if job['userId'] != USERS[email]['id']:
        return jsonify({'error': 'Access denied'}), 403
    
    data = request.get_json()
    if not data or 'items' not in data:
        return jsonify({'error': 'Invalid request'}), 400
    
    # Update item statuses
    for item_data in data['items']:
        item_num = item_data.get('itemNumber')
        new_status = item_data.get('status')
        
        if new_status not in ['Not Started', 'Passed', 'Failed', 'N/A']:
            return jsonify({'error': f'Invalid status: {new_status}'}), 400
        
        for item in job['checklist']['items']:
            if item['itemNumber'] == item_num:
                item['status'] = new_status
                break
    
    update_job_status(job)
    
    # Recalculate summary
    checklist_items = job['checklist']['items']
    passed = sum(1 for item in checklist_items if item['status'] == 'Passed')
    applicable = sum(1 for item in checklist_items if item['status'] != 'N/A')
    
    if applicable > 0:
        pass_rate = round_half_up((passed / applicable) * 100)
    else:
        pass_rate = 0
    
    job['checklist']['summary'] = {
        'passed': passed,
        'applicable': applicable,
        'passRate': pass_rate
    }
    
    return jsonify(job['checklist'])


# ==================== BLOWER DOOR TEST ====================

@app.route('/api/jobs/<job_id>/blower-door', methods=['GET'])
@login_required
def get_blower_door(job_id):
    if job_id not in JOBS:
        return jsonify({'error': 'Job not found'}), 404
    
    job = JOBS[job_id]
    email = session.get('email')
    if job['userId'] != USERS[email]['id']:
        return jsonify({'error': 'Access denied'}), 403
    
    return jsonify(job['blowerDoor'])


@app.route('/api/jobs/<job_id>/blower-door', methods=['PUT'])
@login_required
def update_blower_door(job_id):
    if job_id not in JOBS:
        return jsonify({'error': 'Job not found'}), 404
    
    job = JOBS[job_id]
    email = session.get('email')
    if job['userId'] != USERS[email]['id']:
        return jsonify({'error': 'Access denied'}), 403
    
    data = request.get_json()
    if not data:
        return jsonify({'error': 'Invalid request'}), 400
    
    # Update ring configuration
    if 'ringConfiguration' in data:
        job['blowerDoor']['ringConfiguration'] = data['ringConfiguration']
    
    # Update test points
    if 'testPoints' in data:
        job['blowerDoor']['testPoints'] = data['testPoints']
    
    # Calculate if requested
    if data.get('calculate'):
        test_points = job['blowerDoor']['testPoints']
        
        if len(test_points) < 5:
            return jsonify({'error': 'At least 5 test points required for calculation'}), 400
        
        house_pressures = []
        cfm_values = []
        calibration = SEED_DATA['constants']['blowerDoorCalibration']
        
        for point in test_points:
            house_pressure = point.get('housePressure')
            fan_pressure = point.get('fanPressure')
            ring = point.get('ring')
            
            if house_pressure is None or fan_pressure is None or ring is None:
                return jsonify({'error': 'Invalid test point data'}), 400
            
            if ring not in calibration:
                return jsonify({'error': f'Invalid ring configuration: {ring}'}), 400
            
            cal = calibration[ring]
            cfm = cal['C'] * (fan_pressure ** cal['n'])
            
            house_pressures.append(house_pressure)
            cfm_values.append(cfm)
        
        cfm50, n_factor, r_squared = calculate_regression(house_pressures, cfm_values)
        
        if cfm50 is None:
            return jsonify({'error': 'Calculation failed'}), 500
        
        ach50 = (cfm50 * 60) / job['houseVolume']
        
        results = {
            'cfm50': cfm50,
            'ach50': ach50,
            'nFactor': n_factor,
            'rSquared': r_squared,
            'compliance': ach50 <= 3.0
        }
        
        if r_squared < 0.98:
            results['warning'] = 'Low correlation coefficient (R² < 0.98)'
        
        job['blowerDoor']['results'] = results
    
    update_job_status(job)
    
    return jsonify(job['blowerDoor'])


# ==================== DUCT LEAKAGE TEST ====================

@app.route('/api/jobs/<job_id>/duct-leakage', methods=['GET'])
@login_required
def get_duct_leakage(job_id):
    if job_id not in JOBS:
        return jsonify({'error': 'Job not found'}), 404
    
    job = JOBS[job_id]
    email = session.get('email')
    if job['userId'] != USERS[email]['id']:
        return jsonify({'error': 'Access denied'}), 403
    
    return jsonify(job['ductLeakage'])


@app.route('/api/jobs/<job_id>/duct-leakage', methods=['PUT'])
@login_required
def update_duct_leakage(job_id):
    if job_id not in JOBS:
        return jsonify({'error': 'Job not found'}), 404
    
    job = JOBS[job_id]
    email = session.get('email')
    if job['userId'] != USERS[email]['id']:
        return jsonify({'error': 'Access denied'}), 403
    
    data = request.get_json()
    if not data:
        return jsonify({'error': 'Invalid request'}), 400
    
    tests = data.get('tests', [])
    calibration = SEED_DATA['constants']['ductBlasterCalibration']
    
    calculated_tests = []
    all_pass = True
    
    for test in tests:
        test_type = test.get('type')
        ring = test.get('ring')
        fan_pressure = test.get('fanPressure')
        house_pressure = test.get('housePressure')
        
        if test_type not in ['TDL', 'DLO', 'Both']:
            return jsonify({'error': f'Invalid test type: {test_type}'}), 400
        
        if ring not in calibration:
            return jsonify({'error': f'Invalid ring configuration: {ring}'}), 400
        
        if fan_pressure is None:
            return jsonify({'error': 'Fan pressure required'}), 400
        
        if test_type == 'DLO' and house_pressure is None:
            return jsonify({'error': 'House pressure required for DLO test'}), 400
        
        cal = calibration[ring]
        cfm25 = cal['C'] * (fan_pressure ** cal['n'])
        cfm25_per_100 = (cfm25 * 100) / job['conditionedArea']
        
        result = {
            'type': test_type,
            'ring': ring,
            'fanPressure': fan_pressure,
            'cfm25': cfm25,
            'cfm25Per100SqFt': cfm25_per_100,
            'calculated': True
        }
        
        if test_type in ['TDL', 'Both']:
            tdl_pass = cfm25_per_100 <= 4.0
            result['tdlCompliance'] = tdl_pass
            if not tdl_pass:
                all_pass = False
        
        if test_type in ['DLO', 'Both']:
            dlo_pass = cfm25_per_100 <= 3.0
            result['dloCompliance'] = dlo_pass
            if not dlo_pass:
                all_pass = False
            
            if house_pressure < -27 or house_pressure > -23:
                result['warning'] = 'House pressure outside recommended range (-27 to -23 Pa)'
        
        result['compliance'] = all_pass
        calculated_tests.append(result)
    
    job['ductLeakage']['tests'] = calculated_tests
    
    update_job_status(job)
    
    return jsonify(job['ductLeakage'])


# ==================== PHOTOS ====================

@app.route('/api/jobs/<job_id>/photos', methods=['GET'])
@login_required
def get_photos(job_id):
    if job_id not in JOBS:
        return jsonify({'error': 'Job not found'}), 404
    
    job = JOBS[job_id]
    email = session.get('email')
    if job['userId'] != USERS[email]['id']:
        return jsonify({'error': 'Access denied'}), 403
    
    return jsonify({'photos': job['photos']})


@app.route('/api/jobs/<job_id>/photos', methods=['POST'])
@login_required
def upload_photo(job_id):
    if job_id not in JOBS:
        return jsonify({'error': 'Job not found'}), 404
    
    job = JOBS[job_id]
    email = session.get('email')
    if job['userId'] != USERS[email]['id']:
        return jsonify({'error': 'Access denied'}), 403
    
    if len(job['photos']) >= 10:
        return jsonify({'error': 'Maximum 10 photos per job'}), 400
    
    # Check for file upload or base64 data
    if 'photo' in request.files:
        file = request.files['photo']
        if file.filename == '':
            return jsonify({'error': 'No file selected'}), 400
        
        allowed_extensions = ['jpg', 'jpeg', 'png', 'webp']
        ext = file.filename.rsplit('.', 1)[1].lower() if '.' in file.filename else ''
        
        if ext not in allowed_extensions:
            return jsonify({'error': 'Only JPEG, PNG, and WebP files are allowed'}), 400
        
        photo_id = secrets.token_hex(16)
        filename = f"{photo_id}.{ext}"
        filepath = os.path.join(PHOTO_DIR, filename)
        file.save(filepath)
        
        photo = {
            'id': photo_id,
            'filename': filename,
            'uploadedAt': get_current_utc()
        }
        job['photos'].append(photo)
        PHOTOS[photo_id] = filepath
        
    elif request.data:
        # Handle base64 encoded image
        try:
            content = request.get_json()
            if not content or 'data' not in content:
                return jsonify({'error': 'Invalid request'}), 400
            
            # Decode base64
            import re
            match = re.match(r'^data:image/(?:png|jpeg|webp);base64,([^,]+)$', content['data'])
            if not match:
                return jsonify({'error': 'Invalid image data format'}), 400
            
            image_data = base64.b64decode(match.group(1))
            
            # Determine extension from content type
            ext_map = {'png': 'png', 'jpeg': 'jpg', 'webp': 'webp'}
            ext = ext_map.get(match.group(0).split(';')[0].split('/')[1], 'jpg')
            
            photo_id = secrets.token_hex(16)
            filename = f"{photo_id}.{ext}"
            filepath = os.path.join(PHOTO_DIR, filename)
            
            with open(filepath, 'wb') as f:
                f.write(image_data)
            
            photo = {
                'id': photo_id,
                'filename': filename,
                'uploadedAt': get_current_utc()
            }
            job['photos'].append(photo)
            PHOTOS[photo_id] = filepath
            
        except Exception as e:
            return jsonify({'error': 'Failed to process image'}), 400
    else:
        return jsonify({'error': 'No photo data provided'}), 400
    
    return jsonify({
        'message': 'Photo uploaded successfully',
        'photo': photo
    }), 201


@app.route('/api/jobs/<job_id>/photos/<photo_id>', methods=['DELETE'])
@login_required
def delete_photo(job_id, photo_id):
    if job_id not in JOBS:
        return jsonify({'error': 'Job not found'}), 404
    
    job = JOBS[job_id]
    email = session.get('email')
    if job['userId'] != USERS[email]['id']:
        return jsonify({'error': 'Access denied'}), 403
    
    # Find and remove photo
    photo_index = None
    for i, photo in enumerate(job['photos']):
        if photo['id'] == photo_id:
            photo_index = i
            break
    
    if photo_index is None:
        return jsonify({'error': 'Photo not found'}), 404
    
    # Remove from job
    job['photos'].pop(photo_index)
    
    # Delete file
    if photo_id in PHOTOS:
        try:
            os.remove(PHOTOS[photo_id])
        except:
            pass
        del PHOTOS[photo_id]
    
    return jsonify({'message': 'Photo deleted successfully'})


@app.route('/api/jobs/<job_id>/photos/<photo_id>', methods=['GET'])
@login_required
def get_photo(job_id, photo_id):
    if job_id not in JOBS:
        return jsonify({'error': 'Job not found'}), 404
    
    job = JOBS[job_id]
    email = session.get('email')
    if job['userId'] != USERS[email]['id']:
        return jsonify({'error': 'Access denied'}), 403
    
    if photo_id not in PHOTOS:
        return jsonify({'error': 'Photo not found'}), 404
    
    filepath = PHOTOS[photo_id]
    
    # Read and encode as base64
    with open(filepath, 'rb') as f:
        image_data = f.read()
    
    ext = filepath.rsplit('.', 1)[1].lower()
    mime_types = {
        'jpg': 'image/jpeg',
        'jpeg': 'image/jpeg',
        'png': 'image/png',
        'webp': 'image/webp'
    }
    
    return {
        'data': base64.b64encode(image_data).decode(),
        'contentType': mime_types.get(ext, 'image/jpeg')
    }, 200, {'Content-Type': 'application/json'}


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5001)
