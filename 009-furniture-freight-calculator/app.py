"""Furniture Delivery Pricing Calculator (MVP) - HTTP API"""
from flask import Flask, request, jsonify
from copy import deepcopy
from datetime import datetime
import uuid

app = Flask(__name__)


def new_store():
    return {
        "settings": {
            "ruralRatePerKm": 0.0,
            "assemblyRatePerInterval": 0.0,
            "rubbishFlatRate": 0.0,
        },
        "locations": {},   # id -> location
        "rateCards": {},   # id -> rate card
        "catalog": {},     # id -> catalog item
        "quotes": {},      # id -> quote snapshot
    }


store = new_store()


def _err(msg, code=400):
    return jsonify({"error": msg}), code


def _fmt_money(x):
    return round(float(x) + 1e-9, 2)


def _fmt_vol(x):
    return round(float(x) + 1e-9, 2)


# ---------------- Settings ----------------
@app.get("/settings")
def get_settings():
    return jsonify(store["settings"])


@app.put("/settings")
def put_settings():
    data = request.get_json(force=True, silent=True) or {}
    s = store["settings"]
    for k in ("ruralRatePerKm", "assemblyRatePerInterval", "rubbishFlatRate"):
        if k in data:
            try:
                val = float(data[k])
            except (TypeError, ValueError):
                return _err(f"Invalid value for {k}")
            if val < 0:
                return _err(f"{k} must be >= 0")
            s[k] = val
    return jsonify(s)


# ---------------- Locations ----------------
VALID_LOC_TYPES = {"store", "warehouse", "supplier"}


def _validate_location(data, partial=False):
    fields = ["type", "name", "address", "city", "suburb"]
    if not partial:
        for f in fields:
            if f not in data:
                return f"Missing field: {f}"
    if "type" in data and data["type"] not in VALID_LOC_TYPES:
        return "Invalid location type"
    for f in ["name", "address", "city"]:
        if f in data and (not isinstance(data[f], str) or not data[f].strip()):
            return f"Invalid {f}"
    if "suburb" in data and not isinstance(data["suburb"], str):
        return "Invalid suburb"
    return None


@app.get("/locations")
def list_locations():
    return jsonify(list(store["locations"].values()))


@app.post("/locations")
def create_location():
    data = request.get_json(force=True, silent=True) or {}
    err = _validate_location(data)
    if err:
        return _err(err)
    loc_id = str(uuid.uuid4())
    loc = {
        "id": loc_id,
        "type": data["type"],
        "name": data["name"].strip(),
        "address": data["address"].strip(),
        "city": data["city"].strip(),
        "suburb": data.get("suburb", "").strip(),
    }
    store["locations"][loc_id] = loc
    return jsonify(loc), 201


@app.get("/locations/<lid>")
def get_location(lid):
    if lid not in store["locations"]:
        return _err("Not found", 404)
    return jsonify(store["locations"][lid])


@app.put("/locations/<lid>")
def update_location(lid):
    if lid not in store["locations"]:
        return _err("Not found", 404)
    data = request.get_json(force=True, silent=True) or {}
    err = _validate_location(data, partial=True)
    if err:
        return _err(err)
    loc = store["locations"][lid]
    for f in ("type", "name", "address", "city", "suburb"):
        if f in data:
            loc[f] = data[f].strip() if isinstance(data[f], str) else data[f]
    return jsonify(loc)


@app.delete("/locations/<lid>")
def delete_location(lid):
    if lid not in store["locations"]:
        return _err("Not found", 404)
    del store["locations"][lid]
    return "", 204


# ---------------- Rate Cards ----------------
VALID_SVC = {"B2B", "B2C"}


def _validate_rate(data, partial=False):
    fields = ["serviceType", "fromCity", "toCity", "toSuburb", "ratePerM3"]
    if not partial:
        for f in fields:
            if f not in data:
                return f"Missing field: {f}"
    if "serviceType" in data and data["serviceType"] not in VALID_SVC:
        return "Invalid serviceType"
    for f in ("fromCity", "toCity"):
        if f in data and (not isinstance(data[f], str) or not data[f].strip()):
            return f"Invalid {f}"
    if "toSuburb" in data and not isinstance(data["toSuburb"], str):
        return "Invalid toSuburb"
    if "ratePerM3" in data:
        try:
            v = float(data["ratePerM3"])
        except (TypeError, ValueError):
            return "Invalid ratePerM3"
        if v < 0:
            return "ratePerM3 must be >= 0"
    return None


