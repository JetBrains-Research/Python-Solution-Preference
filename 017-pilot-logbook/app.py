"""Pilot's Logbook MVP - Flask HTTP API."""
from __future__ import annotations

import csv
import io
import re
import uuid
from dataclasses import dataclass, field, asdict
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from flask import Flask, jsonify, request, Response


# ---------------------------------------------------------------------------
# Domain constants
# ---------------------------------------------------------------------------

CATEGORIES_CLASSES = {
    "Airplane": {"SEL", "SES", "MEL", "MES"},
    "Rotorcraft": {"Helicopter", "Gyroplane"},
    "Glider": {"Glider"},
}

TIME_FIELDS = [
    "total_time",
    "day_time",
    "night_time",
    "pic",
    "sic",
    "dual_given",
    "dual_received",
    "cross_country",
    "actual_instrument",
    "simulated_instrument",
]

COUNT_FIELDS = [
    "day_takeoffs",
    "day_landings",
    "night_takeoffs",
    "night_landings",
    "instrument_approaches",
]

BOOL_FIELDS = ["holds_performed", "intercept_track_performed"]

AIRCRAFT_FLAGS = [
    "type_rating_required",
    "complex",
    "high_performance",
    "tailwheel",
    "turbine",
]


# ---------------------------------------------------------------------------
# In-memory store
# ---------------------------------------------------------------------------

aircraft_store: Dict[str, Dict[str, Any]] = {}
flight_store: Dict[str, Dict[str, Any]] = {}


def canonical_tail(tail: str) -> str:
    return re.sub(r"[\s\-]", "", tail).upper()


def today_utc() -> date:
    return datetime.now(timezone.utc).date()


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------

class ValidationError(Exception):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def require(cond: bool, message: str):
    if not cond:
        raise ValidationError(message)


def parse_date(s: str) -> date:
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except Exception:
        raise ValidationError(f"Invalid date '{s}'; expected YYYY-MM-DD")


def is_tenth(x: float) -> bool:
    # Check multiple of 0.1
    return abs(round(x * 10) - x * 10) < 1e-6


def as_float(v: Any, field_name: str) -> float:
    if v is None:
        return 0.0
    try:
        f = float(v)
    except Exception:
        raise ValidationError(f"{field_name} must be a number")
    return f


def as_int(v: Any, field_name: str) -> int:
    if v is None:
        return 0
    if isinstance(v, bool):
        raise ValidationError(f"{field_name} must be an integer")
    try:
        i = int(v)
    except Exception:
        raise ValidationError(f"{field_name} must be an integer")
    if float(v) != i:
        raise ValidationError(f"{field_name} must be an integer")
    return i


def as_bool(v: Any, field_name: str) -> bool:
    if v is None:
        return False
    if isinstance(v, bool):
        return v
    raise ValidationError(f"{field_name} must be a boolean")


# ---------------------------------------------------------------------------
# Aircraft handling
# ---------------------------------------------------------------------------

def validate_aircraft_payload(data: Dict[str, Any], existing_id: Optional[str] = None) -> Dict[str, Any]:
    require(isinstance(data, dict), "Payload must be a JSON object")
    tail = data.get("registration")
    make_model = data.get("make_model")
    category = data.get("category")
    klass = data.get("class")
    type_designator = data.get("type_designator") or None

    require(isinstance(tail, str) and tail.strip(), "registration is required")
    require(isinstance(make_model, str) and make_model.strip(), "make_model is required")
    require(isinstance(category, str) and category in CATEGORIES_CLASSES, f"category must be one of {sorted(CATEGORIES_CLASSES)}")
    require(isinstance(klass, str) and klass in CATEGORIES_CLASSES[category], f"class must be one of {sorted(CATEGORIES_CLASSES[category])} for category {category}")

    flags = {}
    for f in AIRCRAFT_FLAGS:
        flags[f] = as_bool(data.get(f, False), f)

    if flags["type_rating_required"]:
        require(isinstance(type_designator, str) and type_designator.strip(),
                "type_designator is required when type_rating_required is true")

    canon = canonical_tail(tail)
    for aid, a in aircraft_store.items():
        if aid == existing_id:
            continue
        if canonical_tail(a["registration"]) == canon:
            raise ValidationError(f"Registration/Tail '{tail}' conflicts with existing aircraft", status=409)

    return {
        "registration": tail,
        "make_model": make_model,
        "category": category,
        "class": klass,
        "type_designator": type_designator.strip() if isinstance(type_designator, str) else None,
        **flags,
    }


