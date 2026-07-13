import uvicorn
from fastapi import FastAPI, HTTPException, Query
from typing import List, Optional, Dict, Any
from datetime import date, datetime, timedelta
from pydantic import BaseModel, Field, root_validator, validator
import csv
import io

app = FastAPI(title="Pilot Logbook")

# ---------- Utilities ----------
def normalize_reg(reg: str) -> str:
    return reg.upper().replace(" ", "").replace("-", "")

def utc_today() -> date:
    return datetime.utcnow().date()

def round_to_tenth(value: float) -> float:
    return round(value * 10) / 10.0

def is_multiple_of_tenth(value: float) -> bool:
    return abs(round_to_tenth(value) - value) < 1e-9

# ---------- In‑memory storage ----------
aircraft_store: Dict[str, Dict[str, Any]] = {}   # key = normalized reg
flight_store: Dict[int, Dict[str, Any]] = {}    # key = auto id
next_flight_id = 1

# ---------- Models ----------
class AircraftFlags(BaseModel):
    type_rating_required: bool = False
    complex: bool = False
    high_performance: bool = False
    tailwheel: bool = False
    turbine: bool = False

class AircraftBase(BaseModel):
    registration: str = Field(..., alias="Registration/Tail No.")
    make_model: str = Field(..., alias="Make/Model")
    category: str = Field(..., alias="Category")
    aircraft_class: str = Field(..., alias="Class")
    type_designator: Optional[str] = Field(None, alias="Type Designator")
    flags: AircraftFlags = Field(default_factory=AircraftFlags)

    @validator("registration")
    def reg_not_empty(cls, v):
        if not v.strip():
            raise ValueError("Registration required")
        return v

    @root_validator
    def type_designator_required_if_needed(cls, values):
        flags: AircraftFlags = values.get("flags")
        td = values.get("type_designator")
        if flags and flags.type_rating_required and not td:
            raise ValueError("Type Designator required when type rating is required")
        return values

class AircraftCreate(AircraftBase):
    pass

class AircraftUpdate(BaseModel):
    make_model: Optional[str] = None
    category: Optional[str] = None
    aircraft_class: Optional[str] = None
    type_designator: Optional[str] = None
    flags: Optional[AircraftFlags] = None
    active: Optional[bool] = None   # archive/unarchive

class AircraftOut(AircraftBase):
    active: bool

class FlightTimes(BaseModel):
    total_time: float = Field(..., gt=0, alias="Total Time")
    day_time: float = Field(0, alias="Day Time")
    night_time: float = Field(0, alias="Night Time")
    pic: float = Field(0, alias="PIC")
    sic: float = Field(0, alias="SIC")
    dual_given: float = Field(0, alias="Dual Given")
    dual_received: float = Field(0, alias="Dual Received")
    cross_country: float = Field(0, alias="Cross-country")
    actual_instrument: float = Field(0, alias="Actual Instrument")
    simulated_instrument: float = Field(0, alias="Simulated Instrument")

    @validator("*", pre=True)
    def check_multiple_of_tenth(cls, v):
        if v is None:
            return 0
        if not isinstance(v, (int, float)):
            raise ValueError("must be a number")
        if v < 0:
            raise ValueError("must be non‑negative")
        if not is_multiple_of_tenth(v):
            raise ValueError("must be in 0.1 hour increments")
        return v

    @root_validator
    def validate_logic(cls, values):
        total = values.get("total_time")
        day = values.get("day_time")
        night = values.get("night_time")
        if round_to_tenth(day + night) != round_to_tenth(total):
            raise ValueError("Day Time + Night Time must equal Total Time")
        if values.get("actual_instrument") + values.get("simulated_instrument") > total:
            raise ValueError("Instrument times exceed Total Time")
        if values.get("pic") > 0 and values.get("sic") > 0:
            raise ValueError("PIC and SIC cannot both be > 0")
        if values.get("pic") + values.get("sic") > total:
            raise ValueError("PIC+SIC exceeds Total Time")
        if values.get("dual_given") > 0 and values.get("dual_received") > 0:
            raise ValueError("Dual Given and Dual Received cannot both be > 0")
        for k in ["dual_given", "dual_received", "pic", "sic", "cross_country"]:
            if values.get(k) > total:
                raise ValueError(f"{k} cannot exceed Total Time")
        return values

class FlightCounts(BaseModel):
    day_takeoffs: int = Field(0, ge=0, alias="Day Takeoffs")
    day_landings: int = Field(0, ge=0, alias="Day Landings")
    night_takeoffs: int = Field(0, ge=0, alias="Night Takeoffs")
    night_landings: int = Field(0, ge=0, alias="Night Landings")
    instrument_approaches: int = Field(0, ge=0, alias="Instrument Approaches")

