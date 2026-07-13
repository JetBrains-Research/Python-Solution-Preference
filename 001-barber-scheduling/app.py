from flask import Flask, request, jsonify
from datetime import datetime, timedelta
import uuid

app = Flask(__name__)

# Configuration
BARBERS = ['Alex', 'Lucy', 'George']
START_HOUR = 9
END_HOUR = 18
SLOT_DURATION_MINUTES = 30
TIMEZONE = 'UTC'

# In-memory storage for appointments
# Key: (date_str, barber, start_time_str) -> appointment data
appointments = {}

def generate_slots():
    """Generate all time slots for the day (09:00-18:00, 30 min intervals)."""
    slots = []
    current = timedelta(hours=START_HOUR)
    while current < timedelta(hours=END_HOUR):
        slot_start = current
        slot_end = current + timedelta(minutes=SLOT_DURATION_MINUTES)
        slots.append({
            'start': slot_start,
            'end': slot_end
        })
        current = slot_end
    return slots

def format_time(td):
    """Format timedelta as HH:MM string."""
    return f"{td.seconds // 3600:02d}:{(td.seconds % 3600) // 60:02d}"

def parse_datetime(date_str=None, time_str=None):
    """Parse date and time strings."""
    if date_str:
        date = datetime.strptime(date_str, '%Y-%m-%d')
    else:
        date = datetime.utcnow().date()
    
    if time_str:
        time_parts = time_str.split(':')
        hour = int(time_parts[0])
        minute = int(time_parts[1])
        time = timedelta(hours=hour, minutes=minute)
    else:
        time = None
    
    return date, time

def get_slot_key(date_str, barber, start_time_str):
    """Generate unique key for a slot."""
    return f"{date_str}|{barber}|{start_time_str}"

def is_slot_available(date_str, barber, start_time_str):
    """Check if a slot is available."""
    key = get_slot_key(date_str, barber, start_time_str)
    return key not in appointments

@app.route('/schedule', methods=['GET'])
def get_schedule():
    """Get the schedule for a specific date or today."""
    date_str = request.args.get('date')
    date, _ = parse_datetime(date_str)
    date_str = date.strftime('%Y-%m-%d')
    
    slots = generate_slots()
    schedule = []
    
    for barber in BARBERS:
        barber_schedule = []
        for slot in slots:
            start_time_str = format_time(slot['start'])
            end_time_str = format_time(slot['end'])
            key = get_slot_key(date_str, barber, start_time_str)
            
            if key in appointments:
                apt = appointments[key]
                barber_schedule.append({
                    'barber': barber,
                    'date': date_str,
                    'start_time': start_time_str,
                    'end_time': end_time_str,
                    'customer_name': apt['customer_name'],
                    'notes': apt.get('notes', ''),
                    'appointment_id': apt['id'],
                    'available': False
                })
            else:
                barber_schedule.append({
                    'barber': barber,
                    'date': date_str,
                    'start_time': start_time_str,
                    'end_time': end_time_str,
                    'available': True
                })
        schedule.append(barber_schedule)
    
    return jsonify({
        'date': date_str,
        'schedule': schedule
    })

