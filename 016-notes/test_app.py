import subprocess
import time
import json
import requests
import signal
import sys

# Kill any existing server
subprocess.run(["pkill", "-f", "python3 app.py"], capture_output=True)

# Start server
proc = subprocess.Popen(
    ["python3", "app.py"],
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    preexec_fn=lambda: signal.signal(signal.SIGINT, signal.SIG_IGN)
)
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
    # 1. Health endpoint
    r = requests.get(f"{BASE}/")
    check(r.status_code == 200 and r.json().get("status") == "ok", "health endpoint")

    # 2. Missing password
    r = requests.get(f"{BASE}/notes")
    check(r.status_code == 401 and "required" in r.json().get("error", "").lower(), "missing password")

    # 3. Wrong password
    r = requests.get(f"{BASE}/notes", headers={"X-Password": "wrong"})
    check(r.status_code == 403 and "incorrect" in r.json().get("error", "").lower(), "wrong password")

    # 4. Create note
    r = requests.post(f"{BASE}/notes", headers={"X-Password": PASSWORD})
    check(r.status_code == 201, "create note")
    nid = r.json().get("id")
    ts = r.json().get("timestamp")

    # 5. List notes - empty body title
    r = requests.get(f"{BASE}/notes", headers={"X-Password": PASSWORD})
    notes = r.json().get("notes", [])
    check(len(notes) == 1 and notes[0].get("title") == "New Note", "empty note title is New Note")

    # 6. Update note
    r = requests.put(f"{BASE}/notes/{nid}", headers={"X-Password": PASSWORD}, json={"body": "Hello World\nThis is a preview line.\nMore text here."})
    check(r.status_code == 200, "update note")
    ts2 = r.json().get("timestamp")

    # 7. Get note
    r = requests.get(f"{BASE}/notes/{nid}", headers={"X-Password": PASSWORD})
    check(r.status_code == 200 and r.json().get("body") == "Hello World\nThis is a preview line.\nMore text here.", "get note")

    # 8. List notes after update
    r = requests.get(f"{BASE}/notes", headers={"X-Password": PASSWORD})
    notes = r.json().get("notes", [])
    check(len(notes) == 1 and notes[0].get("title") == "Hello World", "title from first non-empty line")
    check(notes[0].get("preview") == "This is a preview line.", "preview from next non-empty line")
    check(notes[0].get("timestamp") == ts2, "timestamp updated on save")

    # 9. Create another note
    r = requests.post(f"{BASE}/notes", headers={"X-Password": PASSWORD})
    nid2 = r.json().get("id")

    # 10. Search
    r = requests.get(f"{BASE}/notes?q=Hello", headers={"X-Password": PASSWORD})
    notes = r.json().get("notes", [])
    check(len(notes) == 1 and notes[0].get("id") == nid, "search by title")
    r = requests.get(f"{BASE}/notes?q=preview", headers={"X-Password": PASSWORD})
    notes = r.json().get("notes", [])
    check(len(notes) == 1 and notes[0].get("id") == nid, "search by body")

    # 11. Delete note
    r = requests.delete(f"{BASE}/notes/{nid2}", headers={"X-Password": PASSWORD})
    check(r.status_code == 200, "delete note")
    r = requests.get(f"{BASE}/notes", headers={"X-Password": PASSWORD})
    notes = r.json().get("notes", [])
    check(len(notes) == 1, "note removed after delete")

    # 12. Sorting - create note with newer edit
    time.sleep(1.5)
    requests.put(f"{BASE}/notes/{nid}", headers={"X-Password": PASSWORD}, json={"body": "Updated Again"})
    r = requests.get(f"{BASE}/notes", headers={"X-Password": PASSWORD})
    notes = r.json().get("notes", [])
    check(len(notes) == 1 and notes[0].get("title") == "Updated Again", "sorting newest first")

    # 13. Persistence
    proc.terminate()
    time.sleep(1)
    proc2 = subprocess.Popen(["python3", "app.py"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    time.sleep(2)
    r = requests.get(f"{BASE}/notes", headers={"X-Password": PASSWORD})
    notes = r.json().get("notes", [])
    check(len(notes) == 1 and notes[0].get("title") == "Updated Again", "persistence across restart")
    proc2.terminate()

    print(f"\nDone. {FAILS} failures.")

except Exception as e:
    print(f"Exception: {e}")
    import traceback
    traceback.print_exc()
finally:
    proc.terminate()
    proc2 = subprocess.Popen(["python3", "app.py"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    proc2.pid  # just to quiet variable warning
    subprocess.run(["pkill", "-f", "python3 app.py"], capture_output=True)
    sys.exit(FAILS)
