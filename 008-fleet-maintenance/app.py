from flask import Flask, request, jsonify, abort
import models

app = Flask(__name__)

# Initialize database
models.init_db()

@app.route('/vehicles', methods=['GET'])
def list_vehicles():
    with models.get_db() as conn:
        vehicles = conn.execute('SELECT * FROM vehicles ORDER BY created_at ASC').fetchall()
        
    result = []
    for v in vehicles:
        row = dict(v)
        row['status'] = models.get_vehicle_aggregated_status(row['id'])
        result.append(row)
    return jsonify(result)

@app.route('/vehicles', methods=['POST'])
def create_vehicle():
    data = request.get_json()
    name = data.get('name')
    odometer = data.get('odometer')
    
    if not name or not isinstance(name, str) or name.strip() == "":
        abort(400, description="Name is required and must be a non-empty string")
    if odometer is None or not isinstance(odometer, int) or odometer < 0:
        abort(400, description="Odometer is required and must be an integer >= 0")
    
    with models.get_db() as conn:
        cursor = conn.execute('INSERT INTO vehicles (name, odometer) VALUES (?, ?)', (name, odometer))
        conn.commit()
        vehicle_id = cursor.lastrowid
        
    return jsonify({"id": vehicle_id, "name": name, "odometer": odometer}), 201

@app.route('/vehicles/<int:vehicle_id>', methods=['GET'])
def get_vehicle(vehicle_id):
    with models.get_db() as conn:
        vehicle = conn.execute('SELECT * FROM vehicles WHERE id = ?', (vehicle_id,)).fetchone()
        if not vehicle:
            abort(404, description="Vehicle not found")
        
    v_dict = dict(vehicle)
    tasks = models.get_sorted_tasks(vehicle_id)
    
    # Convert task rows to dicts (already done in get_sorted_tasks)
    # Remove internal DB columns from tasks for the API response
    for t in tasks:
        t.pop('created_at', None)
        
    return jsonify({
        "id": v_dict['id'],
        "name": v_dict['name'],
        "odometer": v_dict['odometer'],
        "tasks": tasks
    })

@app.route('/vehicles/<int:vehicle_id>/odometer', methods=['PATCH'])
def update_odometer(vehicle_id):
    data = request.get_json()
    new_odometer = data.get('odometer')
    
    if new_odometer is None or not isinstance(new_odometer, int):
        abort(400, description="Odometer must be an integer")
    
    with models.get_db() as conn:
        vehicle = conn.execute('SELECT odometer FROM vehicles WHERE id = ?', (vehicle_id,)).fetchone()
        if not vehicle:
            abort(404, description="Vehicle not found")
        
        if new_odometer < vehicle['odometer']:
            abort(400, description="Odometer cannot decrease")
            
        conn.execute('UPDATE vehicles SET odometer = ? WHERE id = ?', (new_odometer, vehicle_id))
        conn.commit()
        
    return jsonify({"status": "success"})

@app.route('/vehicles/<int:vehicle_id>', methods=['DELETE'])
def delete_vehicle(vehicle_id):
    with models.get_db() as conn:
        # SQLite doesn't enable foreign keys by default
        conn.execute('PRAGMA foreign_keys = ON')
        cursor = conn.execute('DELETE FROM vehicles WHERE id = ?', (vehicle_id,))
        conn.commit()
        if cursor.rowcount == 0:
            abort(404, description="Vehicle not found")
            
    return jsonify({"status": "success"})

@app.route('/vehicles/<int:vehicle_id>/tasks', methods=['POST'])
def create_task(vehicle_id):
    data = request.get_json()
    name = data.get('name')
    interval = data.get('interval')
    
    if not name or not isinstance(name, str) or name.strip() == "":
        abort(400, description="Task name is required and must be a non-empty string")
    if interval is None or not isinstance(interval, int) or interval <= 0:
        abort(400, description="Interval is required and must be an integer > 0")
        
    with models.get_db() as conn:
        # Check if vehicle exists
        vehicle = conn.execute('SELECT id FROM vehicles WHERE id = ?', (vehicle_id,)).fetchone()
        if not vehicle:
            abort(404, description="Vehicle not found")
            
        cursor = conn.execute('INSERT INTO tasks (vehicle_id, name, interval) VALUES (?, ?, ?)', (vehicle_id, name, interval))
        conn.commit()
        task_id = cursor.lastrowid
        
    return jsonify({"id": task_id, "name": name, "interval": interval}), 201

@app.route('/tasks/<int:task_id>/done', methods=['PATCH'])
def mark_task_done(task_id):
    with models.get_db() as conn:
        task = conn.execute('SELECT vehicle_id FROM tasks WHERE id = ?', (task_id,)).fetchone()
        if not task:
            abort(404, description="Task not found")
        
        vehicle = conn.execute('SELECT odometer FROM vehicles WHERE id = ?', (task['vehicle_id'],)).fetchone()
        # Vehicle should always exist if task exists because of FK, but good to be safe
        
        conn.execute('UPDATE tasks SET last_completed_odometer = ? WHERE id = ?', (vehicle['odometer'], task_id))
        conn.commit()
        
    return jsonify({"status": "success"})

@app.route('/tasks/<int:task_id>', methods=['DELETE'])
def delete_task(task_id):
    with models.get_db() as conn:
        cursor = conn.execute('DELETE FROM tasks WHERE id = ?', (task_id,))
        conn.commit()
        if cursor.rowcount == 0:
            abort(404, description="Task not found")
            
    return jsonify({"status": "success"})

if __name__ == '__main__':
    app.run(port=5000)