@app.get("/rate-cards")
def list_rate_cards():
    return jsonify(list(store["rateCards"].values()))


@app.post("/rate-cards")
def create_rate_card():
    data = request.get_json(force=True, silent=True) or {}
    err = _validate_rate(data)
    if err:
        return _err(err)
    rid = str(uuid.uuid4())
    rc = {
        "id": rid,
        "serviceType": data["serviceType"],
        "fromCity": data["fromCity"].strip(),
        "toCity": data["toCity"].strip(),
        "toSuburb": data["toSuburb"].strip(),
        "ratePerM3": float(data["ratePerM3"]),
    }
    store["rateCards"][rid] = rc
    return jsonify(rc), 201


@app.get("/rate-cards/<rid>")
def get_rate_card(rid):
    if rid not in store["rateCards"]:
        return _err("Not found", 404)
    return jsonify(store["rateCards"][rid])


@app.put("/rate-cards/<rid>")
def update_rate_card(rid):
    if rid not in store["rateCards"]:
        return _err("Not found", 404)
    data = request.get_json(force=True, silent=True) or {}
    err = _validate_rate(data, partial=True)
    if err:
        return _err(err)
    rc = store["rateCards"][rid]
    for f in ("serviceType", "fromCity", "toCity", "toSuburb"):
        if f in data:
            rc[f] = data[f].strip() if isinstance(data[f], str) else data[f]
    if "ratePerM3" in data:
        rc["ratePerM3"] = float(data["ratePerM3"])
    return jsonify(rc)


@app.delete("/rate-cards/<rid>")
def delete_rate_card(rid):
    if rid not in store["rateCards"]:
        return _err("Not found", 404)
    del store["rateCards"][rid]
    return "", 204


# ---------------- Catalog ----------------
def _validate_catalog(data, partial=False):
    fields = ["sku", "name", "cubicMetres", "category"]
    if not partial:
        for f in fields:
            if f not in data:
                return f"Missing field: {f}"
    for f in ("sku", "name", "category"):
        if f in data and (not isinstance(data[f], str) or not data[f].strip()):
            return f"Invalid {f}"
    if "cubicMetres" in data:
        try:
            v = float(data["cubicMetres"])
        except (TypeError, ValueError):
            return "Invalid cubicMetres"
        if v <= 0:
            return "cubicMetres must be > 0"
    return None


@app.get("/catalog")
def list_catalog():
    return jsonify(list(store["catalog"].values()))


@app.post("/catalog")
def create_catalog_item():
    data = request.get_json(force=True, silent=True) or {}
    err = _validate_catalog(data)
    if err:
        return _err(err)
    cid = str(uuid.uuid4())
    item = {
        "id": cid,
        "sku": data["sku"].strip(),
        "name": data["name"].strip(),
        "cubicMetres": float(data["cubicMetres"]),
        "category": data["category"].strip(),
    }
    store["catalog"][cid] = item
    return jsonify(item), 201


@app.get("/catalog/<cid>")
def get_catalog_item(cid):
    if cid not in store["catalog"]:
        return _err("Not found", 404)
    return jsonify(store["catalog"][cid])


@app.put("/catalog/<cid>")
def update_catalog_item(cid):
    if cid not in store["catalog"]:
        return _err("Not found", 404)
    data = request.get_json(force=True, silent=True) or {}
    err = _validate_catalog(data, partial=True)
    if err:
        return _err(err)
    item = store["catalog"][cid]
    for f in ("sku", "name", "category"):
        if f in data:
            item[f] = data[f].strip() if isinstance(data[f], str) else data[f]
    if "cubicMetres" in data:
        item["cubicMetres"] = float(data["cubicMetres"])
    return jsonify(item)


@app.delete("/catalog/<cid>")
def delete_catalog_item(cid):
    if cid not in store["catalog"]:
        return _err("Not found", 404)
    del store["catalog"][cid]
    return "", 204


