import csv
import io
import re
from enum import Enum
from datetime import date, timedelta
from calendar import monthrange
from typing import Optional, List
from fastapi import FastAPI, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_

from database import engine, get_db, Base
from models import Aircraft, Flight
from schemas import (
    AircraftCreate, AircraftUpdate, AircraftResponse,
    FlightCreate, FlightUpdate, FlightResponse, FlightDetailResponse,
    CategoryEnum, ClassEnum
)
from contextlib import asynccontextmanager

VALID_CATEGORY_CLASS = {
    "Airplane": {"SEL", "SES", "MEL", "MES"},
    "Rotorcraft": {"Helicopter", "Gyroplane"},
    "Glider": {"Glider"},
}

@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    yield

app = FastAPI(lifespan=lifespan)


def canonical_reg(reg: str) -> str:
    return re.sub(r'[\s-]', '', reg).upper()

def validate_category_class(category: str, aircraft_class: str):
    valid_classes = VALID_CATEGORY_CLASS.get(category, set())
    if aircraft_class not in valid_classes:
        raise HTTPException(400, f"Invalid class '{aircraft_class}' for category '{category}'")


# -------- Aircraft --------
@app.get("/aircraft", response_model=List[AircraftResponse])
def list_aircraft(db: Session = Depends(get_db), include_inactive: bool = False):
    q = db.query(Aircraft)
    if not include_inactive:
        q = q.filter(Aircraft.active == True)
    return q.all()

@app.post("/aircraft", response_model=AircraftResponse, status_code=201)
def create_aircraft(data: AircraftCreate, db: Session = Depends(get_db)):
    validate_category_class(data.category.value, data.aircraft_class.value)
    can = canonical_reg(data.registration)
    if db.query(Aircraft).filter(Aircraft.registration_canonical == can).first():
        raise HTTPException(409, "Aircraft with this registration already exists")
    ac = Aircraft(
        registration=data.registration.strip(),
        registration_canonical=can,
        make_model=data.make_model,
        category=data.category.value,
        aircraft_class=data.aircraft_class.value,
        type_designator=data.type_designator,
        type_rating_required=data.type_rating_required,
        complex_ac=data.complex_ac,
        high_performance=data.high_performance,
        tailwheel=data.tailwheel,
        turbine=data.turbine,
        active=True,
    )
    db.add(ac)
    db.commit()
    db.refresh(ac)
    return ac

@app.get("/aircraft/{ac_id}", response_model=AircraftResponse)
def get_aircraft(ac_id: int, db: Session = Depends(get_db)):
    ac = db.query(Aircraft).filter(Aircraft.id == ac_id).first()
    if not ac:
        raise HTTPException(404, "Aircraft not found")
    return ac

@app.put("/aircraft/{ac_id}", response_model=AircraftResponse)
def update_aircraft(ac_id: int, data: AircraftUpdate, db: Session = Depends(get_db)):
    ac = db.query(Aircraft).filter(Aircraft.id == ac_id).first()
    if not ac:
        raise HTTPException(404, "Aircraft not found")
    update_data = data.dict(exclude_unset=True)

    if 'registration' in update_data:
        can = canonical_reg(update_data['registration'].strip())
        exist = db.query(Aircraft).filter(Aircraft.registration_canonical == can, Aircraft.id != ac_id).first()
        if exist:
            raise HTTPException(409, "Aircraft with this registration already exists")
        ac.registration = update_data['registration'].strip()
        ac.registration_canonical = can
        del update_data['registration']

    cat_val = update_data.get('category', CategoryEnum(ac.category)).value if 'category' in update_data else ac.category
    cls_val = update_data.get('aircraft_class', ClassEnum(ac.aircraft_class)).value if 'aircraft_class' in update_data else ac.aircraft_class
    if 'category' in update_data or 'aircraft_class' in update_data:
        validate_category_class(cat_val, cls_val)

    for field, value in update_data.items():
        if hasattr(ac, field):
            if isinstance(value, Enum):
                value = value.value
            setattr(ac, field, value)

    if ac.type_rating_required and not ac.type_designator:
        raise HTTPException(400, "Type designator required when type rating required is true")
    db.commit()
    db.refresh(ac)
    return ac

