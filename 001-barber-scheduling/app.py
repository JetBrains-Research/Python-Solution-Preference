from flask import Flask, request, jsonify
from datetime import datetime
import models

app = Flask(__name__)

# Initialize database on startup
models.init_db()

@app.route('/schedule', methods=['GET'])
def get_schedule():
    date = request.args.get('date', datetime.utcnow().strftime('%Y-%m-%d'))
    try:
        schedule = models.get_schedule(date)
        return jsonify(schedule)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/appointments', methods=['POST'])
def create_appointment():
    data = request.json
    try:
        models.add_appointment(
            date=data.get('date'),
            start_time=data.get('start_time'),
            end_time=data.get('end_time'),
            barber=data.get('barber'),
            customer_name=data.get('customer_name'),
            notes=data.get('notes')
        )
        return jsonify({'message': 'Appointment created successfully'}), 201
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except RuntimeError as e:
        return jsonify({'error': str(e)}), 409
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/appointments/<int:appointment_id>', methods=['GET'])
def view_appointment(appointment_id):
    appointment = models.get_appointment(appointment_id)
    if appointment:
        return jsonify({
            'id': appointment['id'],
            'date': appointment['date'],
            'start_time': appointment['start_time'],
            'end_time': appointment['end_time'],
            'barber': appointment['barber'],
            'customer_name': appointment['customer_name'],
            'notes': appointment['notes']
        })
    return jsonify({'error': 'Appointment not found'}), 404

@app.route('/appointments/<int:appointment_id>', methods=['PUT'])
def edit_appointment(appointment_id):
    data = request.json
    try:
        models.update_appointment(
            appointment_id=appointment_id,
            customer_name=data.get('customer_name'),
            notes=data.get('notes')
        )
        return jsonify({'message': 'Appointment updated successfully'})
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/appointments/<int:appointment_id>', methods=['DELETE'])
def delete_appointment(appointment_id):
    try:
        models.cancel_appointment(appointment_id)
        return jsonify({'message': 'Appointment cancelled successfully'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
