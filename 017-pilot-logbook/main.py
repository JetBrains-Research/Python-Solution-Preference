from fastapi import FastAPI, HTTPException, Depends, Query, status
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional, List, Dict, Any
from datetime import date, datetime, timedelta
from dateutil.relativedelta import relativedelta
import csv
import io
from database import get_db_connection, canonical_registration, init_database
from models import (
    AircraftCreate, AircraftUpdate, AircraftResponse,
    FlightCreate, FlightUpdate, FlightResponse, FlightListResponse,
    FilterParams, AnalyticsParams, AnalyticsResponse, AnalyticsTimeRange,
    TotalsResponse, GroupedTotals, CurrencyResponse, DayNightCurrencyResponse, InstrumentCurrencyResponse,
    MessageResponse, AircraftCategory, AircraftClass
)
import models

app = FastAPI(title="Pilot's Logbook API", version="1.0.0")

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize database on startup
@app.on_event("startup")
def startup_event():
    init_database()

def get_current_date():
    """Get current date in UTC, truncating to date only"""
    return date.today()

def validate_aircraft_exists(aircraft_id: int, conn) -> bool:
    """Check if aircraft exists and return its data"""
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM aircraft WHERE id = ?", (aircraft_id,))
    result = cursor.fetchone()
    if not result:
        return False
    return dict(result)

def validate_aircraft_active(aircraft_id: int, conn) -> bool:
    """Check if aircraft is active"""
    cursor = conn.cursor()
    cursor.execute("SELECT is_active FROM aircraft WHERE id = ?", (aircraft_id,))
    result = cursor.fetchone()
    return result and result['is_active']

def get_aircraft_data(aircraft_id: int, conn) -> Optional[Dict]:
    """Get full aircraft data by ID"""
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM aircraft WHERE id = ?", (aircraft_id,))
    result = cursor.fetchone()
    return dict(result) if result else None

def get_flight_data(flight_id: int, conn) -> Optional[Dict]:
    """Get full flight data by ID"""
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM flights WHERE id = ?", (flight_id,))
    result = cursor.fetchone()
    return dict(result) if result else None

# AIRCRAFT ENDPOINTS