class FlightIFR(BaseModel):
    holds_performed: bool = False
    intercept_track_performed: bool = False

class FlightBase(BaseModel):
    date: date = Field(..., alias="Date")
    aircraft_registration: str = Field(..., alias="Aircraft")
    route_departure: str = Field(..., alias="Departure")
    route_arrival: str = Field(..., alias="Arrival")
    route_via: Optional[str] = Field(None, alias="Via")
    notes: Optional[str] = None
    times: FlightTimes
    counts: FlightCounts
    ifr: FlightIFR

    @validator("date")
    def not_future(cls, v):
        if v > utc_today():
            raise ValueError("Date cannot be in the future")
        return v

class FlightCreate(FlightBase):
    pass

class FlightUpdate(BaseModel):
    date: Optional[date] = None
    aircraft_registration: Optional[str] = None
    route_departure: Optional[str] = None
    route_arrival: Optional[str] = None
    route_via: Optional[str] = None
    notes: Optional[str] = None
    times: Optional[FlightTimes] = None
    counts: Optional[FlightCounts] = None
    ifr: Optional[FlightIFR] = None

class FlightOut(FlightBase):
    id: int

# ---------- Aircraft Endpoints ----------
@app.post("/aircraft", response_model=AircraftOut)
def create_aircraft(ac: AircraftCreate):
    norm = normalize_reg(ac.registration)
    if norm in aircraft_store:
        raise HTTPException(400, "Aircraft with this registration already exists")
    record = ac.dict(by_alias=True)
    record["active"] = True
    aircraft_store[norm] = record
    return AircraftOut(**record)

@app.get("/aircraft", response_model=List[AircraftOut])
def list_aircraft(active: Optional[bool] = None):
    result = []
    for rec in aircraft_store.values():
        if active is None or rec["active"] == active:
            result.append(AircraftOut(**rec))
    return result

@app.patch("/aircraft/{registration}", response_model=AircraftOut)
def update_aircraft(registration: str, upd: AircraftUpdate):
    norm = normalize_reg(registration)
    if norm not in aircraft_store:
        raise HTTPException(404, "Aircraft not found")
    rec = aircraft_store[norm]
    update_data = upd.dict(exclude_unset=True)
    for k, v in update_data.items():
        if k == "flags" and v is not None:
            rec["flags"].update(v.dict())
        else:
            rec[k] = v
    # enforce type designator rule if needed
    if rec["flags"]["type_rating_required"] and not rec.get("type_designator"):
        raise HTTPException(400, "Type Designator required for type‑rated aircraft")
    aircraft_store[norm] = rec
    return AircraftOut(**rec)

# ---------- Flight Endpoints ----------
@app.post("/flights", response_model=FlightOut)
def create_flight(fl: FlightCreate):
    global next_flight_id
    # verify aircraft exists and is active
    norm = normalize_reg(fl.aircraft_registration)
    ac = aircraft_store.get(norm)
    if not ac or not ac["active"]:
        raise HTTPException(400, "Aircraft must be active")
    # store flight
    rec = fl.dict(by_alias=True)
    rec["id"] = next_flight_id
    flight_store[next_flight_id] = rec
    next_flight_id += 1
    return FlightOut(**rec)

@app.get("/flights", response_model=List[FlightOut])
def list_flights(
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    aircraft: List[str] = Query([]),
    category: Optional[str] = None,
    aircraft_class: Optional[str] = None,
    search: Optional[str] = None,
):
    def matches(f):
        if start_date and f["date"] < start_date:
            return False
        if end_date and f["date"] > end_date:
            return False
        if aircraft:
            if normalize_reg(f["aircraft_registration"]) not in [normalize_reg(a) for a in aircraft]:
                return False
        if category:
            ac = aircraft_store.get(normalize_reg(f["aircraft_registration"]))
            if not ac or ac["category"] != category:
                return False
        if aircraft_class:
            ac = aircraft_store.get(normalize_reg(f["aircraft_registration"]))
            if not ac or ac["aircraft_class"] != aircraft_class:
                return False
        if search:
            low = search.lower()
            if low not in f["route_departure"].lower() and low not in f["route_arrival"].lower():
                if not f.get("route_via") or low not in f["route_via"].lower():
                    if not f.get("notes") or low not in f["notes"].lower():
                        return False
        return True

    flights = [FlightOut(**f) for f in sorted(flight_store.values(), key=lambda x: x["date"], reverse=True) if matches(x)]
    return flights