# ---------------------------------------------------------------------------
# Flight handling
# ---------------------------------------------------------------------------

def validate_flight_payload(data: Dict[str, Any], existing: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    require(isinstance(data, dict), "Payload must be a JSON object")

    date_str = data.get("date")
    require(isinstance(date_str, str), "date is required (YYYY-MM-DD)")
    flight_date = parse_date(date_str)
    require(flight_date <= today_utc(), "date cannot be in the future (Zulu)")

    aircraft_id = data.get("aircraft_id")
    if existing is not None and (aircraft_id is None or aircraft_id == existing["aircraft_id"]):
        # unchanged aircraft; allow even if inactive
        aircraft_id = existing["aircraft_id"]
        require(aircraft_id in aircraft_store, "aircraft_id not found")
    else:
        require(isinstance(aircraft_id, str) and aircraft_id in aircraft_store,
                "aircraft_id is required and must reference an existing aircraft")
        ac = aircraft_store[aircraft_id]
        require(ac.get("active", True), "Selected aircraft is Inactive; cannot be used for new/changed flight aircraft")

    departure = data.get("departure")
    arrival = data.get("arrival")
    via = data.get("via") or ""
    notes = data.get("notes") or ""
    require(isinstance(departure, str) and departure.strip(), "departure is required")
    require(isinstance(arrival, str) and arrival.strip(), "arrival is required")
    require(isinstance(via, str), "via must be string")
    require(isinstance(notes, str), "notes must be string")

    times: Dict[str, float] = {}
    for f in TIME_FIELDS:
        v = as_float(data.get(f, 0), f)
        require(v >= 0, f"{f} must be >= 0")
        require(is_tenth(v), f"{f} must be a multiple of 0.1")
        times[f] = round(v, 1)

    require(times["total_time"] > 0, "total_time must be > 0")
    require(round(times["day_time"] + times["night_time"], 1) == times["total_time"],
            "day_time + night_time must equal total_time exactly")
    require(round(times["actual_instrument"] + times["simulated_instrument"], 1) <= times["total_time"],
            "actual_instrument + simulated_instrument must be <= total_time")
    require(not (times["pic"] > 0 and times["sic"] > 0), "PIC and SIC cannot both be > 0")
    require(round(times["pic"] + times["sic"], 1) <= times["total_time"], "PIC + SIC must be <= total_time")
    require(not (times["dual_given"] > 0 and times["dual_received"] > 0),
            "dual_given and dual_received cannot both be > 0")
    require(times["dual_given"] <= times["total_time"], "dual_given must be <= total_time")
    require(times["dual_received"] <= times["total_time"], "dual_received must be <= total_time")
    require(times["cross_country"] <= times["total_time"], "cross_country must be <= total_time")

    counts: Dict[str, int] = {}
    for f in COUNT_FIELDS:
        v = as_int(data.get(f, 0), f)
        require(v >= 0, f"{f} must be >= 0")
        counts[f] = v

    bools: Dict[str, bool] = {}
    for f in BOOL_FIELDS:
        bools[f] = as_bool(data.get(f, False), f)

    return {
        "date": flight_date.isoformat(),
        "aircraft_id": aircraft_id,
        "departure": departure,
        "arrival": arrival,
        "via": via,
        "notes": notes,
        **times,
        **counts,
        **bools,
    }


# ---------------------------------------------------------------------------
# Filtering
# ---------------------------------------------------------------------------

def apply_filters(flights: List[Dict[str, Any]], params: Dict[str, Any]) -> List[Dict[str, Any]]:
    date_from = params.get("date_from")
    date_to = params.get("date_to")
    aircraft_ids = params.get("aircraft_ids")
    categories = params.get("categories")
    classes = params.get("classes")
    text = params.get("text")

    if isinstance(aircraft_ids, str):
        aircraft_ids = [a for a in aircraft_ids.split(",") if a]
    if isinstance(categories, str):
        categories = [c for c in categories.split(",") if c]
    if isinstance(classes, str):
        classes = [c for c in classes.split(",") if c]

    df = parse_date(date_from) if date_from else None
    dt = parse_date(date_to) if date_to else None
    text_l = text.lower() if isinstance(text, str) and text else None

    def match(fl: Dict[str, Any]) -> bool:
        fd = parse_date(fl["date"])
        if df and fd < df:
            return False
        if dt and fd > dt:
            return False
        if aircraft_ids and fl["aircraft_id"] not in aircraft_ids:
            return False
        ac = aircraft_store.get(fl["aircraft_id"], {})
        if categories and ac.get("category") not in categories:
            return False
        if classes and ac.get("class") not in classes:
            return False
        if text_l:
            hay = " ".join([fl.get("departure", ""), fl.get("arrival", ""),
                            fl.get("via", ""), fl.get("notes", "")]).lower()
            if text_l not in hay:
                return False
        return True

    return [fl for fl in flights if match(fl)]


def extract_filter_params(source: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "date_from": source.get("date_from"),
        "date_to": source.get("date_to"),
        "aircraft_ids": source.get("aircraft_ids"),
        "categories": source.get("categories"),
        "classes": source.get("classes"),
        "text": source.get("text"),
    }


# ---------------------------------------------------------------------------
# Flask app
# ---------------------------------------------------------------------------

app = Flask(__name__)


@app.errorhandler(ValidationError)
def handle_validation(err: ValidationError):
    return jsonify({"error": str(err)}), err.status


@app.errorhandler(404)
def handle_404(err):
    return jsonify({"error": "not found"}), 404


# ---------------- Aircraft endpoints ----------------

@app.post("/aircraft")
def create_aircraft():
    data = request.get_json(force=True, silent=True) or {}
    payload = validate_aircraft_payload(data)
    aid = str(uuid.uuid4())
    payload["id"] = aid
    payload["active"] = True
    aircraft_store[aid] = payload
    return jsonify(payload), 201


@app.get("/aircraft")
def list_aircraft():
    include_inactive = request.args.get("include_inactive", "true").lower() != "false"
    items = list(aircraft_store.values())
    if not include_inactive:
        items = [a for a in items if a.get("active", True)]
    items.sort(key=lambda a: canonical_tail(a["registration"]))
    return jsonify(items)


@app.get("/aircraft/<aid>")
def get_aircraft(aid: str):
    if aid not in aircraft_store:
        return jsonify({"error": "aircraft not found"}), 404
    return jsonify(aircraft_store[aid])


@app.put("/aircraft/<aid>")
def update_aircraft(aid: str):
    if aid not in aircraft_store:
        return jsonify({"error": "aircraft not found"}), 404
    data = request.get_json(force=True, silent=True) or {}
    payload = validate_aircraft_payload(data, existing_id=aid)
    payload["id"] = aid
    payload["active"] = aircraft_store[aid].get("active", True)
    aircraft_store[aid] = payload
    return jsonify(payload)


@app.post("/aircraft/<aid>/archive")
def archive_aircraft(aid: str):
    if aid not in aircraft_store:
        return jsonify({"error": "aircraft not found"}), 404
    aircraft_store[aid]["active"] = False
    return jsonify(aircraft_store[aid])


@app.post("/aircraft/<aid>/unarchive")
def unarchive_aircraft(aid: str):
    if aid not in aircraft_store:
        return jsonify({"error": "aircraft not found"}), 404
    aircraft_store[aid]["active"] = True
    return jsonify(aircraft_store[aid])


# ---------------- Flight endpoints ----------------

@app.post("/flights")
def create_flight():
    data = request.get_json(force=True, silent=True) or {}
    payload = validate_flight_payload(data)
    fid = str(uuid.uuid4())
    payload["id"] = fid
    flight_store[fid] = payload
    return jsonify(payload), 201


@app.get("/flights")
def list_flights():
    params = extract_filter_params(request.args)
    flights = list(flight_store.values())
    flights = apply_filters(flights, params)
    flights.sort(key=lambda f: (f["date"], f["id"]), reverse=True)
    # attach aircraft info
    result = []
    for f in flights:
        item = dict(f)
        item["aircraft"] = aircraft_store.get(f["aircraft_id"])
        result.append(item)
    return jsonify(result)


@app.get("/flights/<fid>")
def get_flight(fid: str):
    if fid not in flight_store:
        return jsonify({"error": "flight not found"}), 404
    f = dict(flight_store[fid])
    f["aircraft"] = aircraft_store.get(f["aircraft_id"])
    return jsonify(f)


@app.put("/flights/<fid>")
def update_flight(fid: str):
    if fid not in flight_store:
        return jsonify({"error": "flight not found"}), 404
    data = request.get_json(force=True, silent=True) or {}
    existing = flight_store[fid]
    # If aircraft_id not present in payload, keep existing (allows editing inactive-aircraft flights)
    if "aircraft_id" not in data:
        data["aircraft_id"] = existing["aircraft_id"]
    payload = validate_flight_payload(data, existing=existing)
    payload["id"] = fid
    flight_store[fid] = payload
    return jsonify(payload)


@app.delete("/flights/<fid>")
def delete_flight(fid: str):
    if fid not in flight_store:
        return jsonify({"error": "flight not found"}), 404
    del flight_store[fid]
    return jsonify({"deleted": fid})


# ---------------- Analytics ----------------

def resolve_preset(preset: str) -> Tuple[date, date]:
    today = today_utc()
    if preset == "last_90_days":
        return today - timedelta(days=89), today
    if preset == "last_6_months":
        # 6 calendar months ending current month
        y, m = today.year, today.month
        # Start month = month - 5
        start_m = m - 5
        start_y = y
        while start_m <= 0:
            start_m += 12
            start_y -= 1
        # last day of current month
        if m == 12:
            end = date(y, 12, 31)
        else:
            end = date(y, m + 1, 1) - timedelta(days=1)
        return date(start_y, start_m, 1), end
    if preset == "last_12_months":
        start = today - timedelta(days=364)
        return start, today
    raise ValidationError(f"Unknown preset '{preset}'")


def collect_metrics(flights: List[Dict[str, Any]]) -> Dict[str, Any]:
    metrics = {f: 0.0 for f in [
        "total_time", "pic", "sic", "night_time", "actual_instrument",
        "simulated_instrument", "cross_country",
    ]}
    metrics["instrument_approaches"] = 0
    metrics["day_takeoffs"] = 0
    metrics["day_landings"] = 0
    metrics["night_takeoffs"] = 0
    metrics["night_landings"] = 0
    metrics["flights"] = 0
    for f in flights:
        metrics["total_time"] += f["total_time"]
        metrics["pic"] += f["pic"]
        metrics["sic"] += f["sic"]
        metrics["night_time"] += f["night_time"]
        metrics["actual_instrument"] += f["actual_instrument"]
        metrics["simulated_instrument"] += f["simulated_instrument"]
        metrics["cross_country"] += f["cross_country"]
        metrics["instrument_approaches"] += f["instrument_approaches"]
        metrics["day_takeoffs"] += f["day_takeoffs"]
        metrics["day_landings"] += f["day_landings"]
        metrics["night_takeoffs"] += f["night_takeoffs"]
        metrics["night_landings"] += f["night_landings"]
        metrics["flights"] += 1
    for k in ["total_time", "pic", "sic", "night_time", "actual_instrument",
              "simulated_instrument", "cross_country"]:
        metrics[k] = round(metrics[k], 1)
    return metrics


@app.get("/analytics/totals")
def analytics_totals():
    params = extract_filter_params(request.args)
    preset = request.args.get("preset")
    if preset:
        df, dt = resolve_preset(preset)
        params["date_from"] = df.isoformat()
        params["date_to"] = dt.isoformat()
    group_by = request.args.get("group_by", "overall")
    flights = apply_filters(list(flight_store.values()), params)

    if group_by == "overall":
        return jsonify({"group_by": "overall", "totals": collect_metrics(flights)})

    groups: Dict[str, List[Dict[str, Any]]] = {}
    for fl in flights:
        ac = aircraft_store.get(fl["aircraft_id"], {})
        if group_by == "category_class":
            key = f"{ac.get('category','?')}/{ac.get('class','?')}"
        elif group_by == "make_model":
            key = ac.get("make_model", "?")
        else:
            raise ValidationError("group_by must be one of: overall, category_class, make_model")
        groups.setdefault(key, []).append(fl)

    return jsonify({
        "group_by": group_by,
        "groups": {k: collect_metrics(v) for k, v in groups.items()},
    })


# ---------------- Currency ----------------

def day_night_currency() -> List[Dict[str, Any]]:
    today = today_utc()
    window_start = today - timedelta(days=89)

    # find category/class combos with at least one flight ever
    combos: Dict[Tuple[str, str, Optional[str]], List[Dict[str, Any]]] = {}
    for fl in flight_store.values():
        ac = aircraft_store.get(fl["aircraft_id"])
        if not ac:
            continue
        type_des = ac.get("type_designator") if ac.get("type_rating_required") else None
        key = (ac["category"], ac["class"], type_des)
        combos.setdefault(key, []).append(fl)

    results = []
    for (cat, klass, tdes), all_fls in combos.items():
        recent = [f for f in all_fls if window_start <= parse_date(f["date"]) <= today]
        day_to = sum(f["day_takeoffs"] for f in recent)
        day_ldg = sum(f["day_landings"] for f in recent)
        night_to = sum(f["night_takeoffs"] for f in recent)
        night_ldg = sum(f["night_landings"] for f in recent)
        entry = {
            "category": cat,
            "class": klass,
            "type_designator": tdes,
            "window_start": window_start.isoformat(),
            "window_end": today.isoformat(),
            "day": {
                "takeoffs": day_to,
                "landings": day_ldg,
                "current": day_to >= 3 and day_ldg >= 3,
                "report": f"Day TO {day_to}/3; Day LDG {day_ldg}/3",
            },
            "night": {
                "takeoffs": night_to,
                "landings": night_ldg,
                "current": night_to >= 3 and night_ldg >= 3,
                "report": f"Night TO {night_to}/3; Night LDG {night_ldg}/3",
            },
        }
        results.append(entry)
    return results


def instrument_currency() -> List[Dict[str, Any]]:
    today = today_utc()
    # window: 6 calendar months ending current month
    y, m = today.year, today.month
    start_m = m - 5
    start_y = y
    while start_m <= 0:
        start_m += 12
        start_y -= 1
    start = date(start_y, start_m, 1)
    if m == 12:
        end = date(y, 12, 31)
    else:
        end = date(y, m + 1, 1) - timedelta(days=1)

    combos: Dict[str, List[Dict[str, Any]]] = {}
    for fl in flight_store.values():
        ac = aircraft_store.get(fl["aircraft_id"])
        if not ac:
            continue
        combos.setdefault(ac["category"], []).append(fl)

    results = []
    for cat, all_fls in combos.items():
        recent = [f for f in all_fls if start <= parse_date(f["date"]) <= end]
        approaches = sum(f["instrument_approaches"] for f in recent)
        holds = any(f["holds_performed"] for f in recent)
        intercept = any(f["intercept_track_performed"] for f in recent)
        results.append({
            "category": cat,
            "window_start": start.isoformat(),
            "window_end": end.isoformat(),
            "approaches": approaches,
            "holds_performed": holds,
            "intercept_track_performed": intercept,
            "current": approaches >= 6 and holds and intercept,
        })
    return results


@app.get("/analytics/currency")
def analytics_currency():
    return jsonify({
        "day_night": day_night_currency(),
        "instrument": instrument_currency(),
    })


# ---------------- Export ----------------

CSV_FIELDS = [
    "date", "aircraft_registration", "aircraft_make_model", "aircraft_category",
    "aircraft_class", "aircraft_type_designator",
    "aircraft_type_rating_required", "aircraft_complex", "aircraft_high_performance",
    "aircraft_tailwheel", "aircraft_turbine",
    "departure", "arrival", "via", "notes",
] + TIME_FIELDS + COUNT_FIELDS + BOOL_FIELDS


@app.get("/export.csv")
def export_csv():
    params = extract_filter_params(request.args)
    flights = list(flight_store.values())
    if any(v for v in params.values()):
        flights = apply_filters(flights, params)
    flights.sort(key=lambda f: (f["date"], f["id"]), reverse=True)

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(CSV_FIELDS)
    for fl in flights:
        ac = aircraft_store.get(fl["aircraft_id"], {})
        row = [
            fl["date"],
            ac.get("registration", ""),
            ac.get("make_model", ""),
            ac.get("category", ""),
            ac.get("class", ""),
            ac.get("type_designator") or "",
            "true" if ac.get("type_rating_required") else "false",
            "true" if ac.get("complex") else "false",
            "true" if ac.get("high_performance") else "false",
            "true" if ac.get("tailwheel") else "false",
            "true" if ac.get("turbine") else "false",
            fl.get("departure", ""),
            fl.get("arrival", ""),
            fl.get("via", ""),
            fl.get("notes", ""),
        ]
        for f in TIME_FIELDS:
            row.append(f"{fl[f]:.1f}")
        for f in COUNT_FIELDS:
            row.append(str(fl[f]))
        for f in BOOL_FIELDS:
            row.append("true" if fl[f] else "false")
        writer.writerow(row)

    data = buf.getvalue().encode("utf-8")
    return Response(data, mimetype="text/csv; charset=utf-8",
                    headers={"Content-Disposition": "attachment; filename=logbook.csv"})


@app.get("/health")
def health():
    return jsonify({"ok": True})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(__import__("os").environ.get("PORT", "5000")), debug=False)
