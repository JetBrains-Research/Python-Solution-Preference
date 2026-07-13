from datetime import datetime
from flask import Flask, jsonify, request
from flask_sqlalchemy import SQLAlchemy

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///fleetcare.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

class Vehicle(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    odometer = db.Column(db.Integer, nullable=False, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    tasks = db.relationship('Task', backref='vehicle', lazy=True, cascade='all, delete-orphan')

    def to_dict(self):
        status = self.get_aggregated_status()
        return {
            'id': self.id,
            'name': self.name,
            'odometer': self.odometer,
            'status': status
        }

    def get_aggregated_status(self):
        if not self.tasks:
            return 'OK'

        has_overdue = False
        has_due_soon = False

        for task in self.tasks:
            task_status = task.get_status()
            if task_status == 'Overdue':
                has_overdue = True
                break
            elif task_status == 'Due Soon':
                has_due_soon = True

        if has_overdue:
            return 'Overdue'
        elif has_due_soon:
            return 'Due Soon'
        else:
            return 'OK'

    def detail_dict(self):
        status = self.get_aggregated_status()
        return {
            'id': self.id,
            'name': self.name,
            'odometer': self.odometer,
            'status': status,
            'tasks': [task.to_dict() for task in self.tasks]
        }

class Task(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    interval = db.Column(db.Integer, nullable=False)
    last_completed_odometer = db.Column(db.Integer, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    vehicle_id = db.Column(db.Integer, db.ForeignKey('vehicle.id'), nullable=False)

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'interval': self.interval,
            'last_completed_odometer': self.last_completed_odometer,
            'status': self.get_status()
        }

    def get_status(self):
        current_odometer = self.vehicle.odometer
        starting_point = self.last_completed_odometer if self.last_completed_odometer is not None else 0
        distance_elapsed = current_odometer - starting_point
        distance_until_due = self.interval - distance_elapsed

        if distance_elapsed >= self.interval:
            return 'Overdue'

        if 1 <= distance_until_due <= 1000:
            return 'Due Soon'

        return 'OK'

def sort_tasks(tasks):
    overdue = []
    due_soon = []
    ok = []

    for task in tasks:
        status = task.get_status()
        if status == 'Overdue':
            overdue.append(task)
        elif status == 'Due Soon':
            due_soon.append(task)
        else:
            ok.append(task)

    overdue.sort(key=lambda t: t.created_at)
    due_soon.sort(key=lambda t: t.created_at)
    ok.sort(key=lambda t: t.created_at)

    return overdue + due_soon + ok

@app.route('/vehicles', methods=['GET'])
def get_vehicles():
    vehicles = Vehicle.query.order_by(Vehicle.created_at).all()
    return jsonify([v.to_dict() for v in vehicles])

@app.route('/vehicles/<int:vehicle_id>', methods=['GET'])
def get_vehicle_detail(vehicle_id):
    vehicle = Vehicle.query.get_or_404(vehicle_id)
    tasks = Task.query.filter_by(vehicle_id=vehicle_id).all()
    sorted_tasks = sort_tasks(tasks)
    result = vehicle.detail_dict()
    result['tasks'] = [t.to_dict() for t in sorted_tasks]
    return jsonify(result)

@app.route('/vehicles', methods=['POST'])
def create_vehicle():
    data = request.get_json()
    if not data or 'name' not in data:
        return jsonify({'error': 'Name is required'}), 400

    name = data['name']
    if not name or not name.strip():
        return jsonify({'error': 'Name must be non-empty'}), 400

    odometer = data.get('odometer', 0)
    if not isinstance(odometer, int) or odometer < 0:
        return jsonify({'error': 'Odometer must be an integer >= 0'}), 400

    vehicle = Vehicle(name=name, odometer=odometer)
    db.session.add(vehicle)
    db.session.commit()
    return jsonify(vehicle.to_dict()), 201

@app.route('/vehicles/<int:vehicle_id>/odometer', methods=['PUT'])
def update_odometer(vehicle_id):
    vehicle = Vehicle.query.get_or_404(vehicle_id)
    data = request.get_json()
    if not data or 'odometer' not in data:
        return jsonify({'error': 'Odometer is required'}), 400

    new_odometer = data['odometer']
    if not isinstance(new_odometer, int) or new_odometer < 0:
        return jsonify({'error': 'Odometer must be an integer >= 0'}), 400

    if new_odometer < vehicle.odometer:
        return jsonify({'error': 'Odometer cannot decrease'}), 400

    vehicle.odometer = new_odometer
    db.session.commit()
    return jsonify(vehicle.to_dict())

@app.route('/vehicles/<int:vehicle_id>', methods=['DELETE'])
def delete_vehicle(vehicle_id):
    vehicle = Vehicle.query.get_or_404(vehicle_id)
    db.session.delete(vehicle)
    db.session.commit()
    return jsonify({'message': 'Vehicle deleted'}), 200

@app.route('/vehicles/<int:vehicle_id>/tasks', methods=['POST'])
def create_task(vehicle_id):
    vehicle = Vehicle.query.get_or_404(vehicle_id)
    data = request.get_json()
    if not data or 'name' not in data:
        return jsonify({'error': 'Name is required'}), 400

    name = data['name']
    if not name or not name.strip():
        return jsonify({'error': 'Name must be non-empty'}), 400

    if 'interval' not in data:
        return jsonify({'error': 'Interval is required'}), 400

    interval = data['interval']
    if not isinstance(interval, int) or interval <= 0:
        return jsonify({'error': 'Interval must be an integer > 0'}), 400

    task = Task(
        name=name,
        interval=interval,
        last_completed_odometer=None,
        vehicle_id=vehicle_id
    )
    db.session.add(task)
    db.session.commit()
    return jsonify(task.to_dict()), 201

@app.route('/vehicles/<int:vehicle_id>/tasks/<int:task_id>', methods=['DELETE'])
def delete_task(vehicle_id, task_id):
    task = Task.query.filter_by(id=task_id, vehicle_id=vehicle_id).first_or_404()
    db.session.delete(task)
    db.session.commit()
    return jsonify({'message': 'Task deleted'}), 200

@app.route('/vehicles/<int:vehicle_id>/tasks/<int:task_id>/done', methods=['POST'])
def mark_task_done(vehicle_id, task_id):
    task = Task.query.filter_by(id=task_id, vehicle_id=vehicle_id).first_or_404()
    task.last_completed_odometer = task.vehicle.odometer
    db.session.commit()
    return jsonify(task.to_dict())

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(port=8000)
