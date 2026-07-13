from flask import Flask, request, jsonify
from datetime import datetime, date, time, timedelta
import threading
import uuid

app = Flask(__name__)

# Shop configuration
BARBERS = ["Alex", "Lucy", "George"]
OPEN_HOUR = 9
CLOSE_HOUR = 18
SLOT_MINUTES = 30

# In-memory storage
# appointments: dict[appointment_id] = { id, date (YYYY-MM-DD), start_time (HH:MM), barber, customer_name, notes }
appointments = {}
# Index for quick slot lookup: (date, barber, start_time) -> appointment_id
slot_index = {}
lock = threading.Lock()


def generate_slots():
    """Return list of (start_time_str, end_time_str) tuples for the day."""
    slots = []
    current = datetime.combine(date.today(), time(OPEN_HOUR, 0))
    end = datetime.combine(date.today(), time(CLOSE_HOUR, 0))
    while current < end:
        nxt = current + timedelta(minutes=SLOT_MINUTES)
        slots.append((current.strftime("%H:%M"), nxt.strftime("%H:%M")))
        current = nxt
    return slots


def valid_slot_time(t_str):
    for s, _ in generate_slots():
        if s == t_str:
            return True
    return False


def parse_date(date_str):
    if not date_str:
        return date.today().isoformat()
    try:
        d = datetime.strptime(date_str, "%Y-%m-%d").date()
        return d.isoformat()
    except ValueError:
        return None


def appointment_to_dict(appt):
    start = appt["start_time"]
    start_dt = datetime.strptime(start, "%H:%M")
    end_dt = start_dt + timedelta(minutes=SLOT_MINUTES)
    return {
        "id": appt["id"],
        "date": appt["date"],
        "start_time": start,
        "end_time": end_dt.strftime("%H:%M"),
        "barber": appt["barber"],
        "customer_name": appt["customer_name"],
        "notes": appt.get("notes", ""),
    }


@app.route("/schedule", methods=["GET"])
def get_schedule():
    date_str = request.args.get("date")
    d = parse_date(date_str)
    if d is None:
        return jsonify({"error": "Invalid date format. Use YYYY-MM-DD."}), 400

    slots = generate_slots()
    schedule = {"date": d, "barbers": {}}
    with lock:
        for barber in BARBERS:
            barber_slots = []
            for start, end in slots:
                key = (d, barber, start)
                appt_id = slot_index.get(key)
                if appt_id:
                    appt = appointments[appt_id]
                    barber_slots.append({
                        "start_time": start,
                        "end_time": end,
                        "available": False,
                        "appointment_id": appt_id,
                        "customer_name": appt["customer_name"],
                    })
                else:
                    barber_slots.append({
                        "start_time": start,
                        "end_time": end,
                        "available": True,
                        "appointment_id": None,
                        "customer_name": None,
                    })
            schedule["barbers"][barber] = barber_slots
    return jsonify(schedule)


@app.route("/appointments", methods=["POST"])
def create_appointment():
    data = request.get_json(silent=True) or {}
    date_str = data.get("date")
    start_time = data.get("start_time")
    barber = data.get("barber")
    customer_name = data.get("customer_name")
    notes = data.get("notes", "")

    if not date_str:
        return jsonify({"error": "date is required"}), 400
    d = parse_date(date_str)
    if d is None:
        return jsonify({"error": "Invalid date format. Use YYYY-MM-DD."}), 400
    if not start_time or not valid_slot_time(start_time):
        return jsonify({"error": "Invalid or missing start_time. Must be a valid slot start (HH:MM)."}), 400
    if barber not in BARBERS:
        return jsonify({"error": f"Invalid barber. Must be one of {BARBERS}."}), 400
    if customer_name is None or not str(customer_name).strip():
        return jsonify({"error": "customer_name is required and cannot be empty"}), 400

    with lock:
        key = (d, barber, start_time)
        if key in slot_index:
            return jsonify({"error": "Slot is no longer available"}), 409
        appt_id = str(uuid.uuid4())
        appt = {
            "id": appt_id,
            "date": d,
            "start_time": start_time,
            "barber": barber,
            "customer_name": str(customer_name).strip(),
            "notes": notes or "",
        }
        appointments[appt_id] = appt
        slot_index[key] = appt_id

    return jsonify(appointment_to_dict(appt)), 201


@app.route("/appointments/<appt_id>", methods=["GET"])
def get_appointment(appt_id):
    with lock:
        appt = appointments.get(appt_id)
        if not appt:
            return jsonify({"error": "Appointment not found"}), 404
        return jsonify(appointment_to_dict(appt))


@app.route("/appointments/<appt_id>", methods=["PATCH", "PUT"])
def update_appointment(appt_id):
    data = request.get_json(silent=True) or {}
    with lock:
        appt = appointments.get(appt_id)
        if not appt:
            return jsonify({"error": "Appointment not found"}), 404

        # Only customer_name and notes editable
        immutable = {"date", "start_time", "barber", "end_time"}
        for field in immutable:
            if field in data:
                return jsonify({"error": f"Field '{field}' cannot be changed. Cancel and re-create to reschedule."}), 400

        if "customer_name" in data:
            cn = data["customer_name"]
            if cn is None or not str(cn).strip():
                return jsonify({"error": "customer_name cannot be empty"}), 400
            appt["customer_name"] = str(cn).strip()
        if "notes" in data:
            appt["notes"] = data["notes"] or ""

        return jsonify(appointment_to_dict(appt))


@app.route("/appointments/<appt_id>", methods=["DELETE"])
def cancel_appointment(appt_id):
    with lock:
        appt = appointments.pop(appt_id, None)
        if not appt:
            return jsonify({"error": "Appointment not found"}), 404
        key = (appt["date"], appt["barber"], appt["start_time"])
        slot_index.pop(key, None)
    return jsonify({"status": "cancelled", "id": appt_id})


@app.route("/config", methods=["GET"])
def config():
    return jsonify({
        "timezone": "UTC",
        "open": f"{OPEN_HOUR:02d}:00",
        "close": f"{CLOSE_HOUR:02d}:00",
        "slot_minutes": SLOT_MINUTES,
        "barbers": BARBERS,
    })


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