@app.post("/aircraft/", response_model=AircraftResponse, status_code=status.HTTP_201_CREATED)
def create_aircraft(aircraft: AircraftCreate):
    """Create a new aircraft"""
    with get_db_connection() as conn:
        cursor = conn.cursor()

        # Check if aircraft with same canonical registration exists
        canonical_reg = canonical_registration(aircraft.registration)
        cursor.execute("SELECT id FROM aircraft WHERE registration_canonical = ?", (canonical_reg,))
        existing = cursor.fetchone()
        if existing:
            raise HTTPException(status_code=400, detail="Aircraft with this registration already exists")

        # Validate type designator requirement
        if aircraft.type_rating_required and not aircraft.type_designator:
            raise HTTPException(status_code=400, detail="Type Designator is required when Type rating required is true")

        # Insert aircraft
        cursor.execute('''
        INSERT INTO aircraft (
            registration, registration_canonical, make_model, category, class,
            type_designator, type_rating_required, is_complex, is_high_performance,
            is_tailwheel, is_turbine, is_active
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            aircraft.registration,
            canonical_reg,
            aircraft.make_model,
            aircraft.category.value,
            aircraft.class_.value,
            aircraft.type_designator,
            aircraft.type_rating_required,
            aircraft.is_complex,
            aircraft.is_high_performance,
            aircraft.is_tailwheel,
            aircraft.is_turbine,
            True  # is_active defaults to True
        ))

        aircraft_id = cursor.lastrowid
        conn.commit()

        # Fetch the created aircraft
        cursor.execute("SELECT * FROM aircraft WHERE id = ?", (aircraft_id,))
        result = cursor.fetchone()

        return AircraftResponse(**dict(result))

@app.get("/aircraft/", response_model=List[AircraftResponse])
def list_aircraft(include_inactive: bool = False):
    """List all aircraft, optionally including inactive ones"""
    with get_db_connection() as conn:
        cursor = conn.cursor()

        if include_inactive:
            cursor.execute("SELECT * FROM aircraft ORDER BY registration")
        else:
            cursor.execute("SELECT * FROM aircraft WHERE is_active = TRUE ORDER BY registration")

        aircrafts = cursor.fetchall()
        return [AircraftResponse(**dict(row)) for row in aircrafts]

@app.get("/aircraft/{aircraft_id}", response_model=AircraftResponse)
def get_aircraft(aircraft_id: int):
    """Get a specific aircraft by ID"""
    with get_db_connection() as conn:
        aircraft = get_aircraft_data(aircraft_id, conn)
        if not aircraft:
            raise HTTPException(status_code=404, detail="Aircraft not found")
        return AircraftResponse(**aircraft)

@app.put("/aircraft/{aircraft_id}", response_model=AircraftResponse)
def update_aircraft(aircraft_id: int, aircraft_update: AircraftUpdate):
    """Update an aircraft"""
    with get_db_connection() as conn:
        # Check if aircraft exists
        existing_aircraft = get_aircraft_data(aircraft_id, conn)
        if not existing_aircraft:
            raise HTTPException(status_code=404, detail="Aircraft not found")

        # Check canonical registration uniqueness
        if aircraft_update.registration is not None:
            new_canonical = canonical_registration(aircraft_update.registration)
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM aircraft WHERE registration_canonical = ? AND id != ?",
                          (new_canonical, aircraft_id))
            existing = cursor.fetchone()
            if existing:
                raise HTTPException(status_code=400, detail="Aircraft with this registration already exists")

        # Build update query
        update_data = {}
        if aircraft_update.registration is not None:
            update_data['registration'] = aircraft_update.registration
            update_data['registration_canonical'] = canonical_registration(aircraft_update.registration)
        if aircraft_update.make_model is not None:
            update_data['make_model'] = aircraft_update.make_model
        if aircraft_update.category is not None:
            update_data['category'] = aircraft_update.category.value
        if aircraft_update.class_ is not None:
            update_data['class'] = aircraft_update.class_.value
        if aircraft_update.type_designator is not None:
            update_data['type_designator'] = aircraft_update.type_designator
        if aircraft_update.type_rating_required is not None:
            update_data['type_rating_required'] = aircraft_update.type_rating_required
        if aircraft_update.is_complex is not None:
            update_data['is_complex'] = aircraft_update.is_complex
        if aircraft_update.is_high_performance is not None:
            update_data['is_high_performance'] = aircraft_update.is_high_performance
        if aircraft_update.is_tailwheel is not None:
            update_data['is_tailwheel'] = aircraft_update.is_tailwheel
        if aircraft_update.is_turbine is not None:
            update_data['is_turbine'] = aircraft_update.is_turbine
        if aircraft_update.is_active is not None:
            update_data['is_active'] = aircraft_update.is_active

        # Validate type designator requirement
        type_rating_required = aircraft_update.type_rating_required
        if type_rating_required is None:
            type_rating_required = existing_aircraft['type_rating_required']

        type_designator = aircraft_update.type_designator
        if type_designator is None:
            type_designator = existing_aircraft.get('type_designator', None)

        if type_rating_required and not type_designator:
            raise HTTPException(status_code=400, detail="Type Designator is required when Type rating required is true")

        if not update_data:
            raise HTTPException(status_code=400, detail="No data provided for update")

        update_data['updated_at'] = datetime.utcnow().isoformat()

        set_clause = ", ".join([f"{k} = ?" for k in update_data.keys()])
        values = list(update_data.values()) + [aircraft_id]

        cursor.execute(f"UPDATE aircraft SET {set_clause} WHERE id = ?", values)
        conn.commit()

        # Fetch updated aircraft
        cursor.execute("SELECT * FROM aircraft WHERE id = ?", (aircraft_id,))
        result = cursor.fetchone()

        return AircraftResponse(**dict(result))

@app.patch("/aircraft/{aircraft_id}/archive", response_model=AircraftResponse)
def archive_aircraft(aircraft_id: int):
    """Archive (set inactive) an aircraft"""
    with get_db_connection() as conn:
        existing_aircraft = get_aircraft_data(aircraft_id, conn)
        if not existing_aircraft:
            raise HTTPException(status_code=404, detail="Aircraft not found")

        cursor = conn.cursor()
        cursor.execute(
            "UPDATE aircraft SET is_active = FALSE, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (aircraft_id,)
        )
        conn.commit()

        cursor.execute("SELECT * FROM aircraft WHERE id = ?", (aircraft_id,))
        result = cursor.fetchone()
        return AircraftResponse(**dict(result))

@app.patch("/aircraft/{aircraft_id}/unarchive", response_model=AircraftResponse)
def unarchive_aircraft(aircraft_id: int):
    """Unarchive (set active) an aircraft"""
    with get_db_connection() as conn:
        existing_aircraft = get_aircraft_data(aircraft_id, conn)
        if not existing_aircraft:
            raise HTTPException(status_code=404, detail="Aircraft not found")

        cursor = conn.cursor()
        cursor.execute(
            "UPDATE aircraft SET is_active = TRUE, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (aircraft_id,)
        )
        conn.commit()

        cursor.execute("SELECT * FROM aircraft WHERE id = ?", (aircraft_id,))
        result = cursor.fetchone()
        return AircraftResponse(**dict(result))

# FLIGHT ENDPOINTS

@app.post("/flights/", response_model=FlightResponse, status_code=status.HTTP_201_CREATED)
def create_flight(flight: FlightCreate):
    """Create a new flight"""
    with get_db_connection() as conn:
        # Validate aircraft exists and is active
        if not validate_aircraft_exists(flight.aircraft_id, conn):
            raise HTTPException(status_code=404, detail="Aircraft not found")

        if not validate_aircraft_active(flight.aircraft_id, conn):
            raise HTTPException(status_code=400, detail="Cannot use inactive aircraft for new flights")

        cursor = conn.cursor()

        # Insert flight
        cursor.execute('''
        INSERT INTO flights (
            date, aircraft_id, departure, arrival, via, total_time, day_time, night_time,
            pic_time, sic_time, dual_given, dual_received, cross_country,
            actual_instrument, simulated_instrument, day_takeoffs, day_landings,
            night_takeoffs, night_landings, instrument_approaches,
            holds_performed, intercept_track_performed, notes
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            flight.date.isoformat(),
            flight.aircraft_id,
            flight.departure,
            flight.arrival,
            flight.via,
            flight.total_time,
            flight.day_time,
            flight.night_time,
            flight.pic_time,
            flight.sic_time,
            flight.dual_given,
            flight.dual_received,
            flight.cross_country,
            flight.actual_instrument,
            flight.simulated_instrument,
            flight.day_takeoffs,
            flight.day_landings,
            flight.night_takeoffs,
            flight.night_landings,
            flight.instrument_approaches,
            flight.holds_performed,
            flight.intercept_track_performed,
            flight.notes
        ))

        flight_id = cursor.lastrowid
        conn.commit()

        # Fetch the created flight
        cursor.execute("SELECT * FROM flights WHERE id = ?", (flight_id,))
        result = cursor.fetchone()

        return FlightResponse(**dict(result))