@app.route('/appointments', methods=['POST'])
def add_appointment():
    """Add a new appointment."""
    data = request.get_json()
    
    if not data:
        return jsonify({'error': 'No data provided'}), 400
    
    customer_name = data.get('customer_name', '').strip()
    notes = data.get('notes', '')
    date_str = data.get('date')
    barber = data.get('barber')
    start_time_str = data.get('start_time')
    
    # Validate required fields
    if not customer_name:
        return jsonify({'error': 'Customer name is required'}), 400
    
    if not date_str:
        return jsonify({'error': 'Date is required'}), 400
    
    if not barber:
        return jsonify({'error': 'Barber is required'}), 400
    
    if not start_time_str:
        return jsonify({'error': 'Start time is required'}), 400
    
    # Validate barber
    if barber not in BARBERS:
        return jsonify({'error': f'Invalid barber. Must be one of: {", ".join(BARBERS)}'}), 400
    
    # Parse date
    try:
        date = datetime.strptime(date_str, '%Y-%m-%d')
        date_str = date.strftime('%Y-%m-%d')
    except ValueError:
        return jsonify({'error': 'Invalid date format. Use YYYY-MM-DD'}), 400
    
    # Validate start time
    try:
        time_parts = start_time_str.split(':')
        hour = int(time_parts[0])
        minute = int(time_parts[1])
        
        if minute not in [0, 30]:
            return jsonify({'error': 'Start time must be on a 30-minute boundary'}), 400
        
        if hour < START_HOUR or hour >= END_HOUR:
            return jsonify({'error': f'Start time must be between {START_HOUR:02d}:00 and {END_HOUR:02d}:00'}), 400
        
        if hour == END_HOUR:
            return jsonify({'error': f'Start time must be before {END_HOUR:02d}:00'}), 400
    except (ValueError, IndexError):
        return jsonify({'error': 'Invalid start time format. Use HH:MM'}), 400
    
    # Calculate end time
    end_time = timedelta(hours=hour, minutes=minute) + timedelta(minutes=SLOT_DURATION_MINUTES)
    end_time_str = format_time(end_time)
    
    # Check if slot is available (race condition check)
    key = get_slot_key(date_str, barber, start_time_str)
    if not is_slot_available(date_str, barber, start_time_str):
        return jsonify({'error': 'Slot is already booked'}), 409
    
    # Create appointment
    appointment_id = str(uuid.uuid4())
    appointment = {
        'id': appointment_id,
        'date': date_str,
        'start_time': start_time_str,
        'end_time': end_time_str,
        'barber': barber,
        'customer_name': customer_name,
        'notes': notes
    }
    
    appointments[key] = appointment
    
    return jsonify(appointment), 201

@app.route('/appointments/<appointment_id>', methods=['GET'])
def get_appointment(appointment_id):
    """Get appointment details by ID."""
    for key, apt in appointments.items():
        if apt['id'] == appointment_id:
            return jsonify(apt)
    
    return jsonify({'error': 'Appointment not found'}), 404

@app.route('/appointments/<appointment_id>', methods=['PUT'])
def update_appointment(appointment_id):
    """Update an existing appointment (customer name and notes only)."""
    data = request.get_json()
    
    if not data:
        return jsonify({'error': 'No data provided'}), 400
    
    # Find the appointment
    appointment_key = None
    appointment = None
    for key, apt in appointments.items():
        if apt['id'] == appointment_id:
            appointment_key = key
            appointment = apt
            break
    
    if not appointment:
        return jsonify({'error': 'Appointment not found'}), 404
    
    # Get new values (only customer_name and notes are editable)
    new_customer_name = data.get('customer_name')
    new_notes = data.get('notes')
    
    # Update if provided
    if new_customer_name is not None:
        new_customer_name = new_customer_name.strip()
        if not new_customer_name:
            return jsonify({'error': 'Customer name cannot be empty'}), 400
        appointment['customer_name'] = new_customer_name
    
    if new_notes is not None:
        appointment['notes'] = new_notes
    
    # Save back
    appointments[appointment_key] = appointment
    
    return jsonify(appointment)

@app.route('/appointments/<appointment_id>', methods=['DELETE'])
def cancel_appointment(appointment_id):
    """Cancel (delete) an appointment."""
    # Find the appointment
    appointment_key = None
    for key, apt in appointments.items():
        if apt['id'] == appointment_id:
            appointment_key = key
            break
    
    if not appointment_key:
        return jsonify({'error': 'Appointment not found'}), 404
    
    # Delete the appointment
    del appointments[appointment_key]
    
    return jsonify({'message': 'Appointment cancelled'})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001, debug=True)