@app.patch("/flights/{flight_id}", response_model=FlightOut)
def update_flight(flight_id: int, upd: FlightUpdate):
    if flight_id not in flight_store:
        raise HTTPException(404, "Flight not found")
    rec = flight_store[flight_id]
    if "aircraft_registration" in upd.dict(exclude_unset=True):
        new_reg = upd.aircraft_registration
        norm_new = normalize_reg(new_reg)
        ac_new = aircraft_store.get(norm_new)
        if not ac_new or not ac_new["active"]:
            raise HTTPException(400, "New aircraft must be active")
        # keep original if original aircraft is inactive (allowed)
        if not aircraft_store[normalize_reg(rec["aircraft_registration"])]["active"]:
            rec["aircraft_registration"] = new_reg
    for field in upd.dict(exclude_unset=True):
        if field in ["times", "counts", "ifr"]:
            rec[field] = upd.__dict__[field].dict()
        elif field not in ["aircraft_registration"]:
            rec[field] = upd.__dict__[field]
    flight_store[flight_id] = rec
    return FlightOut(**rec)

@app.delete("/flights/{flight_id}")
def delete_flight(flight_id: int):
    if flight_id not in flight_store:
        raise HTTPException(404, "Flight not found")
    del flight_store[flight_id]
    return {"detail": "Deleted"}

# ---------- Analytics ----------
@app.get("/analytics")
def analytics(
    preset: Optional[str] = None,
    start: Optional[date] = None,
    end: Optional[date] = None,
    group_by: Optional[str] = None,
):
    # determine range
    if preset:
        today = utc_today()
        if preset == "90":
            start = today - timedelta(days=89)
            end = today
        elif preset == "180":
            start = today - timedelta(days=179)
            end = today
        elif preset == "365":
            start = today - timedelta(days=364)
            end = today
        else:
            raise HTTPException(400, "Invalid preset")
    if not start or not end:
        raise HTTPException(400, "Date range required")
    # collect matching flights
    matching = [f for f in flight_store.values() if start <= f["date"] <= end]
    # aggregate
    totals = {
        "total_time": 0.0,
        "pic": 0.0,
        "sic": 0.0,
        "night": 0.0,
        "actual_instrument": 0.0,
        "simulated_instrument": 0.0,
        "cross_country": 0.0,
        "approaches": 0,
        "day_takeoffs": 0,
        "night_takeoffs": 0,
        "day_landings": 0,
        "night_landings": 0,
    }
    groups: Dict[str, Any] = {}
    for f in matching:
        t = f["times"]
        c = f["counts"]
        totals["total_time"] += t["total_time"]
        totals["pic"] += t["pic"]
        totals["sic"] += t["sic"]
        totals["night"] += t["night_time"]
        totals["actual_instrument"] += t["actual_instrument"]
        totals["simulated_instrument"] += t["simulated_instrument"]
        totals["cross_country"] += t["cross_country"]
        totals["approaches"] += c["instrument_approaches"]
        totals["day_takeoffs"] += c["day_takeoffs"]
        totals["night_takeoffs"] += c["night_takeoffs"]
        totals["day_landings"] += c["day_landings"]
        totals["night_landings"] += c["night_landings"]

        # grouping key
        if group_by:
            ac = aircraft_store.get(normalize_reg(f["aircraft_registration"]))
            if not ac:
                continue
            if group_by == "category":
                key = ac["category"]
            elif group_by == "class":
                key = ac["aircraft_class"]
            elif group_by == "make_model":
                key = ac["make_model"]
            else:
                raise HTTPException(400, "Invalid group_by")
            if key not in groups:
                groups[key] = dict(totals)  # copy current totals as start
            else:
                # add current flight values
                g = groups[key]
                g["total_time"] += t["total_time"]
                g["pic"] += t["pic"]
                g["sic"] += t["sic"]
                g["night"] += t["night_time"]
                g["actual_instrument"] += t["actual_instrument"]
                g["simulated_instrument"] += t["simulated_instrument"]
                g["cross_country"] += t["cross_country"]
                g["approaches"] += c["instrument_approaches"]
                g["day_takeoffs"] += c["day_takeoffs"]
                g["night_takeoffs"] += c["night_takeoffs"]
                g["day_landings"] += c["day_landings"]
                g["night_landings"] += c["night_landings"]
    return {"totals": totals, "groups": groups if group_by else None}