@app.get("/flights/", response_model=FlightListResponse)
def list_flights(
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    aircraft_ids: Optional[List[int]] = Query(None),
    categories: Optional[List[str]] = Query(None),
    classes: Optional[List[str]] = Query(None),
    search_text: Optional[str] = None,
    page: int = 1,
    page_size: int = 50
):
    """List flights with optional filters"""
    with get_db_connection() as conn:
        cursor = conn.cursor()

        # Build the base query with joins to get aircraft data
        query = '''
        SELECT f.*, a.registration, a.make_model, a.category, a.class, a.type_designator,
               a.type_rating_required, a.is_complex, a.is_high_performance,
               a.is_tailwheel, a.is_turbine, a.is_active
        FROM flights f
        JOIN aircraft a ON f.aircraft_id = a.id
        '''

        conditions = []
        params = []

        # Date range filter
        if start_date is not None:
            conditions.append("f.date >= ?")
            params.append(start_date.isoformat())
        if end_date is not None:
            conditions.append("f.date <= ?")
            params.append(end_date.isoformat())

        # Aircraft filter
        if aircraft_ids:
            placeholders = ",".join("?" * len(aircraft_ids))
            conditions.append(f"f.aircraft_id IN ({placeholders})")
            params.extend(aircraft_ids)

        # Category/Class filter
        if categories:
            placeholders = ",".join("?" * len(categories))
            conditions.append(f"a.category IN ({placeholders})")
            params.extend(categories)

        if classes:
            placeholders = ",".join("?" * len(classes))
            conditions.append(f"a.class IN ({placeholders})")
            params.extend(classes)

        # Text search across route fields and notes
        if search_text:
            search_pattern = f"%{search_text.lower()}%"
            conditions.append("""
                (LOWER(f.departure) LIKE ? OR
                 LOWER(f.arrival) LIKE ? OR
                 LOWER(f.via) LIKE ? OR
                 LOWER(f.notes) LIKE ?)
            """)
            params.extend([search_pattern] * 4)

        # Combine conditions
        if conditions:
            query += " WHERE " + " AND ".join(conditions)

        # Sort by date descending (most recent first)
        query += " ORDER BY f.date DESC, f.id DESC"

        # Pagination
        offset = (page - 1) * page_size
        query += " LIMIT ? OFFSET ?"
        params.extend([page_size, offset])

        cursor.execute(query, params)
        flights = cursor.fetchall()

        # Count total for pagination
        count_query = "SELECT COUNT(*) FROM flights f JOIN aircraft a ON f.aircraft_id = a.id"
        if conditions:
            count_query += " WHERE " + " AND ".join(conditions)
        cursor.execute(count_query, params[:-2])  # Remove pagination params
        total = cursor.fetchone()['COUNT(*)']

        # Convert to response format
        flight_responses = []
        for flight in flights:
            flight_dict = dict(flight)
            # Remove aircraft fields that aren't part of FlightResponse
            aircraft_fields = ['registration', 'make_model', 'category', 'class',
                              'type_designator', 'type_rating_required', 'is_complex',
                              'is_high_performance', 'is_tailwheel', 'is_turbine', 'is_active']
            for field in aircraft_fields:
                flight_dict.pop(field, None)

            flight_responses.append(FlightResponse(**flight_dict))

        return FlightListResponse(flights=flight_responses, total=total)