@app.post("/aircraft/{ac_id}/archive")
def archive_aircraft(ac_id: int, db: Session = Depends(get_db)):
    ac = db.query(Aircraft).filter(Aircraft.id == ac_id).first()
    if not ac:
        raise HTTPException(404, "Aircraft not found")
    ac.active = False
    db.commit()
    return {"message": "Aircraft archived"}

@app.post("/aircraft/{ac_id}/unarchive")
def unarchive_aircraft(ac_id: int, db: Session = Depends(get_db)):
    ac = db.query(Aircraft).filter(Aircraft.id == ac_id).first()
    if not ac:
        raise HTTPException(404, "Aircraft not found")
    ac.active = True
    db.commit()
    return {"message": "Aircraft unarchived"}


# -------- Flights --------
@app.get("/flights", response_model=List[FlightDetailResponse])
def list_flights(
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    aircraft_ids: Optional[str] = Query(None),
    category: Optional[str] = None,
    aircraft_class: Optional[str] = None,
    search: Optional[str] = None,
    db: Session = Depends(get_db)
):
    q = db.query(Flight).join(Aircraft)
    conds = []
    if start_date:
        conds.append(Flight.date >= start_date)
    if end_date:
        conds.append(Flight.date <= end_date)
    if aircraft_ids:
        ids = [int(x.strip()) for x in aircraft_ids.split(",") if x.strip()]
        conds.append(Flight.aircraft_id.in_(ids))
    if category:
        conds.append(Aircraft.category == category)
    if aircraft_class:
        conds.append(Aircraft.aircraft_class == aircraft_class)
    if search:
        like = f"%{search}%"
        conds.append(or_(Flight.departure.ilike(like), Flight.arrival.ilike(like),
                         Flight.via.ilike(like), Flight.notes.ilike(like)))
    if conds:
        q = q.filter(and_(*conds))
    return q.order_by(Flight.date.desc(), Flight.id.desc()).all()

@app.post("/flights", response_model=FlightDetailResponse, status_code=201)
def create_flight(data: FlightCreate, db: Session = Depends(get_db)):
    ac = db.query(Aircraft).filter(Aircraft.id == data.aircraft_id).first()
    if not ac:
        raise HTTPException(404, "Aircraft not found")
    if not ac.active:
        raise HTTPException(400, "Cannot log flight on inactive aircraft")
    flight = Flight(**data.dict())
    db.add(flight)
    db.commit()
    db.refresh(flight)
    return db.query(Flight).filter(Flight.id == flight.id).first()

@app.get("/flights/{flight_id}", response_model=FlightDetailResponse)
def get_flight(flight_id: int, db: Session = Depends(get_db)):
    f = db.query(Flight).filter(Flight.id == flight_id).first()
    if not f:
        raise HTTPException(404, "Flight not found")
    return f

