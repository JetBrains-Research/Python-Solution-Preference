import json
import re
from typing import List, Optional
from fastapi import FastAPI, Header, HTTPException, Body
from pydantic import BaseModel, Field

app = FastAPI()

# Data storage
with open('assets/books.json', 'r') as f:
    books = json.load(f)

users = set()
checkpoints = []  # List of dicts: {username, book_id, chapter, note, mood}

# Models
class LoginRequest(BaseModel):
    username: str

class CheckpointRequest(BaseModel):
    chapter: int
    note: str
    mood: Optional[str] = None

# Helpers
def validate_username(username: str):
    if not (3 <= len(username) <= 20):
        raise HTTPException(status_code=400, detail="Username must be between 3 and 20 characters")
    if not re.match(r'^\w+$', username):
        raise HTTPException(status_code=400, detail="Username must contain only letters, numbers, and underscores")

def get_current_user(x_username: Optional[str] = Header(None)):
    if not x_username:
        raise HTTPException(status_code=401, detail="Authentication required")
    if x_username not in users:
        raise HTTPException(status_code=401, detail="User not logged in")
    return x_username

# API Endpoints
@app.post("/login")
async def login(request: LoginRequest):
    username = request.username
    validate_username(username)
    users.add(username)
    return {"message": "Logged in successfully", "username": username}

@app.get("/books")
async def browse_books(q: Optional[str] = None):
    results = []
    for b in books:
        # Preview synopsis: first 100 chars
        preview = b['synopsis'][:100] + "..." if len(b['synopsis']) > 100 else b['synopsis']
        results.append({
            "title": b['title'],
            "author": b['author'],
            "year_published": b['year_published'],
            "genre": b['genre'],
            "synopsis_preview": preview
        })
    
    if q:
        q = q.lower()
        results = [b for b in results if q in b['title'].lower() or q in b['author'].lower()]
    
    return results

@app.get("/my-journey")
async def my_journey(x_username: Optional[str] = Header(None)):
    user = get_current_user(x_username)
    user_book_ids = {cp['book_id'] for cp in checkpoints if cp['username'] == user}
    
    journey = []
    for b in books:
        if b['id'] in user_book_ids:
            journey.append({
                "title": b['title'],
                "author": b['author'],
                "year_published": b['year_published']
            })
    return journey

@app.get("/books/{book_id}")
async def book_details(book_id: int, x_username: Optional[str] = Header(None)):
    book = next((b for b in books if b['id'] == book_id), None)
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")
    
    user = get_current_user(x_username)
    
    user_cps = [cp for cp in checkpoints if cp['book_id'] == book_id and cp['username'] == user]
    all_cps = [cp for cp in checkpoints if cp['book_id'] == book_id]
    all_cps.sort(key=lambda x: x['chapter'])
    
    reader_checkpoints = []
    for cp in all_cps:
        reader_checkpoints.append({
            "username": cp['username'],
            "chapter": cp['chapter'],
            "note": cp['note'],
            "mood": cp['mood'],
            "is_mine": cp['username'] == user
        })

    return {
        "details": {
            "title": book['title'],
            "author": book['author'],
            "year_published": book['year_published'],
            "genre": book['genre'],
            "synopsis": book['synopsis'],
            "total_chapters": book['total_chapters']
        },
        "your_journey": {
            "has_checkpoints": len(user_cps) > 0,
            "count": len(user_cps)
        },
        "reader_checkpoints": reader_checkpoints
    }

@app.post("/books/{book_id}/checkpoints")
async def add_checkpoint(book_id: int, request: CheckpointRequest, x_username: Optional[str] = Header(None)):
    user = get_current_user(x_username)
    book = next((b for b in books if b['id'] == book_id), None)
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")
    
    # Validation
    chapter = request.chapter
    if not (1 <= chapter <= book['total_chapters']):
        raise HTTPException(status_code=400, detail=f"Chapter must be between 1 and {book['total_chapters']}")
    
    note = request.note.strip()
    if not (1 <= len(note) <= 280):
        raise HTTPException(status_code=400, detail="Note must be between 1 and 280 characters")
    
    mood = request.mood
    valid_moods = {"Curious", "Confused", "Excited", "Calm", "Sad", "Delighted"}
    if mood and mood not in valid_moods:
        raise HTTPException(status_code=400, detail=f"Mood must be one of {', '.join(valid_moods)}")
    
    checkpoints.append({
        "username": user,
        "book_id": book_id,
        "chapter": chapter,
        "note": note,
        "mood": mood
    })
    
    return {"message": "Checkpoint saved"}