@app.get("/flights/{flight_id}", response_model=FlightResponse)
def get_flight(flight_id: int):
    """Get a specific flight by ID"""
    with get_db_connection() as conn:
        flight = get_flight_data(flight_id, conn)
        if not flight:
            raise HTTPException(status_code=404, detail="Flight not found")
        return FlightResponse(**flight)

@app.put("/flights/{flight_id}", response_model=FlightResponse)
def update_flight(flight_id: int, flight_update: FlightUpdate):
    """Update an existing flight"""
    with get_db_connection() as conn:
        # Check if flight exists
        existing_flight = get_flight_data(flight_id, conn)
        if not existing_flight:
            raise HTTPException(status_code=404, detail="Flight not found")

        # Get current aircraft data for validation
        current_aircraft = get_aircraft_data(existing_flight['aircraft_id'], conn)

        # If aircraft_id is being changed, validate new aircraft is active
        new_aircraft_id = flight_update.aircraft_id
        if new_aircraft_id is not None and new_aircraft_id != existing_flight['aircraft_id']:
            if not validate_aircraft_exists(new_aircraft_id, conn):
                raise HTTPException(status_code=404, detail="New aircraft not found")
            if not validate_aircraft_active(new_aircraft_id, conn):
                raise HTTPException(status_code=400, detail="Cannot use inactive aircraft for flights")

        # If aircraft_id is not being changed but current aircraft is inactive, that's allowed
        if new_aircraft_id is None:
            new_aircraft_id = existing_flight['aircraft_id']

        # Build update data
        update_data = {}
        for field, value in flight_update.dict(exclude_unset=True).items():
            if field == 'aircraft_id':
                continue  # Handle separately
            if value is not None:
                update_data[field] = value

        # Handle aircraft_id separately
        if new_aircraft_id != existing_flight['aircraft_id']:
            update_data['aircraft_id'] = new_aircraft_id

        if not update_data:
            raise HTTPException(status_code=400, detail="No data provided for update")

        update_data['updated_at'] = datetime.utcnow().isoformat()

        # Handle date field
        if 'date' in update_data:
            update_data['date'] = update_data['date'].isoformat()

        set_clause = ", ".join([f"{k} = ?" for k in update_data.keys()])
        values = list(update_data.values()) + [flight_id]

        cursor = conn.cursor()
        cursor.execute(f"UPDATE flights SET {set_clause} WHERE id = ?", values)
        conn.commit()

        # Fetch updated flight
        cursor.execute("SELECT * FROM flights WHERE id = ?", (flight_id,))
        result = cursor.fetchone()

        return FlightResponse(**dict(result))

@app.delete("/flights/{flight_id}", response_model=MessageResponse)
def delete_flight(flight_id: int):
    """Delete a flight"""
    with get_db_connection() as conn:
        # Check if flight exists
        existing_flight = get_flight_data(flight_id, conn)
        if not existing_flight:
            raise HTTPException(status_code=404, detail="Flight not found")

        cursor = conn.cursor()
        cursor.execute("DELETE FROM flights WHERE id = ?", (flight_id,))
        conn.commit()

        return MessageResponse(message=f"Flight {flight_id} deleted successfully")

# ANALYTICS ENDPOINTS

def get_analytics_time_range(start_date: Optional[date], end_date: Optional[date], time_range: AnalyticsTimeRange) -> Dict[str, date]:
    """Get the date range for analytics based on parameters"""
    today = get_current_date()

    if time_range == AnalyticsTimeRange.CUSTOM:
        if not start_date or not end_date:
            raise HTTPException(status_code=400, detail="start_date and end_date are required for custom time range")
        if start_date > end_date:
            raise HTTPException(status_code=400, detail="start_date must be before or equal to end_date")
        return {'start_date': start_date, 'end_date': end_date}

    elif time_range == AnalyticsTimeRange.LAST_90_DAYS:
        start_date_calc = today - timedelta(days=89)
        return {'start_date': start_date_calc, 'end_date': today}

    elif time_range == AnalyticsTimeRange.LAST_6_MONTHS:
        start_date_calc = today - relativedelta(months=6) + timedelta(days=1)
        # Go back to the first day of the month 6 months ago
        start_date_calc = date(start_date_calc.year, start_date_calc.month, 1)
        return {'start_date': start_date_calc, 'end_date': today}

    elif time_range == AnalyticsTimeRange.LAST_12_MONTHS:
        start_date_calc = today - relativedelta(months=12) + timedelta(days=1)
        start_date_calc = date(start_date_calc.year, start_date_calc.month, 1)
        return {'start_date': start_date_calc, 'end_date': today}

    return {'start_date': None, 'end_date': today}

