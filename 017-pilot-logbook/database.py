import sqlite3
import os
from datetime import datetime, date
from typing import Optional, List, Dict, Any
from contextlib import contextmanager

DATABASE_PATH = "pilots_logbook.db"

@contextmanager
def get_db_connection():
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()

def init_database():
    """Initialize the database with all required tables"""
    with get_db_connection() as conn:
        cursor = conn.cursor()

        # Create aircraft table
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS aircraft (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            registration TEXT NOT NULL,
            registration_canonical TEXT NOT NULL UNIQUE,
            make_model TEXT NOT NULL,
            category TEXT NOT NULL,
            class TEXT NOT NULL,
            type_designator TEXT,
            type_rating_required BOOLEAN DEFAULT FALSE,
            is_complex BOOLEAN DEFAULT FALSE,
            is_high_performance BOOLEAN DEFAULT FALSE,
            is_tailwheel BOOLEAN DEFAULT FALSE,
            is_turbine BOOLEAN DEFAULT FALSE,
            is_active BOOLEAN DEFAULT TRUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        ''')

        # Create flights table
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS flights (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date DATE NOT NULL,
            aircraft_id INTEGER NOT NULL,
            departure TEXT NOT NULL,
            arrival TEXT NOT NULL,
            via TEXT,
            total_time REAL NOT NULL,
            day_time REAL DEFAULT 0.0,
            night_time REAL DEFAULT 0.0,
            pic_time REAL DEFAULT 0.0,
            sic_time REAL DEFAULT 0.0,
            dual_given REAL DEFAULT 0.0,
            dual_received REAL DEFAULT 0.0,
            cross_country REAL DEFAULT 0.0,
            actual_instrument REAL DEFAULT 0.0,
            simulated_instrument REAL DEFAULT 0.0,
            day_takeoffs INTEGER DEFAULT 0,
            day_landings INTEGER DEFAULT 0,
            night_takeoffs INTEGER DEFAULT 0,
            night_landings INTEGER DEFAULT 0,
            instrument_approaches INTEGER DEFAULT 0,
            holds_performed BOOLEAN DEFAULT FALSE,
            intercept_track_performed BOOLEAN DEFAULT FALSE,
            notes TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (aircraft_id) REFERENCES aircraft(id)
        )
        ''')

        # Create indexes for better performance
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_flights_date ON flights(date)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_flights_aircraft_id ON flights(aircraft_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_aircraft_active ON aircraft(is_active)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_aircraft_canonical ON aircraft(registration_canonical)')

        conn.commit()

def canonical_registration(reg: str) -> str:
    """Convert registration to canonical form (uppercase, no spaces/hyphens)"""
    return reg.replace(" ", "").replace("-", "").upper()

def reset_database():
    """Reset the database - for testing only"""
    if os.path.exists(DATABASE_PATH):
        os.remove(DATABASE_PATH)
    init_database()
