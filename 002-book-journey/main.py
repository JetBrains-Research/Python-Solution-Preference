import json
import uuid
from pathlib import Path
from typing import List, Optional, Dict

from fastapi import FastAPI, HTTPException, Depends, Header, Query, status
from pydantic import BaseModel, Field, validator

app = FastAPI(title="Book Journey MVP")

# Load books data
BOOKS_PATH = Path(__file__).parent / "assets" / "books.json"
with BOOKS_PATH.open() as f:
    books_data = json.load(f)

# Index books by id for quick lookup
books_by_id: Dict[int, dict] = {book["id"]: book for book in books_data}

# In‑memory stores
users: set = set()                         # usernames
sessions: Dict[str, str] = {}              # token -> username
checkpoints: Dict[int, List[dict]] = {}    # book_id -> list of checkpoints


# ----- Models -----
USERNAME_REGEX = r'^[A-Za-z0-9_]{3,20}$'


class LoginRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=20, regex=USERNAME_REGEX)


class CheckpointCreate(BaseModel):
    chapter: int
    note: str = Field(..., min_length=1, max_length=280)
    mood: Optional[str] = None

    @validator('chapter')
    def chapter_range(cls, v, values, **kwargs):
        # book total chapters will be validated later in route
        if v < 1:
            raise ValueError('chapter must be >= 1')
        return v

    @validator('mood')
    def valid_mood(cls, v):
        allowed = {"Curious", "Confused", "Excited", "Calm", "Sad", "Delighted"}
        if v is not None and v not in allowed:
            raise ValueError(f'mood must be one of {allowed}')
        return v

    @validator('note')
    def trim_note(cls, v):
        return v.strip()


class CheckpointOut(BaseModel):
    username: str
    chapter: int
    note: str
    mood: Optional[str] = None
    is_self: bool = False


# ----- Dependency -----
def get_current_user(authorization: Optional[str] = Header(None)):
    if not authorization:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="Missing Authorization header")
    token = authorization.replace("Bearer ", "")
    username = sessions.get(token)
    if not username:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="Invalid or expired token")
    return username


# ----- Endpoints -----
@app.post("/login")
def login(req: LoginRequest):
    username = req.username
    if username in users:
        # existing user, just log in
        pass
    else:
        users.add(username)
    # create new token
    token = str(uuid.uuid4())
    sessions[token] = username
    return {"token": token, "username": username}


@app.get("/books")
def browse_books(q: Optional[str] = Query(None, description="Search query for title or author")):
    result = []
    for book in books_data:
        if q:
            if q.lower() not in book["title"].lower() and q.lower() not in book["author"].lower():
                continue
        # synopsis preview: first 100 chars
        preview = book["synopsis"][:100] + ("..." if len(book["synopsis"]) > 100 else "")
        result.append({
            "id": book["id"],
            "title": book["title"],
            "author": book["author"],
            "year_published": book["year_published"],
            "genre": book["genre"],
            "synopsis_preview": preview
        })
    return result


@app.get("/myjourney")
def my_journey(current_user: str = Depends(get_current_user)):
    journey = []
    for book_id, cps in checkpoints.items():
        if any(cp["username"] == current_user for cp in cps):
            book = books_by_id[book_id]
            journey.append({
                "id": book_id,
                "title": book["title"],
                "author": book["author"],
                "year_published": book["year_published"]
            })
    return journey


@app.get("/books/{book_id}")
def book_details(book_id: int, current_user: str = Depends(get_current_user)):
    book = books_by_id.get(book_id)
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")

    # User's checkpoints count for this book
    user_cps = [cp for cp in checkpoints.get(book_id, []) if cp["username"] == current_user]
    user_checkpoint_count = len(user_cps)
    has_checkpoints = user_checkpoint_count > 0

    # All checkpoints sorted by chapter
    all_cps = sorted(checkpoints.get(book_id, []), key=lambda x: x["chapter"])
    cps_out = []
    for cp in all_cps:
        cps_out.append({
            "username": cp["username"],
            "chapter": cp["chapter"],
            "note": cp["note"],
            "mood": cp.get("mood"),
            "is_self": cp["username"] == current_user
        })

    return {
        "book": {
            "title": book["title"],
            "author": book["author"],
            "year_published": book["year_published"],
            "genre": book["genre"],
            "synopsis": book["synopsis"],
            "total_chapters": book["total_chapters"]
        },
        "your_journey": {
            "has_checkpoints": has_checkpoints,
            "checkpoint_count": user_checkpoint_count
        },
        "reader_checkpoints": cps_out
    }


@app.post("/books/{book_id}/checkpoints")
def add_checkpoint(book_id: int, cp: CheckpointCreate, current_user: str = Depends(get_current_user)):
    book = books_by_id.get(book_id)
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")
    total = book["total_chapters"]
    if not (1 <= cp.chapter <= total):
        raise HTTPException(status_code=400, detail=f"chapter must be between 1 and {total}")

    # Validate note length after trimming (already done by model)
    # Mood already validated

    # Save checkpoint
    entry = {
        "username": current_user,
        "chapter": cp.chapter,
        "note": cp.note,
        "mood": cp.mood
    }
    checkpoints.setdefault(book_id, []).append(entry)
    return {"detail": "Checkpoint saved"}
