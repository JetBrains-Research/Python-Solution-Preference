import json
import string
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

app = FastAPI()

# Paths
BASE_DIR = Path(__file__).parent
QUESTIONS_PATH = BASE_DIR / "assets" / "questions.json"
STATE_PATH = BASE_DIR / "state.json"

# Load exercise definitions
def load_questions() -> Dict[str, Any]:
    """Load and flatten all exercises from questions.json."""
    with QUESTIONS_PATH.open(encoding="utf-8") as f:
        data = json.load(f)
    exercises = {}
    for lst in data["exercises"].values():
        for ex in lst:
            exercises[ex["id"]] = ex
    return exercisesQUESTIONS = load_questions()

# Default state structure
def default_state() -> Dict[str, Any]:
    return {
        "lessons": {
            "1": {
                "status": "Not started",
                "current_exercise": 0,   # 0‑based index
                "correct": 0,
                "completed": False,
            },
            "2": {
                "status": "Locked",
                "current_exercise": 0,
                "correct": 0,
                "completed": False,
            },
        }
    }

# Load or create persistent state
def load_state() -> Dict[str, Any]:
    if STATE_PATH.exists():
        with STATE_PATH.open(encoding="utf-8") as f:
            return json.load(f)
    else:
        state = default_state()
        save_state(state)
        return state