# ---------------- Rate Matching + Calculation ----------------
def match_rate(service_type, from_city, dest_city, dest_suburb):
    candidates = [
        rc for rc in store["rateCards"].values()
        if rc["serviceType"] == service_type and rc["fromCity"] == from_city
    ]
    # City matching
    city_matches = [rc for rc in candidates if rc["toCity"] == dest_city]
    if not city_matches:
        return {"tier": "Unavailable", "message": "No rate card for selected route and delivery type."}
    exact = [rc for rc in city_matches if rc["toSuburb"] == dest_suburb]
    if exact:
        best = min(exact, key=lambda r: r["ratePerM3"])
        return {"tier": "Exact Match", "rateCard": best, "ratePerM3": best["ratePerM3"]}
    # City match (fallback)
    best = max(city_matches, key=lambda r: r["ratePerM3"])
    suburbs = {rc["toSuburb"] for rc in city_matches if rc["toSuburb"]}
    n = len(suburbs)
    return {
        "tier": "City Match",
        "rateCard": best,
        "ratePerM3": best["ratePerM3"],
        "message": f"{n} suburbs available for this city.",
        "suburbsAvailable": n,
    }


def _calculate(payload):
    # Validate required
    dtype = payload.get("deliveryType")
    if dtype not in VALID_SVC:
        return None, "Delivery Type is required (B2B or B2C)"
    origin_id = payload.get("originId")
    if not origin_id:
        return None, "Origin is required"
    if not store["locations"]:
        return None, "No locations configured; calculation not possible"
    if origin_id not in store["locations"]:
        return None, "Origin location not found"
    origin = store["locations"][origin_id]

    # Destination
    if dtype == "B2B":
        dest_id = payload.get("destinationId")
        if not dest_id:
            return None, "Destination is required"
        if dest_id not in store["locations"]:
            return None, "Destination location not found"
        dest_loc = store["locations"][dest_id]
        dest_city = dest_loc["city"]
        dest_suburb = dest_loc.get("suburb", "")
    else:  # B2C
        dest_city = (payload.get("destinationCity") or "").strip()
        if not dest_city:
            return None, "Destination City is required for B2C"
        dest_suburb = (payload.get("destinationSuburb") or "").strip()
        dest_loc = None

    # Items
    items_in = payload.get("items") or []
    if not items_in:
        return None, "At least one item is required"

    total_volume = 0.0
    resolved_items = []
    for it in items_in:
        qty = it.get("quantity")
        if not isinstance(qty, int) or qty < 1 or qty > 10:
            return None, "Item quantity must be integer 1-10"
        if "catalogId" in it and it["catalogId"]:
            cid = it["catalogId"]
            if cid not in store["catalog"]:
                return None, "Catalog item not found"
            catalog_item = store["catalog"][cid]
            if "cubicMetresOverride" in it and it["cubicMetresOverride"] is not None:
                try:
                    m3 = float(it["cubicMetresOverride"])
                except (TypeError, ValueError):
                    return None, "Invalid cubicMetresOverride"
                if m3 <= 0:
                    return None, "cubicMetresOverride must be > 0"
            else:
                m3 = catalog_item["cubicMetres"]
            resolved_items.append({
                "source": "catalog",
                "catalogId": cid,
                "sku": catalog_item["sku"],
                "name": catalog_item["name"],
                "cubicMetres": m3,
                "quantity": qty,
                "lineVolume": m3 * qty,
            })
        else:
            name = (it.get("name") or "").strip()
            if not name:
                return None, "Custom item requires name"
            if "cubicMetres" not in it:
                return None, "Custom item requires cubicMetres"
            try:
                m3 = float(it["cubicMetres"])
            except (TypeError, ValueError):
                return None, "Invalid cubicMetres"
            if m3 <= 0:
                return None, "cubicMetres must be > 0"
            resolved_items.append({
                "source": "custom",
                "name": name,
                "cubicMetres": m3,
                "quantity": qty,
                "lineVolume": m3 * qty,
            })
        total_volume += resolved_items[-1]["lineVolume"]

    # Services
    services = payload.get("services") or {}
    assembly_intervals = services.get("assemblyIntervals", 0) or 0
    rubbish_qty = services.get("rubbishQuantity", 0) or 0
    rural_km = services.get("ruralKm", 0) or 0

    if not isinstance(assembly_intervals, int) or assembly_intervals < 0 or assembly_intervals > 99:
        return None, "assemblyIntervals must be integer 0-99"
    if not isinstance(rubbish_qty, int) or rubbish_qty < 0 or rubbish_qty > 99:
        return None, "rubbishQuantity must be integer 0-99"
    try:
        rural_km_f = float(rural_km)
    except (TypeError, ValueError):
        return None, "Invalid ruralKm"
    if rural_km_f < 0:
        return None, "ruralKm must be >= 0"
    if dtype == "B2B" and rural_km_f > 0:
        return None, "Rural km is not accepted for B2B"

    # Match rate
    match = match_rate(dtype, origin["city"], dest_city, dest_suburb)

    settings = store["settings"]
    assembly_cost = settings["assemblyRatePerInterval"] * assembly_intervals
    rubbish_cost = settings["rubbishFlatRate"] * rubbish_qty
    rural_cost = settings["ruralRatePerKm"] * rural_km_f if dtype == "B2C" else 0.0

    volume_charged = max(1.0, total_volume)
    volume_note = None
    if total_volume < 1.0:
        volume_note = f"{_fmt_vol(total_volume):.2f} m³ (charged as 1.00 m³)"

    result = {
        "deliveryType": dtype,
        "origin": {"id": origin["id"], "city": origin["city"], "suburb": origin.get("suburb", ""), "name": origin["name"]},
        "destination": {
            "city": dest_city,
            "suburb": dest_suburb,
            "locationId": dest_loc["id"] if dest_loc else None,
            "name": dest_loc["name"] if dest_loc else None,
        },
        "items": resolved_items,
        "services": {
            "assemblyIntervals": assembly_intervals,
            "rubbishQuantity": rubbish_qty,
            "ruralKm": rural_km_f,
        },
        "totalCubicMetres": _fmt_vol(total_volume),
        "volumeCharged": _fmt_vol(volume_charged),
        "volumeNote": volume_note,
        "matchTier": match["tier"],
        "assemblyCost": _fmt_money(assembly_cost),
        "rubbishCost": _fmt_money(rubbish_cost),
        "ruralCost": _fmt_money(rural_cost),
        "settingsSnapshot": deepcopy(settings),
    }

    if match["tier"] == "Unavailable":
        result["message"] = match["message"]
        result["ratePerM3"] = None
        result["baseDelivery"] = None
        result["total"] = None
        result["available"] = False
    else:
        rate = match["ratePerM3"]
        base = rate * volume_charged
        total = base + assembly_cost + rubbish_cost + rural_cost
        result["ratePerM3"] = _fmt_money(rate)
        result["baseDelivery"] = _fmt_money(base)
        result["total"] = _fmt_money(total)
        result["available"] = True
        result["matchedRateCard"] = deepcopy(match["rateCard"])
        if match["tier"] == "City Match":
            result["message"] = match["message"]
            result["suburbsAvailable"] = match["suburbsAvailable"]

    return result, None


