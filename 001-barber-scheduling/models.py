import sqlite3
from datetime import datetime, timedelta

DATABASE = 'barber_shop.db'
BARBERS = ['Alex', 'Lucy', 'George']
START_HOUR = 9
END_HOUR = 18
SLOT_DURATION_MINUTES = 30

def get_db_connection():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with open('schema.sql', 'r') as f:
        sql = f.read()
    conn = get_db_connection()
    conn.executescript(sql)
    conn.close()

def get_slots():
    slots = []
    start = datetime.strptime(f"{START_HOUR}:00", "%H:%M")
    end = datetime.strptime(f"{END_HOUR}:00", "%H:%M")
    current = start
    while current < end:
        slot_start = current.strftime("%H:%M")
        current += timedelta(minutes=SLOT_DURATION_MINUTES)
        slot_end = current.strftime("%H:%M")
        slots.append((slot_start, slot_end))
    return slots

def get_schedule(date):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT start_time, barber, customer_name FROM appointments WHERE date = ?', (date,))
    rows = cursor.fetchall()
    conn.close()
    
    booked = {(row['start_time'], row['barber']): row['customer_name'] for row in rows}
    
    schedule = []
    for slot_start, slot_end in get_slots():
        for barber in BARBERS:
            schedule.append({
                'date': date,
                'start_time': slot_start,
                'end_time': slot_end,
                'barber': barber,
                'customer_name': booked.get((slot_start, barber), None)
            })
    return schedule

def add_appointment(date, start_time, end_time, barber, customer_name, notes):
    if not customer_name:
        raise ValueError("Customer name is required")
    
    conn = get_db_connection()
    try:
        conn.execute(
            'INSERT INTO appointments (date, start_time, end_time, barber, customer_name, notes) VALUES (?, ?, ?, ?, ?, ?)',
            (date, start_time, end_time, barber, customer_name, notes)
        )
        conn.commit()
    except sqlite3.IntegrityError:
        conn.close()
        raise RuntimeError("Slot already booked")
    finally:
        conn.close()

def get_appointment(appointment_id):
    conn = get_db_connection()
    appointment = conn.execute('SELECT * FROM appointments WHERE id = ?', (appointment_id,)).fetchone()
    conn.close()
    return appointment

def update_appointment(appointment_id, customer_name, notes):
    if not customer_name:
        raise ValueError("Customer name is required")
    
    conn = get_db_connection()
    conn.execute(
        'UPDATE appointments SET customer_name = ?, notes = ? WHERE id = ?',
        (customer_name, notes, appointment_id)
    )
    conn.commit()
    conn.close()

def cancel_appointment(appointment_id):
    conn = get_db_connection()
    conn.execute('DELETE FROM appointments WHERE id = ?', (appointment_id,))
    conn.commit()
    conn.close()
