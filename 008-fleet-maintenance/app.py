from flask import Flask, jsonify, request
import json
import os
from datetime import datetime

app = Flask(__name__)

DATA_FILE = 'fleetcare_data.json'

def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, 'r') as f:
            return json.load(f)
    return {'vehicles': [], 'next_vehicle_id': 1, 'next_task_id': 1}

def save_data(data):
    with open(DATA_FILE, 'w') as f:
        json.dump(data, f, indent=2)

def get_vehicle_status(vehicle):
    """Calculate aggregated status for a vehicle based on its tasks."""
    if not vehicle.get('tasks'):
        return 'OK'
    
    has_overdue = False
    has_due_soon = False
    
    for task in vehicle['tasks']:
        status = calculate_task_status(vehicle, task)
        if status == 'Overdue':
            has_overdue = True
            break
        elif status == 'Due Soon':
            has_due_soon = True
    
    if has_overdue:
        return 'Overdue'
    elif has_due_soon:
        return 'Due Soon'
    return 'OK'

def calculate_task_status(vehicle, task):
    """Calculate status for a single task."""
    current_odometer = vehicle['odometer']
    interval = task['interval']
    last_completed = task.get('last_completed_odometer')
    
    if last_completed is None:
        # Never completed
        distance_elapsed = current_odometer
    else:
        distance_elapsed = current_odometer - last_completed
    
    distance_until_due = interval - distance_elapsed
    
    if distance_elapsed >= interval:
        return 'Overdue'
    elif 1 <= distance_until_due <= 1000:
        return 'Due Soon'
    else:
        return 'OK'

def sort_tasks(vehicle):
    """Sort tasks by status: Overdue first, then Due Soon, then OK."""
    tasks = vehicle.get('tasks', [])
    overdue = []
    due_soon = []
    ok = []
    
    for task in tasks:
        status = calculate_task_status(vehicle, task)
        if status == 'Overdue':
            overdue.append(task)
        elif status == 'Due Soon':
            due_soon.append(task)
        else:
            ok.append(task)
    
    return overdue + due_soon + ok

def get_task_with_status(vehicle, task):
    """Get task with its calculated status."""
    task_copy = task.copy()
    task_copy['status'] = calculate_task_status(vehicle, task)
    return task_copy

@app.route('/vehicles', methods=['GET'])
def list_vehicles():
    data = load_data()
    vehicles = []
    for v in data['vehicles']:
        vehicle_info = {
            'id': v['id'],
            'name': v['name'],
            'odometer': v['odometer'],
            'status': get_vehicle_status(v)
        }
        vehicles.append(vehicle_info)
    return jsonify(vehicles)

@app.route('/vehicles', methods=['POST'])
def create_vehicle():
    req_data = request.get_json()
    
    if not req_data:
        return jsonify({'error': 'Request body required'}), 400
    
    name = req_data.get('name', '').strip()
    if not name:
        return jsonify({'error': 'Name is required and cannot be empty'}), 400
    
    odometer = req_data.get('odometer')
    if odometer is None:
        return jsonify({'error': 'Odometer is required'}), 400
    
    try:
        odometer = int(odometer)
    except (ValueError, TypeError):
        return jsonify({'error': 'Odometer must be an integer'}), 400
    
    if odometer < 0:
        return jsonify({'error': 'Odometer must be >= 0'}), 400
    
    data = load_data()
    
    vehicle = {
        'id': data['next_vehicle_id'],
        'name': name,
        'odometer': odometer,
        'tasks': [],
        'created_at': datetime.now().isoformat()
    }
    
    data['vehicles'].append(vehicle)
    data['next_vehicle_id'] += 1
    save_data(data)
    
    return jsonify(vehicle), 201

@app.route('/vehicles/<int:vehicle_id>', methods=['GET'])
def get_vehicle(vehicle_id):
    data = load_data()
    
    for v in data['vehicles']:
        if v['id'] == vehicle_id:
            vehicle_copy = v.copy()
            vehicle_copy['status'] = get_vehicle_status(v)
            vehicle_copy['tasks'] = [get_task_with_status(v, t) for t in sort_tasks(v)]
            return jsonify(vehicle_copy)
    
    return jsonify({'error': 'Vehicle not found'}), 404