# ---------- Currency ----------
@app.get("/currency")
def currency():
    today = utc_today()
    # Day/Night currency (90‑day window)
    start_90 = today - timedelta(days=89)
    recent_flights = [f for f in flight_store.values() if start_90 <= f["date"] <= today]
    day_night = {}
    for f in recent_flights:
        ac = aircraft_store.get(normalize_reg(f["aircraft_registration"]))
        if not ac:
            continue
        key = (ac["category"], ac["aircraft_class"])
        if key not in day_night:
            day_night[key] = {"takeoffs": 0, "landings": 0}
        cnt = f["counts"]
        day_night[key]["takeoffs"] += cnt["day_takeoffs"] + cnt["night_takeoffs"]
        day_night[key]["landings"] += cnt["day_landings"] + cnt["night_landings"]
    day_night_report = {}
    for k, v in day_night.items():
        cur = v["takeoffs"] >= 3 and v["landings"] >= 3
        day_night_report[f"{k[0]} {k[1]}"] = {
            "current": cur,
            "takeoffs": f"{v['takeoffs']}/3",
            "landings": f"{v['landings']}/3",
        }

    # Instrument currency (6‑calendar‑month window)
    # compute start of month 6 months ago
    first_of_current_month = today.replace(day=1)
    month = first_of_current_month.month - 5
    year = first_of_current_month.year
    if month <= 0:
        month += 12
        year -= 1
    start_instr = date(year, month, 1)
    end_instr = date(today.year, today.month, 1) + timedelta(days=31)
    end_instr = end_instr.replace(day=1) - timedelta(days=1)  # last day of current month
    instr_flights = [f for f in flight_store.values() if start_instr <= f["date"] <= end_instr]
    instr_report = {}
    for f in instr_flights:
        ac = aircraft_store.get(normalize_reg(f["aircraft_registration"]))
        if not ac:
            continue
        key = (ac["category"],)
        if key not in instr_report:
            instr_report[key] = {"approaches": 0, "holds": False, "intercepts": False}
        cnt = f["counts"]
        instr_report[key]["approaches"] += cnt["instrument_approaches"]
        iff = f["ifr"]
        if iff["holds_performed"]:
            instr_report[key]["holds"] = True
        if iff["intercept_track_performed"]:
            instr_report[key]["intercepts"] = True
    # format
    formatted_instr = {}
    for k, v in instr_report.items():
        cur = v["approaches"] >= 6 and v["holds"] and v["intercepts"]
        formatted_instr[k[0]] = {"current": cur, "approaches": f"{v['approaches']}/6"}
    return {"day_night": day_night_report, "instrument": formatted_instr}

# ---------- Export ----------
@app.get("/export")
def export_csv(
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    aircraft: List[str] = Query([]),
):
    # filter same as list_flights
    def matches(f):
        if start_date and f["date"] < start_date:
            return False
        if end_date and f["date"] > end_date:
            return False
        if aircraft:
            if normalize_reg(f["aircraft_registration"]) not in [normalize_reg(a) for a in aircraft]:
                return False
        return True

    rows = [f for f in flight_store.values() if matches(f)]
    output = io.StringIO()
    writer = csv.writer(output)
    header = [
        "Date","Aircraft","Departure","Arrival","Via","Notes",
        "Total Time","Day Time","Night Time","PIC","SIC","Dual Given","Dual Received",
        "Cross-country","Actual Instrument","Simulated Instrument",
        "Day Takeoffs","Day Landings","Night Takeoffs","Night Landings","Instrument Approaches",
        "Holds performed","Intercept/Track performed"
    ]
    # add aircraft attributes
    header.extend(["Registration","Make/Model","Category","Class","Type Designator"])
    writer.writerow(header)
    for f in rows:
        ac = aircraft_store.get(normalize_reg(f["aircraft_registration"]), {})
        row = [
            f["date"].isoformat(),
            f["aircraft_registration"],
            f["route_departure"],
            f["route_arrival"],
            f.get("route_via",""),
            f.get("notes",""),
            f["times"]["total_time"],
            f["times"]["day_time"],
            f["times"]["night_time"],
            f["times"]["pic"],
            f["times"]["sic"],
            f["times"]["dual_given"],
            f["times"]["dual_received"],
            f["times"]["cross_country"],
            f["times"]["actual_instrument"],
            f["times"]["simulated_instrument"],
            f["counts"]["day_takeoffs"],
            f["counts"]["day_landings"],
            f["counts"]["night_takeoffs"],
            f["counts"]["night_landings"],
            f["counts"]["instrument_approaches"],
            f["ifr"]["holds_performed"],
            f["ifr"]["intercept_track_performed"],
        ]
        row.extend([
            ac.get("registration",""),
            ac.get("make_model",""),
            ac.get("category",""),
            ac.get("aircraft_class",""),
            ac.get("type_designator",""),
        ])
        writer.writerow(row)
    return {"csv": output.getvalue()}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