@app.put("/flights/{flight_id}", response_model=FlightDetailResponse)
def update_flight(flight_id: int, data: FlightUpdate, db: Session = Depends(get_db)):
    f = db.query(Flight).filter(Flight.id == flight_id).first()
    if not f:
        raise HTTPException(404, "Flight not found")
    upd = data.dict(exclude_unset=True)

    if 'aircraft_id' in upd:
        ac = db.query(Aircraft).filter(Aircraft.id == upd['aircraft_id']).first()
        if not ac:
            raise HTTPException(404, "Aircraft not found")
        if not ac.active:
            raise HTTPException(400, "Cannot use inactive aircraft")
        f.aircraft_id = upd['aircraft_id']
        del upd['aircraft_id']

    for field, value in upd.items():
        if hasattr(f, field):
            setattr(f, field, value)

    # validation
    for attr in ["total_time","day_time","night_time","pic","sic","dual_given",
                 "dual_received","cross_country","actual_instrument","simulated_instrument"]:
        v = getattr(f, attr)
        if v is not None and abs((v * 10) % 1) > 1e-9 and abs((v * 10) % 1) < (1 - 1e-9):
            raise HTTPException(400, "Times must be in 0.1 hour increments")
    if abs(f.day_time + f.night_time - f.total_time) > 1e-9:
        raise HTTPException(400, "Day Time + Night Time must equal Total Time exactly")
    if f.actual_instrument + f.simulated_instrument > f.total_time + 1e-9:
        raise HTTPException(400, "Actual + Simulated Instrument cannot exceed Total Time")
    if f.pic > 0 and f.sic > 0:
        raise HTTPException(400, "PIC and SIC cannot both be > 0")
    if f.pic + f.sic > f.total_time + 1e-9:
        raise HTTPException(400, "PIC + SIC cannot exceed Total Time")
    if f.dual_given > 0 and f.dual_received > 0:
        raise HTTPException(400, "Dual Given and Dual Received cannot both be > 0")
    if f.dual_given > f.total_time + 1e-9:
        raise HTTPException(400, "Dual Given cannot exceed Total Time")
    if f.dual_received > f.total_time + 1e-9:
        raise HTTPException(400, "Dual Received cannot exceed Total Time")
    if f.cross_country > f.total_time + 1e-9:
        raise HTTPException(400, "Cross-country cannot exceed Total Time")

    db.commit()
    db.refresh(f)
    return f

@app.delete("/flights/{flight_id}")
def delete_flight(flight_id: int, db: Session = Depends(get_db)):
    f = db.query(Flight).filter(Flight.id == flight_id).first()
    if not f:
        raise HTTPException(404, "Flight not found")
    db.delete(f)
    db.commit()
    return {"message": "Flight deleted"}


# -------- Analytics & Currency --------
@app.get("/analytics/totals")
def get_totals(
    preset: Optional[str] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    group_by: str = "overall",
    aircraft_ids: Optional[str] = Query(None),
    category: Optional[str] = None,
    aircraft_class: Optional[str] = None,
    search: Optional[str] = None,
    db: Session = Depends(get_db)
):
    today = date.today()
    if preset == "90d":
        start_date, end_date = today - timedelta(days=89), today
    elif preset == "6m":
        start_date, end_date = today - timedelta(days=180), today
    elif preset == "12m":
        start_date, end_date = today - timedelta(days=365), today
    else:
        start_date = start_date or date(1900, 1, 1)
        end_date = end_date or today

    q = db.query(Flight).join(Aircraft).filter(Flight.date >= start_date, Flight.date <= end_date)
    if aircraft_ids:
        ids = [int(x.strip()) for x in aircraft_ids.split(",") if x.strip()]
        q = q.filter(Flight.aircraft_id.in_(ids))
    if category:
        q = q.filter(Aircraft.category == category)
    if aircraft_class:
        q = q.filter(Aircraft.aircraft_class == aircraft_class)
    if search:
        like = f"%{search}%"
        q = q.filter(or_(Flight.departure.ilike(like), Flight.arrival.ilike(like),
                         Flight.via.ilike(like), Flight.notes.ilike(like)))
    flights = q.all()

    def aggregate(fl):
        return {
            "total_time": sum(f.total_time for f in fl),
            "pic": sum(f.pic for f in fl),
            "sic": sum(f.sic for f in fl),
            "night": sum(f.night_time for f in fl),
            "actual_instrument": sum(f.actual_instrument for f in fl),
            "simulated_instrument": sum(f.simulated_instrument for f in fl),
            "cross_country": sum(f.cross_country for f in fl),
            "approaches": sum(f.instrument_approaches for f in fl),
            "day_takeoffs": sum(f.day_takeoffs for f in fl),
            "day_landings": sum(f.day_landings for f in fl),
            "night_takeoffs": sum(f.night_takeoffs for f in fl),
            "night_landings": sum(f.night_landings for f in fl),
            "flight_count": len(fl),
        }

    if group_by == "overall":
        return [{"group": "overall", **aggregate(flights)}]
    if group_by == "category_class":
        groups = {}
        for f in flights:
            key = f"{f.aircraft.category}|{f.aircraft.aircraft_class}"
            groups.setdefault(key, []).append(f)
        return [{"group": {"category": k.split("|")[0], "class": k.split("|")[1]}, **aggregate(v)} for k, v in groups.items()]
    if group_by == "make_model":
        groups = {}
        for f in flights:
            groups.setdefault(f.aircraft.make_model, []).append(f)
        return [{"group": {"make_model": k}, **aggregate(v)} for k, v in groups.items()]
    raise HTTPException(400, "Invalid group_by")