def save_state(state: Dict[str, Any]) -> None:
    with STATE_PATH.open("w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)

STATE = load_state()

# Helper functions
def lesson_unlock_check():
    """Unlock Lesson 2 if Lesson 1 was completed with at least 4 correct."""
    l1 = STATE["lessons"]["1"]
    if l1["completed"] and l1["correct"] >= 4:
        l2 = STATE["lessons"]["2"]
        if l2["status"] == "Locked":
            l2["status"] = "Not started"
            save_state(STATE)

def get_lesson_status(lesson_id: str) -> Dict[str, Any]:
    lesson = STATE["lessons"][lesson_id]
    status = lesson["status"]
    if status.startswith("Completed"):
        return {
            "lesson": f"Lesson {lesson_id}",
            "status": f"Completed - {lesson['correct']}/5 correct ({int(lesson['correct']*20)}%)"
        }
    return {"lesson": f"Lesson {lesson_id}", "status": status}

def normalize_text(text: str) -> str:
    return text.strip().lower().translate(str.maketrans("", "", string.punctuation))

# Pydantic models for request bodies
class AnswerSubmission(BaseModel):
    answer: Any

# Endpoints
@app.get("/lessons")
def list_lessons():
    """Return status of both lessons."""
    lesson1 = get_lesson_status("1")
    lesson2 = get_lesson_status("2")
    return {"lessons": [lesson1, lesson2]}

@app.get("/lessons/{lesson_id}")
def get_lesson_detail(lesson_id: str):
    if lesson_id not in STATE["lessons"]:
        raise HTTPException(status_code=404, detail="Lesson not found")
    lesson = STATE["lessons"][lesson_id]
    return {
        "lesson": f"Lesson {lesson_id}",
        "status": lesson["status"],
        "current_exercise": lesson["current_exercise"] + 1 if not lesson["completed"] else None,
        "correct_sofar": lesson["correct"],
    }

@app.get("/lessons/{lesson_id}/exercise")
def get_current_exercise(lesson_id: str):
    lesson = STATE["lessons"].get(lesson_id)
    if not lesson:
        raise HTTPException(status_code=404, detail="Lesson not found")
    if lesson["status"] == "Locked":
        raise HTTPException(status_code=403, detail="Lesson is locked")
    if lesson["completed"]:
        raise HTTPException(status_code=400, detail="Lesson already completed")
    # Determine exercise id based on lesson and index
    idx = lesson["current_exercise"]
    ex_id = f"{['mc','match','order','fill','typed'][idx]}_{lesson_id}"
    ex = QUESTIONS.get(ex_id)
    if not ex:
        raise HTTPException(status_code=500, detail="Exercise definition missing")
    # Return necessary fields without revealing the correct answer
    resp = {
        "exercise_id": ex["id"],
        "type": ex["type"],
        "prompt": ex["prompt"],
    }
    # Include type‑specific data
    if ex["type"] == "multiple_choice":
        resp["options"] = ex["options"]
    elif ex["type"] == "matching":
        resp["spanish"] = ex["spanish"]
        resp["english"] = ex["english"]
    elif ex["type"] == "ordering":
        resp["words"] = ex["words"]
    elif ex["type"] == "fill_in_blank":
        resp["sentence"] = ex["sentence"]
        resp["word_bank"] = ex["word_bank"]
    elif ex["type"] == "typed_translation":
        resp["sentence"] = ex["sentence"]
    return resp

@app.post("/lessons/{lesson_id}/exercise")
def submit_answer(lesson_id: str, payload: AnswerSubmission):
    lesson = STATE["lessons"].get(lesson_id)
    if not lesson:
        raise HTTPException(status_code=404, detail="Lesson not found")
    if lesson["status"] == "Locked":
        raise HTTPException(status_code=403, detail="Lesson is locked")
    if lesson["completed"]:
        raise HTTPException(status_code=400, detail="Lesson already completed")
    idx = lesson["current_exercise"]
    ex_id = f"{['mc','match','order','fill','typed'][idx]}_{lesson_id}"
    ex = QUESTIONS.get(ex_id)
    if not ex:
        raise HTTPException(status_code=500, detail="Exercise definition missing")
    # Evaluate answer based on type
    correct = False
    feedback = {}
    answer = payload.answer
    if ex["type"] == "multiple_choice":
        correct = answer == ex["correct_answer"]
        feedback["explanation"] = ex.get("explanation", "")
    elif ex["type"] == "matching":
        # Expect a dict mapping Spanish word to selected English word
        correct = isinstance(answer, dict) and all(
            answer.get(sp) == corr for sp, corr in ex["correct_pairs"].items()
        )
        feedback["per_pair"] = {
            sp: {
                "selected": answer.get(sp),
                "correct": corr,
                "is_correct": answer.get(sp) == corr,
            }
            for sp, corr in ex["correct_pairs"].items()
        }
        feedback["explanation"] = ex.get("explanation", "")
    elif ex["type"] == "ordering":
        correct = answer == ex["correct_order"]
        feedback["correct_sentence"] = " ".join(ex["correct_order"])
        feedback["translation"] = ex.get("translation", "")
        feedback["explanation"] = ex.get("explanation", "")
    elif ex["type"] == "fill_in_blank":
        correct = answer == ex["correct_answer"]
        feedback["explanation"] = ex.get("explanation", "")
    elif ex["type"] == "typed_translation":
        normalized = normalize_text(answer)
        normalized_correct = [normalize_text(c) for c in ex["correct_answers"]]
        correct = normalized in normalized_correct
        feedback["explanation"] = ex.get("explanation", "")
    else:
        raise HTTPException(status_code=400, detail="Unknown exercise type")
    # Update lesson state
    if correct:
        lesson["correct"] += 1
    lesson["current_exercise"] += 1
    # Check if lesson finished
    if lesson["current_exercise"] >= 5:
        lesson["completed"] = True
        percent = int(lesson["correct"] * 20)
        lesson["status"] = f"Completed - {lesson['correct']}/5 correct ({percent}%)"
        # Unlock next lesson if conditions satisfied
        lesson_unlock_check()
    else:
        lesson["status"] = "In progress"
    save_state(STATE)
    return {
        "correct": correct,
        "feedback": feedback,
        "lesson_status": lesson["status"],
        "next_exercise": (lesson["current_exercise"] + 1) if not lesson["completed"] else None,
    }

@app.post("/reset")
def reset_state():
    """Reset all stored state to defaults."""
    global STATE
    STATE = default_state()
    save_state(STATE)
    return {"detail": "State reset to defaults"}