@app.post("/quote/calculate")
def calculate_endpoint():
    payload = request.get_json(force=True, silent=True) or {}
    result, err = _calculate(payload)
    if err:
        return _err(err)
    return jsonify(result)


# ---------------- Quotes ----------------
@app.post("/quotes")
def save_quote():
    payload = request.get_json(force=True, silent=True) or {}
    result, err = _calculate(payload)
    if err:
        return _err(err)
    qid = str(uuid.uuid4())
    snap = {
        "id": qid,
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "input": deepcopy(payload),
        "result": deepcopy(result),
    }
    store["quotes"][qid] = snap
    return jsonify(snap), 201


@app.get("/quotes")
def list_quotes():
    out = []
    for q in store["quotes"].values():
        r = q["result"]
        dest_display = f"{r['destination']['city']}"
        if r['destination'].get('suburb'):
            dest_display += f" ({r['destination']['suburb']})"
        out.append({
            "id": q["id"],
            "timestamp": q["timestamp"],
            "deliveryType": r["deliveryType"],
            "originCity": r["origin"]["city"],
            "destination": dest_display,
            "matchTier": r["matchTier"],
            "total": r["total"] if r["available"] else "Unavailable",
        })
    out.sort(key=lambda x: x["timestamp"], reverse=True)
    return jsonify(out)


@app.get("/quotes/<qid>")
def get_quote(qid):
    if qid not in store["quotes"]:
        return _err("Not found", 404)
    return jsonify(store["quotes"][qid])


@app.delete("/quotes/<qid>")
def delete_quote(qid):
    if qid not in store["quotes"]:
        return _err("Not found", 404)
    del store["quotes"][qid]
    return "", 204


# ---------------- Reset ----------------
@app.post("/admin/reset")
def reset():
    global store
    store = new_store()
    return jsonify({"status": "reset"})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