@app.get("/analytics/currency")
def get_currency(db: Session = Depends(get_db)):
    today = date.today()
    d_start = today - timedelta(days=89)
    em, ey = today.month, today.year
    sm = today.month - 5
    sy = today.year
    if sm <= 0:
        sm += 12
        sy -= 1
    i_start = date(sy, sm, 1)
    i_end = date(ey, em, monthrange(ey, em)[1])

    day_flights = db.query(Flight).join(Aircraft).filter(Flight.date >= d_start, Flight.date <= today).all()
    inst_flights = db.query(Flight).join(Aircraft).filter(Flight.date >= i_start, Flight.date <= i_end).all()

    dg = {}  # day groups: (cat, cls) -> {takeoffs, landings, night_takeoffs, night_landings, td_groups: {td: ...}}
    for f in day_flights:
        cat, cls = f.aircraft.category, f.aircraft.aircraft_class
        td = f.aircraft.type_designator if f.aircraft.type_rating_required else None
        g = dg.setdefault((cat, cls), {'takeoffs': 0, 'landings': 0, 'night_takeoffs': 0, 'night_landings': 0, 'td_groups': {}})
        g['takeoffs'] += f.day_takeoffs
        g['landings'] += f.day_landings
        g['night_takeoffs'] += f.night_takeoffs
        g['night_landings'] += f.night_landings
        if td:
            tg = g['td_groups'].setdefault(td, {'takeoffs': 0, 'landings': 0, 'night_takeoffs': 0, 'night_landings': 0})
            tg['takeoffs'] += f.day_takeoffs
            tg['landings'] += f.day_landings
            tg['night_takeoffs'] += f.night_takeoffs
            tg['night_landings'] += f.night_landings

    ig = {}  # instrument groups: cat -> {approaches, holds, intercept}
    for f in inst_flights:
        cat = f.aircraft.category
        igc = ig.setdefault(cat, {'approaches': 0, 'holds': False, 'intercept': False})
        igc['approaches'] += f.instrument_approaches
        if f.holds_performed:
            igc['holds'] = True
        if f.intercept_track:
            igc['intercept'] = True

    result = []
    all_combos = db.query(Aircraft.category, Aircraft.aircraft_class).join(Flight).distinct().all()
    for cat, cls in all_combos:
        dd = dg.get((cat, cls), {'takeoffs': 0, 'landings': 0, 'night_takeoffs': 0, 'night_landings': 0, 'td_groups': {}})
        idata = ig.get(cat, {'approaches': 0, 'holds': False, 'intercept': False})
        result.append({
            "category": cat, "aircraft_class": cls, "type_designator": None,
            "day_current": dd['takeoffs'] >= 3 and dd['landings'] >= 3,
            "day_takeoffs": dd['takeoffs'], "day_landings": dd['landings'],
            "night_current": dd['night_takeoffs'] >= 3 and dd['night_landings'] >= 3,
            "night_takeoffs": dd['night_takeoffs'], "night_landings": dd['night_landings'],
            "instrument_current": idata['approaches'] >= 6 and idata['holds'] and idata['intercept'],
            "instrument_approaches": idata['approaches'],
            "holds_performed_any": idata['holds'],
            "intercept_track_any": idata['intercept'],
        })
        for td, td_data in dd.get('td_groups', {}).items():
            result.append({
                "category": cat, "aircraft_class": cls, "type_designator": td,
                "day_current": td_data['takeoffs'] >= 3 and td_data['landings'] >= 3,
                "day_takeoffs": td_data['takeoffs'], "day_landings": td_data['landings'],
                "night_current": td_data['night_takeoffs'] >= 3 and td_data['night_landings'] >= 3,
                "night_takeoffs": td_data['night_takeoffs'], "night_landings": td_data['night_landings'],
                "instrument_current": None, "instrument_approaches": None,
                "holds_performed_any": None, "intercept_track_any": None,
            })
    return result


