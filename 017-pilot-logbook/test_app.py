"""Basic smoke test of the pilot logbook API."""
import json
from datetime import date, timedelta, datetime, timezone

import app as app_module


def jload(resp):
    return json.loads(resp.get_data(as_text=True))


def main():
    client = app_module.app.test_client()

    # health
    r = client.get("/health")
    assert r.status_code == 200

    # create aircraft
    r = client.post("/aircraft", json={
        "registration": "N-123AB",
        "make_model": "Cessna 172",
        "category": "Airplane",
        "class": "SEL",
    })
    assert r.status_code == 201, r.get_data(as_text=True)
    ac1 = jload(r)
    print("Created aircraft:", ac1["registration"], ac1["id"])

    # duplicate canonical tail -> conflict
    r = client.post("/aircraft", json={
        "registration": "n123ab",
        "make_model": "Cessna 172",
        "category": "Airplane",
        "class": "SEL",
    })
    assert r.status_code == 409, r.status_code

    # invalid category/class
    r = client.post("/aircraft", json={
        "registration": "N999XX",
        "make_model": "Foo",
        "category": "Airplane",
        "class": "Helicopter",
    })
    assert r.status_code == 400

    # type rating required needs designator
    r = client.post("/aircraft", json={
        "registration": "N737BA",
        "make_model": "Boeing 737",
        "category": "Airplane",
        "class": "MEL",
        "type_rating_required": True,
    })
    assert r.status_code == 400

    r = client.post("/aircraft", json={
        "registration": "N737BA",
        "make_model": "Boeing 737",
        "category": "Airplane",
        "class": "MEL",
        "type_rating_required": True,
        "type_designator": "B737",
    })
    assert r.status_code == 201
    ac2 = jload(r)

    # create flight - basic valid
    today = datetime.now(timezone.utc).date()
    r = client.post("/flights", json={
        "date": today.isoformat(),
        "aircraft_id": ac1["id"],
        "departure": "KJFK",
        "arrival": "KBOS",
        "total_time": 2.0,
        "day_time": 2.0,
        "night_time": 0.0,
        "pic": 2.0,
        "day_takeoffs": 1,
        "day_landings": 1,
    })
    assert r.status_code == 201, r.get_data(as_text=True)
    fl1 = jload(r)

    # future date not allowed
    r = client.post("/flights", json={
        "date": (today + timedelta(days=1)).isoformat(),
        "aircraft_id": ac1["id"],
        "departure": "A", "arrival": "B",
        "total_time": 1.0, "day_time": 1.0,
    })
    assert r.status_code == 400

    # day+night != total
    r = client.post("/flights", json={
        "date": today.isoformat(),
        "aircraft_id": ac1["id"],
        "departure": "A", "arrival": "B",
        "total_time": 2.0, "day_time": 1.0, "night_time": 0.5,
    })
    assert r.status_code == 400

    # 0.1 increments
    r = client.post("/flights", json={
        "date": today.isoformat(),
        "aircraft_id": ac1["id"],
        "departure": "A", "arrival": "B",
        "total_time": 1.05, "day_time": 1.05,
    })
    assert r.status_code == 400

    # PIC and SIC both > 0
    r = client.post("/flights", json={
        "date": today.isoformat(),
        "aircraft_id": ac1["id"],
        "departure": "A", "arrival": "B",
        "total_time": 2.0, "day_time": 2.0,
        "pic": 1.0, "sic": 1.0,
    })
    assert r.status_code == 400

    # Archive aircraft, cannot use for new flight
    r = client.post(f"/aircraft/{ac1['id']}/archive")
    assert r.status_code == 200
    r = client.post("/flights", json={
        "date": today.isoformat(),
        "aircraft_id": ac1["id"],
        "departure": "A", "arrival": "B",
        "total_time": 1.0, "day_time": 1.0,
    })
    assert r.status_code == 400

    # Edit existing flight without changing aircraft: allowed
    r = client.put(f"/flights/{fl1['id']}", json={
        "date": today.isoformat(),
        "departure": "KJFK",
        "arrival": "KBOS",
        "total_time": 2.5, "day_time": 2.5,
        "pic": 2.5,
        "day_takeoffs": 1, "day_landings": 1,
    })
    assert r.status_code == 200, r.get_data(as_text=True)

    # unarchive
    client.post(f"/aircraft/{ac1['id']}/unarchive")

    # Add more flights for currency
    for i in range(3):
        d = today - timedelta(days=i)
        r = client.post("/flights", json={
            "date": d.isoformat(),
            "aircraft_id": ac1["id"],
            "departure": "KJFK", "arrival": "KBOS",
            "total_time": 1.0, "day_time": 1.0,
            "day_takeoffs": 1, "day_landings": 1,
            "instrument_approaches": 2,
            "holds_performed": True,
            "intercept_track_performed": True,
        })
        assert r.status_code == 201

    # Filters + listing
    r = client.get("/flights?text=KJFK")
    assert r.status_code == 200
    fls = jload(r)
    assert len(fls) >= 2

    # Analytics totals
    r = client.get("/analytics/totals?preset=last_90_days&group_by=category_class")
    assert r.status_code == 200
    tot = jload(r)
    print("Totals:", tot)

    # Currency
    r = client.get("/analytics/currency")
    assert r.status_code == 200
    cur = jload(r)
    print("Currency:", cur)
    # Should have Airplane/SEL day current
    dn = [x for x in cur["day_night"] if x["category"] == "Airplane" and x["class"] == "SEL"]
    assert dn and dn[0]["day"]["current"] is True

    # Export
    r = client.get("/export.csv")
    assert r.status_code == 200
    csv_text = r.get_data(as_text=True)
    print("CSV first 200 chars:")
    print(csv_text[:200])
    assert "date,aircraft_registration" in csv_text.splitlines()[0]

    # Delete a flight
    r = client.delete(f"/flights/{fl1['id']}")
    assert r.status_code == 200

    print("ALL TESTS PASSED")


if __name__ == "__main__":
    main()
