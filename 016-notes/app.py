import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from fastapi import FastAPI, HTTPException, Query

app = FastAPI()

PASSWORD = "my-notes-are-mine"
DATA_FILE = Path("notes.json")


def load_notes():
    if DATA_FILE.is_file():
        with DATA_FILE.open("r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_notes(notes):
    with DATA_FILE.open("w", encoding="utf-8") as f:
        json.dump(notes, f, ensure_ascii=False, indent=2)


def check_password(pwd: Optional[str]):
    if pwd is None:
        raise HTTPException(status_code=400, detail="Password is required")
    if pwd != PASSWORD:
        raise HTTPException(status_code=403, detail="Incorrect password")


def format_timestamp(ts_str: str) -> str:
    dt = datetime.fromisoformat(ts_str).astimezone(timezone.utc)
    return dt.strftime("%Y-%m-%d %H:%M")


def get_title(body: str) -> str:
    for line in body.splitlines():
        stripped = line.strip()
        if stripped:
            return stripped
    return "New Note"


def get_preview(body: str) -> str:
    lines = body.splitlines()
    # Find first non‑empty line as title
    title_idx = None
    for i, line in enumerate(lines):
        if line.strip():
            title_idx = i
            break
    if title_idx is None:
        return ""
    # Preview is the line after title
    if title_idx + 1 < len(lines):
        preview = lines[title_idx + 1].strip()
        if len(preview) > 50:
            return preview[:47] + "..."
        return preview
    return ""


@app.get("/notes")
def list_notes(password: Optional[str] = Query(None), q: Optional[str] = Query(None)):
    check_password(password)
    notes = load_notes()
    result = []
    for nid, note in notes.items():
        body = note["body"]
        title = get_title(body)
        preview = get_preview(body)
        ts = format_timestamp(note["updated_at"])
        result.append(
            {
                "id": nid,
                "title": title,
                "preview": preview,
                "timestamp": ts,
            }
        )
    if q:
        q_lower = q.lower()
        result = [
            n
            for n in result
            if q_lower in n["title"].lower()
            or q_lower in notes[n["id"]]["body"].lower()
        ]
    # Sort by updated_at descending
    result.sort(
        key=lambda x: notes[x["id"]]["updated_at"], reverse=True
    )
    return result


@app.post("/notes")
def create_note(password: Optional[str] = Query(None)):
    check_password(password)
    notes = load_notes()
    nid = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    notes[nid] = {"body": "", "updated_at": now}
    save_notes(notes)
    return {"id": nid}


@app.put("/notes/{note_id}")
def edit_note(
    note_id: str,
    body: str,
    password: Optional[str] = Query(None),
):
    check_password(password)
    notes = load_notes()
    if note_id not in notes:
        raise HTTPException(status_code=404, detail="Note not found")
    notes[note_id]["body"] = body
    notes[note_id]["updated_at"] = datetime.now(timezone.utc).isoformat()
    save_notes(notes)
    return {"status": "updated"}


@app.delete("/notes/{note_id}")
def delete_note(note_id: str, password: Optional[str] = Query(None)):
    check_password(password)
    notes = load_notes()
    if note_id not in notes:
        raise HTTPException(status_code=404, detail="Note not found")
    del notes[note_id]
    save_notes(notes)
    return {"status": "deleted"}


@app.get("/notes/{note_id}")
def get_note(note_id: str, password: Optional[str] = Query(None)):
    check_password(password)
    notes = load_notes()
    if note_id not in notes:
        raise HTTPException(status_code=404, detail="Note not found")
    return {"id": note_id, "body": notes[note_id]["body"]}


# Optional: simple run command
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
