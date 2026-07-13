from datetime import datetime, time, timedelta
from flask import Flask, request, jsonify
from dateutil.parser import parse as parse_date
import uuid

app = Flask(__name__)

# Configuration
BARBERS = ['Alex', 'Lucy', 'George']
SHOP_OPEN = time(9, 0)
SHOP_CLOSE = time(18, 0)
SLOT_DURATION = timedelta(minutes=30)

# In-memory storage for appointments
appointments = {}

def get_time_slots(date):
    """Generate all 30-minute slots from 09:00 to 18:00 for a given date."""
    slots = []
    current_time = datetime.combine(date, SHOP_OPEN)
    end_time = datetime.combine(date, SHOP_CLOSE)

    while current_time < end_time:
        slots.append(current_time.time())
        current_time += SLOT_DURATION

    return slots

def generate_date_key(date):
    """Generate a consistent string key for a date."""
    return date.strftime('%Y-%m-%d')

def get_slot_key(date, barber, start_time):
    """Generate a unique key for a specific slot."""
    return f"{generate_date_key(date)}_{barber}_{start_time.strftime('%H:%M')}"

def get_schedule(date):
    """Get the schedule for a specific date."""
    date_key = generate_date_key(date)
    schedule = {}

    time_slots = get_time_slots(date)

    for barber in BARBERS:
        schedule[barber] = {}
        for slot in time_slots:
            slot_key = get_slot_key(date, barber, slot)
            appointment = appointments.get(slot_key)
            if appointment:
                schedule[barber][slot.strftime('%H:%M')] = {
                    'customer_name': appointment['customer_name'],
                    'notes': appointment.get('notes', ''),
                    'appointment_id': appointment['id']
                }
            else:
                schedule[barber][slot.strftime('%H:%M')] = None

    return schedule

@app.route('/schedule', methods=['GET'])
def get_schedule_endpoint():
    """Get the schedule for a specific date (default: today)."""
    date_str = request.args.get('date', None)

    if date_str:
        try:
            date = parse_date(date_str).date()
        except ValueError:
            return jsonify({'error': 'Invalid date format. Use YYYY-MM-DD or ISO format.'}), 400
    else:
        date = datetime.now().date()

    schedule = get_schedule(date)

    return jsonify({
        'date': date.strftime('%Y-%m-%d'),
        'schedule': schedule
    })

@app.route('/appointments', methods=['POST'])
def add_appointment():
    """Add a new appointment to an available slot."""
    data = request.get_json()

    if not data:
        return jsonify({'error': 'No data provided'}), 400

    # Required fields
    date_str = data.get('date')
    barber = data.get('barber')
    start_time_str = data.get('start_time')
    customer_name = data.get('customer_name')



    # Validate required fields
    if not customer_name or (customer_name and not customer_name.strip()):
        return jsonify({'error': 'Customer name cannot be empty'}), 400

    if not date_str or not barber or not start_time_str:
        return jsonify({'error': 'Missing required fields: date, barber, start_time'}), 400

    # Validate barber
    if barber not in BARBERS:
        return jsonify({'error': f'Invalid barber. Must be one of {BARBERS}'}), 400

    # Parse date and time
    try:
        date = parse_date(date_str).date()
        start_time = parse_date(start_time_str).time()
    except ValueError:
        return jsonify({'error': 'Invalid date or time format'}), 400

    # Validate time slot
    try:
        slot_datetime = datetime.combine(date, start_time)
        # Check if the time is within shop hours and aligned to 30-minute slots
        if start_time < SHOP_OPEN or start_time >= SHOP_CLOSE:
            return jsonify({'error': 'Time slot must be between 09:00 and 18:00'}), 400

        # Check if the time is aligned to 30-minute slots
        minutes = start_time.minute
        if minutes % 30 != 0:
            return jsonify({'error': 'Time slots must be at 30-minute intervals (00, 30)'}), 400

    except ValueError:
        return jsonify({'error': 'Invalid time format'}), 400

    # Check if slot is available
    slot_key = get_slot_key(date, barber, start_time)
    if slot_key in appointments:
        return jsonify({'error': 'This time slot is already booked'}), 409

    # Create appointment
    appointment_id = str(uuid.uuid4())
    appointment = {
        'id': appointment_id,
        'date': date.strftime('%Y-%m-%d'),
        'start_time': start_time.strftime('%H:%M'),
        'end_time': (datetime.combine(date, start_time) + SLOT_DURATION).time().strftime('%H:%M'),
        'barber': barber,
        'customer_name': customer_name.strip(),
        'notes': data.get('notes', '').strip() if data.get('notes') else ''
    }

    # Store the appointment
    appointments[slot_key] = appointment

    return jsonify({
        'message': 'Appointment added successfully',
        'appointment': appointment
    }), 201

@app.route('/appointments/<appointment_id>', methods=['GET'])
def get_appointment(appointment_id):
    """Get details of a specific appointment."""
    # Find the appointment by ID
    for slot_key, appointment in appointments.items():
        if appointment['id'] == appointment_id:
            return jsonify(appointment)
    return jsonify({'error': 'Appointment not found'}), 404

@app.route('/appointments/<appointment_id>', methods=['PUT'])
def update_appointment(appointment_id):
    """Update customer name and/or notes of an existing appointment."""
    data = request.get_json()

    if not data:
        return jsonify({'error': 'No data provided'}), 400

    # Find the appointment
    appointment = None
    slot_key = None
    for sk, appt in appointments.items():
        if appt['id'] == appointment_id:
            appointment = appt
            slot_key = sk
            break

    if not appointment:
        return jsonify({'error': 'Appointment not found'}), 404

    # Validate customer name if provided
    customer_name = data.get('customer_name')
    if customer_name is not None:
        if not customer_name.strip():
            return jsonify({'error': 'Customer name cannot be empty'}), 400
        appointment['customer_name'] = customer_name.strip()

    # Update notes if provided
    notes = data.get('notes')
    if notes is not None:
        appointment['notes'] = notes.strip() if notes else ''

    # Update in storage
    appointments[slot_key] = appointment

    return jsonify({
        'message': 'Appointment updated successfully',
        'appointment': appointment
    })

@app.route('/appointments/<appointment_id>', methods=['DELETE'])
def cancel_appointment(appointment_id):
    """Cancel (delete) an appointment."""
    # Find and remove the appointment
    for slot_key, appointment in list(appointments.items()):
        if appointment['id'] == appointment_id:
            del appointments[slot_key]
            return jsonify({'message': 'Appointment cancelled successfully'})

    return jsonify({'error': 'Appointment not found'}), 404

if __name__ == '__main__':
    app.run(debug=True)