def build_analytics_query(filters: Dict, date_range: Dict) -> tuple:
    """Build SQL query for analytics with filters"""
    conditions = []
    params = []

    # Add date range conditions
    if date_range['start_date']:
        conditions.append("f.date >= ?")
        params.append(date_range['start_date'].isoformat())
    if date_range['end_date']:
        conditions.append("f.date <= ?")
        params.append(date_range['end_date'].isoformat())

    # Add aircraft filter if provided
    if filters.get('aircraft_ids'):
        placeholders = ",".join("?" * len(filters['aircraft_ids']))
        conditions.append(f"f.aircraft_id IN ({placeholders})")
        params.extend([str(ac_id) for ac_id in filters['aircraft_ids']])

    # Add category filter if provided
    if filters.get('categories'):
        placeholders = ",".join("?" * len(filters['categories']))
        conditions.append(f"a.category IN ({placeholders})")
        params.extend([cat.value for cat in filters['categories']])

    # Add class filter if provided
    if filters.get('classes'):
        placeholders = ",".join("?" * len(filters['classes']))
        conditions.append(f"a.class IN ({placeholders})")
        params.extend([cls.value for cls in filters['classes']])

    where_clause = " AND ".join(conditions) if conditions else "1=1"

    return where_clause, params

@app.get("/analytics/totals/", response_model=AnalyticsResponse)
def get_analytics_totals(
    time_range: AnalyticsTimeRange = AnalyticsTimeRange.LAST_90_DAYS,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    group_by: Optional[str] = None,
    aircraft_ids: Optional[List[int]] = Query(None),
    categories: Optional[List[AircraftCategory]] = Query(None),
    classes: Optional[List[AircraftClass]] = Query(None)
):
    """Get analytics totals with optional grouping"""
    date_range = get_analytics_time_range(start_date, end_date, time_range)

    filters = {
        'aircraft_ids': aircraft_ids,
        'categories': categories,
        'classes': classes
    }

    where_clause, params = build_analytics_query(filters, date_range)

    with get_db_connection() as conn:
        cursor = conn.cursor()

        # Overall totals query
        overall_query = f'''
        SELECT
            COALESCE(SUM(total_time), 0) as total_time,
            COALESCE(SUM(pic_time), 0) as pic_time,
            COALESCE(SUM(sic_time), 0) as sic_time,
            COALESCE(SUM(night_time), 0) as night_time,
            COALESCE(SUM(actual_instrument), 0) as actual_instrument,
            COALESCE(SUM(simulated_instrument), 0) as simulated_instrument,
            COALESCE(SUM(cross_country), 0) as cross_country,
            COALESCE(SUM(instrument_approaches), 0) as instrument_approaches,
            COALESCE(SUM(day_takeoffs), 0) as day_takeoffs,
            COALESCE(SUM(day_landings), 0) as day_landings,
            COALESCE(SUM(night_takeoffs), 0) as night_takeoffs,
            COALESCE(SUM(night_landings), 0) as night_landings
        FROM flights f
        JOIN aircraft a ON f.aircraft_id = a.id
        WHERE {where_clause}
        '''

        cursor.execute(overall_query, params)
        overall_data = cursor.fetchone()
        overall_totals = TotalsResponse(**dict(overall_data))

        grouped_totals = []
        if group_by == "category_class":
            group_query = f'''
            SELECT
                a.category || ' - ' || a.class as group_key,
                COALESCE(SUM(total_time), 0) as total_time,
                COALESCE(SUM(pic_time), 0) as pic_time,
                COALESCE(SUM(sic_time), 0) as sic_time,
                COALESCE(SUM(night_time), 0) as night_time,
                COALESCE(SUM(actual_instrument), 0) as actual_instrument,
                COALESCE(SUM(simulated_instrument), 0) as simulated_instrument,
                COALESCE(SUM(cross_country), 0) as cross_country,
                COALESCE(SUM(instrument_approaches), 0) as instrument_approaches,
                COALESCE(SUM(day_takeoffs), 0) as day_takeoffs,
                COALESCE(SUM(day_landings), 0) as day_landings,
                COALESCE(SUM(night_takeoffs), 0) as night_takeoffs,
                COALESCE(SUM(night_landings), 0) as night_landings
            FROM flights f
            JOIN aircraft a ON f.aircraft_id = a.id
            WHERE {where_clause}
            GROUP BY a.category, a.class
            ORDER BY a.category, a.class
            '''
            cursor.execute(group_query, params)
            for row in cursor.fetchall():
                grouped_totals.append(GroupedTotals(
                    group_key=row['group_key'],
                    totals=TotalsResponse(**{k: row[k] for k in row.keys() if k != 'group_key'})
                ))

        elif group_by == "make_model":
            group_query = f'''
            SELECT
                a.make_model as group_key,
                COALESCE(SUM(total_time), 0) as total_time,
                COALESCE(SUM(pic_time), 0) as pic_time,
                COALESCE(SUM(sic_time), 0) as sic_time,
                COALESCE(SUM(night_time), 0) as night_time,
                COALESCE(SUM(actual_instrument), 0) as actual_instrument,
                COALESCE(SUM(simulated_instrument), 0) as simulated_instrument,
                COALESCE(SUM(cross_country), 0) as cross_country,
                COALESCE(SUM(instrument_approaches), 0) as instrument_approaches,
                COALESCE(SUM(day_takeoffs), 0) as day_takeoffs,
                COALESCE(SUM(day_landings), 0) as day_landings,
                COALESCE(SUM(night_takeoffs), 0) as night_takeoffs,
                COALESCE(SUM(night_landings), 0) as night_landings
            FROM flights f
            JOIN aircraft a ON f.aircraft_id = a.id
            WHERE {where_clause}
            GROUP BY a.make_model
            ORDER BY a.make_model
            '''
            cursor.execute(group_query, params)
            for row in cursor.fetchall():
                grouped_totals.append(GroupedTotals(
                    group_key=row['group_key'],
                    totals=TotalsResponse(**{k: row[k] for k in row.keys() if k != 'group_key'})
                ))

        return AnalyticsResponse(
            time_range=f"{time_range.value} from {date_range['start_date']} to {date_range['end_date']}",
            overall=overall_totals,
            grouped=grouped_totals if grouped_totals else None
        )

