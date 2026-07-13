import sqlite3
from datetime import datetime

DB_PATH = 'fleetcare.db'

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_db() as conn:
        conn.execute('''
            CREATE TABLE IF NOT EXISTS vehicles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                odometer INTEGER NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        conn.execute('''
            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                vehicle_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                interval INTEGER NOT NULL,
                last_completed_odometer INTEGER DEFAULT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (vehicle_id) REFERENCES vehicles (id) ON DELETE CASCADE
            )
        ''')
        conn.commit()

def calculate_task_status(current_odometer, interval, last_completed_odometer):
    if last_completed_odometer is None:
        return "Overdue"
    
    distance_elapsed = current_odometer - last_completed_odometer
    if distance_elapsed >= interval:
        return "Overdue"
    
    distance_until_due = interval - distance_elapsed
    if 1 <= distance_until_due <= 1000:
        return "Due Soon"
    
    if distance_until_due > 1000:
        return "OK"
    
    return "Overdue" # Fallback for unexpected cases (e.g. distance_until_due < 1)

def get_vehicle_aggregated_status(vehicle_id):
    with get_db() as conn:
        vehicle = conn.execute('SELECT odometer FROM vehicles WHERE id = ?', (vehicle_id,)).fetchone()
        if not vehicle:
            return None
        
        tasks = conn.execute('SELECT interval, last_completed_odometer FROM tasks WHERE vehicle_id = ?', (vehicle_id,)).fetchall()
        
        if not tasks:
            return "OK"
        
        statuses = [calculate_task_status(vehicle['odometer'], t['interval'], t['last_completed_odometer']) for t in tasks]
        
        if "Overdue" in statuses:
            return "Overdue"
        if "Due Soon" in statuses:
            return "Due Soon"
        return "OK"

def get_sorted_tasks(vehicle_id):
    with get_db() as conn:
        vehicle = conn.execute('SELECT odometer FROM vehicles WHERE id = ?', (vehicle_id,)).fetchone()
        if not vehicle:
            return []
        
        current_odometer = vehicle['odometer']
        tasks = conn.execute('SELECT * FROM tasks WHERE vehicle_id = ? ORDER BY created_at ASC', (vehicle_id,)).fetchall()
        
        task_list = []
        for t in tasks:
            row = dict(t)
            row['status'] = calculate_task_status(current_odometer, row['interval'], row['last_completed_odometer'])
            task_list.append(row)
            
        # Grouped by status: Overdue first, then Due Soon, then OK.
        # Within each group: creation order (oldest first) - already sorted by created_at.
        status_priority = {"Overdue": 0, "Due Soon": 1, "OK": 2}
        task_list.sort(key=lambda x: status_priority.get(x['status'], 3))
        
        return task_list