# -------- Export --------
@app.get("/export/csv")
def export_csv(
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    aircraft_ids: Optional[str] = Query(None),
    category: Optional[str] = None,
    aircraft_class: Optional[str] = None,
    search: Optional[str] = None,
    db: Session = Depends(get_db)
):
    q = db.query(Flight).join(Aircraft)
    conds = []
    if start_date:
        conds.append(Flight.date >= start_date)
    if end_date:
        conds.append(Flight.date <= end_date)
    if aircraft_ids:
        ids = [int(x.strip()) for x in aircraft_ids.split(",") if x.strip()]
        conds.append(Flight.aircraft_id.in_(ids))
    if category:
        conds.append(Aircraft.category == category)
    if aircraft_class:
        conds.append(Aircraft.aircraft_class == aircraft_class)
    if search:
        like = f"%{search}%"
        conds.append(or_(Flight.departure.ilike(like), Flight.arrival.ilike(like),
                         Flight.via.ilike(like), Flight.notes.ilike(like)))
    if conds:
        q = q.filter(and_(*conds))
    flights = q.order_by(Flight.date.desc(), Flight.id.desc()).all()

    output = io.StringIO()
    writer = csv.writer(output, lineterminator='\n')
    writer.writerow([
        "Date", "Aircraft Registration", "Aircraft Make/Model", "Aircraft Category", "Aircraft Class",
        "Aircraft Type Designator", "Aircraft Type Rating Required", "Aircraft Complex",
        "Aircraft High Performance", "Aircraft Tailwheel", "Aircraft Turbine",
        "Departure", "Arrival", "Via", "Total Time", "Day Time", "Night Time",
        "PIC", "SIC", "Dual Given", "Dual Received", "Cross Country",
        "Actual Instrument", "Simulated Instrument", "Day Takeoffs", "Day Landings",
        "Night Takeoffs", "Night Landings", "Instrument Approaches",
        "Holds Performed", "Intercept/Track", "Notes"
    ])
    for f in flights:
        writer.writerow([
            f.date.isoformat(),
            f.aircraft.registration,
            f.aircraft.make_model,
            f.aircraft.category,
            f.aircraft.aircraft_class,
            f.aircraft.type_designator or "",
            str(f.aircraft.type_rating_required).lower(),
            str(f.aircraft.complex_ac).lower(),
            str(f.aircraft.high_performance).lower(),
            str(f.aircraft.tailwheel).lower(),
            str(f.aircraft.turbine).lower(),
            f.departure,
            f.arrival,
            f.via or "",
            f"{f.total_time:.1f}",
            f"{f.day_time:.1f}",
            f"{f.night_time:.1f}",
            f"{f.pic:.1f}",
            f"{f.sic:.1f}",
            f"{f.dual_given:.1f}",
            f"{f.dual_received:.1f}",
            f"{f.cross_country:.1f}",
            f"{f.actual_instrument:.1f}",
            f"{f.simulated_instrument:.1f}",
            str(f.day_takeoffs or 0),
            str(f.day_landings or 0),
            str(f.night_takeoffs or 0),
            str(f.night_landings or 0),
            str(f.instrument_approaches or 0),
            str(f.holds_performed).lower(),
            str(f.intercept_track).lower(),
            f.notes or "",
        ])
    return Response(content=output.getvalue(), media_type="text/csv",
                    headers={"Content-Disposition": "attachment; filename=logbook_export.csv"})