# CURRENCY ENDPOINTS

@app.get("/currency/", response_model=CurrencyResponse)
def get_currency_status(
    calculation_date: Optional[date] = None,
    aircraft_ids: Optional[List[int]] = Query(None),
    categories: Optional[List[AircraftCategory]] = Query(None),
    classes: Optional[List[AircraftClass]] = Query(None)
):
    """Get currency status for all category/class combinations"""
    if calculation_date is None:
        calculation_date = get_current_date()

    with get_db_connection() as conn:
        cursor = conn.cursor()

        # Build filters
        conditions = []
        params = []

        if aircraft_ids:
            placeholders = ",".join("?" * len(aircraft_ids))
            conditions.append(f"f.aircraft_id IN ({placeholders})")
            params.extend([str(ac_id) for ac_id in aircraft_ids])

        if categories:
            placeholders = ",".join("?" * len(categories))
            conditions.append(f"a.category IN ({placeholders})")
            params.extend([cat.value for cat in categories])

        if classes:
            placeholders = ",".join("?" * len(classes))
            conditions.append(f"a.class IN ({placeholders})")
            params.extend([cls.value for cls in classes])

        where_clause = " AND ".join(conditions) if conditions else "1=1"

        # Get all category/class combinations that have flights
        cursor.execute(f'''
        SELECT DISTINCT a.category, a.class, a.type_designator, a.type_rating_required
        FROM flights f
        JOIN aircraft a ON f.aircraft_id = a.id
        WHERE {where_clause}
        ''', params)

        category_class_combinations = cursor.fetchall()

        day_night_currency = []
        instrument_currency_by_category = {}

        # Day/Night Currency - last 90 days inclusive
        day_night_start = calculation_date - timedelta(days=89)

        for combo in category_class_combinations:
            cat = combo['category']
            cls = combo['class']
            type_designator = combo['type_designator']
            type_rating_required = combo['type_rating_required']

            # For day/night currency, we need to group by category/class and (type_designator if type_rating_required)
            group_key = (cat, cls)
            if type_rating_required and type_designator:
                group_key = (cat, cls, type_designator)
            elif type_rating_required:
                # If type rating required but no type designator, skip? Or handle differently?
                # According to spec, type designator becomes required when type_rating_required is true
                # So this shouldn't happen, but just in case
                continue

            # Check if we already processed this group (for day/night currency)
            processed_groups = set()
            if isinstance(group_key, tuple):
                group_str = "|".join(str(gk) for gk in group_key)
            else:
                group_str = str(group_key)

            if group_str in processed_groups:
                continue
            processed_groups.add(group_str)

            # Get counts for this group
            if type_rating_required and type_designator:
                group_where = "a.category = ? AND a.class = ? AND a.type_designator = ?"
                group_params = [cat, cls, type_designator]
            else:
                group_where = "a.category = ? AND a.class = ?"
                group_params = [cat, cls]

            if conditions:
                full_where = f"({group_where}) AND f.date >= ? AND f.date <= ? AND {where_clause}"
                full_params = group_params + [day_night_start.isoformat(), calculation_date.isoformat()] + params
            else:
                full_where = f"{group_where} AND f.date >= ? AND f.date <= ?"
                full_params = group_params + [day_night_start.isoformat(), calculation_date.isoformat()]

            cursor.execute(f'''
            SELECT
                COALESCE(SUM(day_takeoffs), 0) as day_takeoffs,
                COALESCE(SUM(day_landings), 0) as day_landings,
                COALESCE(SUM(night_takeoffs), 0) as night_takeoffs,
                COALESCE(SUM(night_landings), 0) as night_landings
            FROM flights f
            JOIN aircraft a ON f.aircraft_id = a.id
            WHERE {full_where}
            ''', full_params)

            counts = cursor.fetchone()

            day_takeoffs = counts['day_takeoffs'] or 0
            day_landings = counts['day_landings'] or 0
            night_takeoffs = counts['night_takeoffs'] or 0
            night_landings = counts['night_landings'] or 0

            day_status = "Current" if day_takeoffs >= 3 and day_landings >= 3 else "Not Current"
            night_status = "Current" if night_takeoffs >= 3 and night_landings >= 3 else "Not Current"

            day_night_currency.append(DayNightCurrencyResponse(
                category=cat,
                class_=cls,
                type_designator=type_designator if type_rating_required else None,
                day_status=f"Day TO {day_takeoffs}/3; Day LDG {day_landings}/3; {day_status}",
                day_takeoffs=day_takeoffs,
                day_landings=day_landings,
                night_status=f"Night TO {night_takeoffs}/3; Night LDG {night_landings}/3; {night_status}",
                night_takeoffs=night_takeoffs,
                night_landings=night_landings
            ))

            # Collect for instrument currency (by category only)
            if cat not in instrument_currency_by_category:
                instrument_currency_by_category[cat] = {
                    'total_approaches': 0,
                    'holds_performed': False,
                    'intercept_track_performed': False
                }

        # Instrument Currency - last 6 calendar months
        current_year = calculation_date.year
        current_month = calculation_date.month

        # Calculate start of the 6-month window (6 calendar months ending with current month)
        start_month = current_month - 5
        start_year = current_year
        if start_month < 1:
            start_month += 12
            start_year -= 1
            if start_year < 1:
                start_year = 1

        window_start_date = date(start_year, start_month, 1)
        window_end_date = date(current_year, current_month + 1, 1) - timedelta(days=1)

        # Get instrument currency data by category
        if conditions:
            full_where = f"f.date >= ? AND f.date <= ? AND {where_clause}"
            full_params = [window_start_date.isoformat(), window_end_date.isoformat()] + params
        else:
            full_where = "f.date >= ? AND f.date <= ?"
            full_params = [window_start_date.isoformat(), window_end_date.isoformat()]

        cursor.execute(f'''
        SELECT
            a.category,
            COALESCE(SUM(instrument_approaches), 0) as total_approaches,
            MAX(holds_performed) as holds_performed,
            MAX(intercept_track_performed) as intercept_track_performed
        FROM flights f
        JOIN aircraft a ON f.aircraft_id = a.id
        WHERE {full_where}
        GROUP BY a.category
        ''', full_params)

        instrument_currency_list = []
        categories_with_flights = {combo['category'] for combo in category_class_combinations}

        for row in cursor.fetchall():
            cat = row['category']
            approaches = row['total_approaches'] or 0
            holds = bool(row['holds_performed'])
            intercept = bool(row['intercept_track_performed'])

            if cat in categories_with_flights:
                if approaches >= 6 and holds and intercept:
                    status = "Current"
                else:
                    status = "Not Current"

                instrument_currency_list.append(InstrumentCurrencyResponse(
                    category=cat,
                    status=status,
                    instrument_approaches=approaches,
                    holds_performed=holds,
                    intercept_track_performed=intercept
                ))

        return CurrencyResponse(
            day_night_currency=day_night_currency,
            instrument_currency=instrument_currency_list
        )

