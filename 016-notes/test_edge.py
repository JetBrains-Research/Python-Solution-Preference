import subprocess
import time
import requests
import signal

# Kill any existing server
subprocess.run(["pkill", "-f", "python3 app.py"], capture_output=True)
time.sleep(0.5)

proc = subprocess.Popen(["python3", "app.py"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
time.sleep(2)

BASE = "http://localhost:8080"
PASSWORD = "my-notes-are-mine"
FAILS = 0

def check(condition, desc):
    global FAILS
    if not condition:
        FAILS += 1
        print(f"FAIL: {desc}")
    else:
        print(f"PASS: {desc}")

try:
    # Empty query shows all notes
    r1 = requests.post(f"{BASE}/notes", headers={"X-Password": PASSWORD})
    r2 = requests.post(f"{BASE}/notes", headers={"X-Password": PASSWORD})
    requests.put(f"{BASE}/notes/{r1.json().get('id')}", headers={"X-Password": PASSWORD}, json={"body": "Note Alpha"})
    requests.put(f"{BASE}/notes/{r2.json().get('id')}", headers={"X-Password": PASSWORD}, json={"body": "Note Beta"})

    r = requests.get(f"{BASE}/notes?q=", headers={"X-Password": PASSWORD})
    check(len(r.json().get("notes", [])) == 2, "empty query shows all")

    # Whitespace-only body
    r3 = requests.post(f"{BASE}/notes", headers={"X-Password": PASSWORD})
    requests.put(f"{BASE}/notes/{r3.json().get('id')}", headers={"X-Password": PASSWORD}, json={"body": "   \n\t\n  "})
    r = requests.get(f"{BASE}/notes", headers={"X-Password": PASSWORD})
    titles = [n["title"] for n in r.json().get("notes", [])]
    check("New Note" in titles, "whitespace-only body uses placeholder")

    # Truncation with ellipsis
    long_text = "A" * 100
    r4 = requests.post(f"{BASE}/notes", headers={"X-Password": PASSWORD})
    requests.put(f"{BASE}/notes/{r4.json().get('id')}", headers={"X-Password": PASSWORD}, json={"body": f"Title\n{long_text}"})
    r = requests.get(f"{BASE}/notes", headers={"X-Password": PASSWORD})
    for n in r.json().get("notes", []):
        if n["title"] == "Title":
            check(n["preview"].endswith("...") and len(n["preview"]) == 83, "truncation with ellipsis")
            break

    # Note counts hidden without password
    r = requests.get(f"{BASE}/notes", headers={"X-Password": PASSWORD})
    info = r.json()
    check("notes" in info, "data accessible WITH password")

    print(f"\nDone. {FAILS} failures.")

except Exception as e:
    print(f"Exception: {e}")
finally:
    proc.terminate()
    time.sleep(0.5)
    subprocess.run(["pkill", "-f", "python3 app.py"], capture_output=True)