@app.route('/vehicles/<int:vehicle_id>', methods=['PUT'])
def update_vehicle(vehicle_id):
    data = load_data()
    
    vehicle = None
    for v in data['vehicles']:
        if v['id'] == vehicle_id:
            vehicle = v
            break
    
    if not vehicle:
        return jsonify({'error': 'Vehicle not found'}), 404
    
    req_data = request.get_json()
    if not req_data:
        return jsonify({'error': 'Request body required'}), 400
    
    odometer = req_data.get('odometer')
    if odometer is not None:
        try:
            odometer = int(odometer)
        except (ValueError, TypeError):
            return jsonify({'error': 'Odometer must be an integer'}), 400
        
        if odometer < 0:
            return jsonify({'error': 'Odometer must be >= 0'}), 400
        
        if odometer < vehicle['odometer']:
            return jsonify({'error': 'Odometer cannot be decreased'}), 400
        
        vehicle['odometer'] = odometer
    
    save_data(data)
    
    vehicle_copy = vehicle.copy()
    vehicle_copy['status'] = get_vehicle_status(vehicle)
    vehicle_copy['tasks'] = [get_task_with_status(vehicle, t) for t in sort_tasks(vehicle)]
    return jsonify(vehicle_copy)

@app.route('/vehicles/<int:vehicle_id>', methods=['DELETE'])
def delete_vehicle(vehicle_id):
    data = load_data()
    
    for i, v in enumerate(data['vehicles']):
        if v['id'] == vehicle_id:
            data['vehicles'].pop(i)
            save_data(data)
            return '', 204
    
    return jsonify({'error': 'Vehicle not found'}), 404

@app.route('/vehicles/<int:vehicle_id>/tasks', methods=['POST'])
def create_task(vehicle_id):
    data = load_data()
    
    vehicle = None
    for v in data['vehicles']:
        if v['id'] == vehicle_id:
            vehicle = v
            break
    
    if not vehicle:
        return jsonify({'error': 'Vehicle not found'}), 404
    
    req_data = request.get_json()
    if not req_data:
        return jsonify({'error': 'Request body required'}), 400
    
    name = req_data.get('name', '').strip()
    if not name:
        return jsonify({'error': 'Name is required and cannot be empty'}), 400
    
    interval = req_data.get('interval')
    if interval is None:
        return jsonify({'error': 'Interval is required'}), 400
    
    try:
        interval = int(interval)
    except (ValueError, TypeError):
        return jsonify({'error': 'Interval must be an integer'}), 400
    
    if interval <= 0:
        return jsonify({'error': 'Interval must be > 0'}), 400
    
    task = {
        'id': data['next_task_id'],
        'name': name,
        'interval': interval,
        'last_completed_odometer': None,
        'created_at': datetime.now().isoformat()
    }
    
    vehicle['tasks'].append(task)
    data['next_task_id'] += 1
    save_data(data)
    
    task_copy = task.copy()
    task_copy['status'] = calculate_task_status(vehicle, task)
    return jsonify(task_copy), 201

@app.route('/vehicles/<int:vehicle_id>/tasks/<int:task_id>', methods=['GET'])
def get_task(vehicle_id, task_id):
    data = load_data()
    
    vehicle = None
    for v in data['vehicles']:
        if v['id'] == vehicle_id:
            vehicle = v
            break
    
    if not vehicle:
        return jsonify({'error': 'Vehicle not found'}), 404
    
    for t in vehicle['tasks']:
        if t['id'] == task_id:
            task_copy = t.copy()
            task_copy['status'] = calculate_task_status(vehicle, t)
            return jsonify(task_copy)
    
    return jsonify({'error': 'Task not found'}), 404

@app.route('/vehicles/<int:vehicle_id>/tasks/<int:task_id>', methods=['PUT'])
def update_task(vehicle_id, task_id):
    data = load_data()
    
    vehicle = None
    for v in data['vehicles']:
        if v['id'] == vehicle_id:
            vehicle = v
            break
    
    if not vehicle:
        return jsonify({'error': 'Vehicle not found'}), 404
    
    task = None
    for t in vehicle['tasks']:
        if t['id'] == task_id:
            task = t
            break
    
    if not task:
        return jsonify({'error': 'Task not found'}), 404
    
    req_data = request.get_json()
    if not req_data:
        return jsonify({'error': 'Request body required'}), 400
    
    if 'done' in req_data and req_data['done']:
        task['last_completed_odometer'] = vehicle['odometer']
        save_data(data)
    
    task_copy = task.copy()
    task_copy['status'] = calculate_task_status(vehicle, task)
    return jsonify(task_copy)

@app.route('/vehicles/<int:vehicle_id>/tasks/<int:task_id>', methods=['DELETE'])
def delete_task(vehicle_id, task_id):
    data = load_data()
    
    vehicle = None
    for v in data['vehicles']:
        if v['id'] == vehicle_id:
            vehicle = v
            break
    
    if not vehicle:
        return jsonify({'error': 'Vehicle not found'}), 404
    
    for i, t in enumerate(vehicle['tasks']):
        if t['id'] == task_id:
            vehicle['tasks'].pop(i)
            save_data(data)
            return '', 204
    
    return jsonify({'error': 'Task not found'}), 404

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001)