# EXPORT ENDPOINTS

def format_boolean(value):
    """Format boolean for CSV export"""
    return str(value).lower() if isinstance(value, bool) else value

@app.get("/export/")
def export_flights_csv(
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    aircraft_ids: Optional[List[int]] = Query(None),
    categories: Optional[List[str]] = Query(None),
    classes: Optional[List[str]] = Query(None),
    search_text: Optional[str] = None
):
    """Export flights as CSV file"""
    with get_db_connection() as conn:
        cursor = conn.cursor()

        # Build the query (similar to list_flights but with aircraft data)
        query = '''
        SELECT
            f.id, f.date, f.departure, f.arrival, f.via, f.total_time, f.day_time, f.night_time,
            f.pic_time, f.sic_time, f.dual_given, f.dual_received, f.cross_country,
            f.actual_instrument, f.simulated_instrument, f.day_takeoffs, f.day_landings,
            f.night_takeoffs, f.night_landings, f.instrument_approaches,
            f.holds_performed, f.intercept_track_performed, f.notes,
            a.registration, a.make_model, a.category, a.class, a.type_designator,
            a.type_rating_required, a.is_complex, a.is_high_performance,
            a.is_tailwheel, a.is_turbine, a.is_active
        FROM flights f
        JOIN aircraft a ON f.aircraft_id = a.id
        '''

        conditions = []
        params = []

        if start_date is not None:
            conditions.append("f.date >= ?")
            params.append(start_date.isoformat())
        if end_date is not None:
            conditions.append("f.date <= ?")
            params.append(end_date.isoformat())
        if aircraft_ids:
            placeholders = ",".join("?" * len(aircraft_ids))
            conditions.append(f"f.aircraft_id IN ({placeholders})")
            params.extend([str(ac_id) for ac_id in aircraft_ids])
        if categories:
            placeholders = ",".join("?" * len(categories))
            conditions.append(f"a.category IN ({placeholders})")
            params.extend(categories)
        if classes:
            placeholders = ",".join("?" * len(classes))
            conditions.append(f"a.class IN ({placeholders})")
            params.extend(classes)
        if search_text:
            search_pattern = f"%{search_text.lower()}%"
            conditions.append("""
                (LOWER(f.departure) LIKE ? OR
                 LOWER(f.arrival) LIKE ? OR
                 LOWER(f.via) LIKE ? OR
                 LOWER(f.notes) LIKE ?)
            """)
            params.extend([search_pattern] * 4)

        if conditions:
            query += " WHERE " + " AND ".join(conditions)

        query += " ORDER BY f.date DESC, f.id DESC"

        cursor.execute(query, params)
        flights = cursor.fetchall()

        # Create CSV in memory
        output = io.StringIO()
        writer = csv.writer(output)

        # Write header
        header = [
            'id', 'date', 'departure', 'arrival', 'via', 'total_time', 'day_time', 'night_time',
            'pic_time', 'sic_time', 'dual_given', 'dual_received', 'cross_country',
            'actual_instrument', 'simulated_instrument', 'day_takeoffs', 'day_landings',
            'night_takeoffs', 'night_landings', 'instrument_approaches',
            'holds_performed', 'intercept_track_performed', 'notes',
            'aircraft_registration', 'aircraft_make_model', 'aircraft_category', 'aircraft_class',
            'aircraft_type_designator', 'aircraft_type_rating_required', 'aircraft_is_complex',
            'aircraft_is_high_performance', 'aircraft_is_tailwheel', 'aircraft_is_turbine',
            'aircraft_is_active'
        ]
        writer.writerow(header)

        # Write data rows
        for flight in flights:
            row = [
                flight['id'],
                flight['date'],
                flight['departure'],
                flight['arrival'],
                flight['via'] or '',
                "{:.1f}".format(flight["total_time"]),
                "{:.1f}".format(flight["day_time"]),
                "{:.1f}".format(flight["night_time"]),
                "{:.1f}".format(flight["pic_time"]),
                "{:.1f}".format(flight["sic_time"]),
                "{:.1f}".format(flight["dual_given"]),
                "{:.1f}".format(flight["dual_received"]),
                "{:.1f}".format(flight["cross_country"]),
                "{:.1f}".format(flight["actual_instrument"]),
                "{:.1f}".format(flight["simulated_instrument"]),                flight['day_landings'],
                flight['night_takeoffs'],
                flight['night_landings'],
                flight['instrument_approaches'],
                format_boolean(flight['holds_performed']),
                format_boolean(flight['intercept_track_performed']),
                flight['notes'] or '',
                flight['registration'],
                flight['make_model'],
                flight['category'],
                flight['class'],
                flight['type_designator'] or '',
                format_boolean(flight['type_rating_required']),
                format_boolean(flight['is_complex']),
                format_boolean(flight['is_high_performance']),
                format_boolean(flight['is_tailwheel']),
                format_boolean(flight['is_turbine']),
                format_boolean(flight['is_active'])
            ]
            writer.writerow(row)

        # Return CSV file
        csv_content = output.getvalue()
        output.close()

        return {
            'content': csv_content,
            'media_type': 'text/csv',
            'filename': f'logbook_export_{datetime.utcnow().strftime("%Y%m%d_%H%M%S")}.csv',
        }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
