import json
import os
import uuid
import shutil
from datetime import datetime, timezone
from typing import Optional, List
from io import BytesIO

import numpy as np

from fastapi import FastAPI, HTTPException, Depends, UploadFile, File, Query
from fastapi.responses import FileResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, EmailStr, Field, validator
from passlib.context import CryptContext
import uvicorn

# ── App Setup ──────────────────────────────────────────────────────
app = FastAPI(title="Energy Auditing Field App")

# ── DB Setup (SQLite) ──────────────────────────────────────────────
import sqlite3
DB_PATH = "app.db"

def get_db():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

def init_db():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    cur = conn.cursor()
    
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)
    
    cur.execute("""
        CREATE TABLE IF NOT EXISTS jobs (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL REFERENCES users(id),
            street TEXT NOT NULL,
            city TEXT NOT NULL,
            state TEXT NOT NULL,
            zip TEXT NOT NULL,
            builder_name TEXT NOT NULL,
            scheduled_date TEXT NOT NULL,
            house_volume REAL NOT NULL,
            conditioned_floor_area REAL NOT NULL,
            num_stories INTEGER,
            surface_area REAL,
            status TEXT NOT NULL DEFAULT 'Pending',
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)
    
    cur.execute("""
        CREATE TABLE IF NOT EXISTS checklist_items (
            id TEXT PRIMARY KEY,
            job_id TEXT NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
            item_number INTEGER NOT NULL,
            title TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'Not Started',
            UNIQUE(job_id, item_number)
        )
    """)
    
    cur.execute("""
        CREATE TABLE IF NOT EXISTS blower_door_tests (
            id TEXT PRIMARY KEY,
            job_id TEXT NOT NULL UNIQUE REFERENCES jobs(id) ON DELETE CASCADE,
            data_points TEXT,  -- JSON array of {housePressure, fanPressure, ringConfig}
            cfm50 REAL,
            ach50 REAL,
            n_factor REAL,
            r_squared REAL,
            compliance_pass INTEGER,  -- 0 or 1
            r_squared_warning INTEGER DEFAULT 0,
            calculated INTEGER DEFAULT 0
        )
    """)
    
    cur.execute("""
        CREATE TABLE IF NOT EXISTS duct_leakage_tests (
            id TEXT PRIMARY KEY,
            job_id TEXT NOT NULL UNIQUE REFERENCES jobs(id) ON DELETE CASCADE,
            test_types TEXT NOT NULL,  -- "TDL", "DLO", or "BOTH"
            tdl_ring_config TEXT,
            tdl_fan_pressure REAL,
            tdl_cfm25 REAL,
            tdl_cfm25_per_100 REAL,
            tdl_compliance_pass INTEGER,
            dlo_house_pressure REAL,
            dlo_ring_config TEXT,
            dlo_fan_pressure REAL,
            dlo_cfm25 REAL,
            dlo_cfm25_per_100 REAL,
            dlo_compliance_pass INTEGER,
            dlo_house_pressure_warning INTEGER DEFAULT 0,
            overall_compliance_pass INTEGER,
            calculated INTEGER DEFAULT 0
        )
    """)
    
    cur.execute("""
        CREATE TABLE IF NOT EXISTS photos (
            id TEXT PRIMARY KEY,
            job_id TEXT NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
            filename TEXT NOT NULL,
            filepath TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)
    
    conn.commit()
    conn.close()

init_db()

# ── Seed Data ──────────────────────────────────────────────────────
SEED_DATA_PATH = os.path.join("assets", "mvp-seed-data.json")
with open(SEED_DATA_PATH, "r") as f:
    SEED_DATA = json.load(f)

CHECKLIST_TEMPLATE = SEED_DATA["checklistTemplate"]["items"]
BLOWER_DOOR_CALIB = SEED_DATA["constants"]["blowerDoorCalibration"]
DUCT_BLASTER_CALIB = SEED_DATA["constants"]["ductBlasterCalibration"]
MIN_BLOWER_POINTS = SEED_DATA["constants"]["minBlowerDoorTestPoints"]
MIN_CORRELATION = SEED_DATA["constants"]["minCorrelationCoefficient"]

# Mapping ring config to key
RING_MAP = {
    "Open": "openRing",
    "Ring A": "ringA",
    "Ring B": "ringB",
    "Ring C": "ringC",
    "Ring D": "ringD",
}

# ── Auth ───────────────────────────────────────────────────────────
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
security = HTTPBearer()

def get_user(credentials: HTTPAuthorizationCredentials = Depends(security), conn=Depends(get_db)):
    token = credentials.credentials
    cur = conn.execute("SELECT * FROM users WHERE id = ?", (token,))
    user = cur.fetchone()
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return dict(user)

# ── Pydantic Models ────────────────────────────────────────────────
class RegisterRequest(BaseModel):
    name: str = Field(..., min_length=1)
    email: EmailStr
    password: str = Field(..., min_length=6)

class LoginRequest(BaseModel):
    email: EmailStr
    password: str

class CreateJobRequest(BaseModel):
    street: str = Field(..., min_length=1)
    city: str = Field(..., min_length=1)
    state: str = Field(..., min_length=2, max_length=2)
    zip: str = Field(..., min_length=5, max_length=10)
    builder_name: str = Field(..., min_length=1)
    scheduled_date: str  # YYYY-MM-DD
    house_volume: float = Field(..., gt=0)
    conditioned_floor_area: float = Field(..., gt=0)
    num_stories: Optional[int] = Field(None, ge=1)
    surface_area: Optional[float] = Field(None, gt=0)

class UpdateChecklistItem(BaseModel):
    status: str = Field(..., pattern="^(Passed|Failed|N/A)$")

class BlowerDoorPoint(BaseModel):
    house_pressure: float
    fan_pressure: float
    ring_config: str = Field(..., pattern="^(Open|Ring A|Ring B|Ring C|Ring D)$")

class BlowerDoorData(BaseModel):
    data_points: List[BlowerDoorPoint] = Field(..., min_length=5, max_length=7)

class DuctLeakageData(BaseModel):
    test_types: str = Field(..., pattern="^(TDL|DLO|BOTH)$")
    # TDL
    tdl_ring_config: Optional[str] = Field(None, pattern="^(Open|Ring A|Ring B|Ring C|Ring D)$")
    tdl_fan_pressure: Optional[float] = None
    # DLO
    dlo_house_pressure: Optional[float] = None
    dlo_ring_config: Optional[str] = Field(None, pattern="^(Open|Ring A|Ring B|Ring C|Ring D)$")
    dlo_fan_pressure: Optional[float] = None

# ── Helpers ────────────────────────────────────────────────────────
def check_job_completion(conn, job_id: str):
    """Check if job should be marked Completed and update status."""
    job = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
    if not job:
        return
    
    # 1. Checklist complete? (all 10 items not "Not Started")
    items = conn.execute("SELECT status FROM checklist_items WHERE job_id = ?", (job_id,)).fetchall()
    checklist_done = len(items) == 10 and all(it["status"] != "Not Started" for it in items)
    
    # 2. Blower door complete? (>=5 points + calculated)
    bd = conn.execute("SELECT * FROM blower_door_tests WHERE job_id = ?", (job_id,)).fetchone()
    blower_done = bd is not None and bd["calculated"] == 1
    
    # 3. Duct leakage complete? (at least one test calculated)
    dl = conn.execute("SELECT * FROM duct_leakage_tests WHERE job_id = ?", (job_id,)).fetchone()
    duct_done = dl is not None and dl["calculated"] == 1
    
    if checklist_done and blower_done and duct_done:
        conn.execute("UPDATE jobs SET status = 'Completed', updated_at = datetime('now') WHERE id = ?", (job_id,))
    elif job["status"] == "Pending":
        # Check if any section has data
        any_in_progress = False
        if items:
            any_in_progress = any(it["status"] != "Not Started" for it in items)
        if not any_in_progress and bd and bd["data_points"]:
            any_in_progress = True
        if not any_in_progress and dl and dl["test_types"]:
            any_in_progress = True
        if any_in_progress:
            conn.execute("UPDATE jobs SET status = 'In Progress', updated_at = datetime('now') WHERE id = ?", (job_id,))

def get_ring_key(ring_config: str) -> str:
    return RING_MAP.get(ring_config, "openRing")

def calc_cfm(calibration: dict, ring_config: str, fan_pressure: float) -> float:
    """CFM = C * (fanPressure)^n"""
    key = get_ring_key(ring_config)
    c = calibration[key]["C"]
    n = calibration[key]["n"]
    return c * (fan_pressure ** n)

# ── Routes: Auth ───────────────────────────────────────────────────
@app.post("/api/register")
def register(req: RegisterRequest, conn=Depends(get_db)):
    existing = conn.execute("SELECT id FROM users WHERE email = ?", (req.email,)).fetchone()
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")
    
    user_id = str(uuid.uuid4())
    password_hash = pwd_context.hash(req.password)
    conn.execute(
        "INSERT INTO users (id, name, email, password_hash) VALUES (?, ?, ?, ?)",
        (user_id, req.name, req.email, password_hash)
    )
    conn.commit()
    return {"id": user_id, "name": req.name, "email": req.email, "token": user_id}

@app.post("/api/login")
def login(req: LoginRequest, conn=Depends(get_db)):
    user = conn.execute("SELECT * FROM users WHERE email = ?", (req.email,)).fetchone()
    if not user or not pwd_context.verify(req.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    return {"id": user["id"], "name": user["name"], "email": user["email"], "token": user["id"]}

@app.post("/api/logout")
def logout(user=Depends(get_user)):
    # Stateless - token is user ID, no server-side session to invalidate
    return {"message": "Logged out"}

# ── Routes: Jobs ───────────────────────────────────────────────────
@app.post("/api/jobs")
def create_job(req: CreateJobRequest, conn=Depends(get_db), user=Depends(get_user)):
    job_id = str(uuid.uuid4())
    conn.execute(
        """INSERT INTO jobs (id, user_id, street, city, state, zip, builder_name, scheduled_date,
           house_volume, conditioned_floor_area, num_stories, surface_area)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (job_id, user["id"], req.street, req.city, req.state, req.zip,
         req.builder_name, req.scheduled_date, req.house_volume, req.conditioned_floor_area,
         req.num_stories, req.surface_area)
    )
    
    # Create checklist items from template
    for item in CHECKLIST_TEMPLATE:
        ci_id = str(uuid.uuid4())
        conn.execute(
            "INSERT INTO checklist_items (id, job_id, item_number, title) VALUES (?, ?, ?, ?)",
            (ci_id, job_id, item["itemNumber"], item["title"])
        )
    
    conn.commit()
    
    job = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
    return dict(job)

@app.get("/api/jobs")
def list_jobs(conn=Depends(get_db), user=Depends(get_user)):
    jobs = conn.execute(
        "SELECT id, street, city, state, zip, builder_name, scheduled_date, status, created_at FROM jobs WHERE user_id = ? ORDER BY created_at DESC",
        (user["id"],)
    ).fetchall()
    return [dict(j) for j in jobs]

@app.get("/api/jobs/{job_id}")
def get_job_details(job_id: str, conn=Depends(get_db), user=Depends(get_user)):
    job = conn.execute("SELECT * FROM jobs WHERE id = ? AND user_id = ?", (job_id, user["id"])).fetchone()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    result = dict(job)
    
    # Checklist
    items = conn.execute("SELECT * FROM checklist_items WHERE job_id = ? ORDER BY item_number", (job_id,)).fetchall()
    checklist_data = [dict(it) for it in items]
    
    # Checklist summary
    applicable = sum(1 for it in checklist_data if it["status"] != "N/A")
    passed = sum(1 for it in checklist_data if it["status"] == "Passed")
    if applicable == 0:
        pass_rate = 0
    else:
        # Round to nearest whole number (0.5 rounds up)
        pass_rate = int(np.round(passed / applicable * 100))
    summary = f"{passed}/{applicable} Passed ({pass_rate}%)"
    
    result["checklist"] = {
        "items": checklist_data,
        "summary": summary
    }
    
    # Blower Door Test
    bd = conn.execute("SELECT * FROM blower_door_tests WHERE job_id = ?", (job_id,)).fetchone()
    if bd:
        bd_dict = dict(bd)
        if bd_dict["data_points"]:
            bd_dict["data_points"] = json.loads(bd_dict["data_points"])
        result["blower_door"] = bd_dict
    else:
        result["blower_door"] = None
    
    # Duct Leakage Test
    dl = conn.execute("SELECT * FROM duct_leakage_tests WHERE job_id = ?", (job_id,)).fetchone()
    if dl:
        result["duct_leakage"] = dict(dl)
    else:
        result["duct_leakage"] = None
    
    # Photos
    photos = conn.execute("SELECT id, filename, created_at FROM photos WHERE job_id = ?", (job_id,)).fetchall()
    result["photos"] = [dict(p) for p in photos]
    
    return result

# ── Routes: Checklist ──────────────────────────────────────────────
@app.put("/api/jobs/{job_id}/checklist/{item_number}")
def update_checklist_item(job_id: str, item_number: int, req: UpdateChecklistItem,
                           conn=Depends(get_db), user=Depends(get_user)):
    job = conn.execute("SELECT * FROM jobs WHERE id = ? AND user_id = ?", (job_id, user["id"])).fetchone()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    item = conn.execute(
        "SELECT * FROM checklist_items WHERE job_id = ? AND item_number = ?",
        (job_id, item_number)
    ).fetchone()
    if not item:
        raise HTTPException(status_code=404, detail="Checklist item not found")
    
    conn.execute(
        "UPDATE checklist_items SET status = ? WHERE id = ?",
        (req.status, item["id"])
    )
    conn.commit()
    
    check_job_completion(conn, job_id)
    
    return {"item_number": item_number, "status": req.status}

# ── Routes: Blower Door ────────────────────────────────────────────
@app.post("/api/jobs/{job_id}/blower-door")
def save_blower_door_data(job_id: str, req: BlowerDoorData,
                           conn=Depends(get_db), user=Depends(get_user)):
    job = conn.execute("SELECT * FROM jobs WHERE id = ? AND user_id = ?", (job_id, user["id"])).fetchone()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    data_points_json = json.dumps([dp.model_dump() for dp in req.data_points])
    
    existing = conn.execute("SELECT id FROM blower_door_tests WHERE job_id = ?", (job_id,)).fetchone()
    if existing:
        conn.execute(
            "UPDATE blower_door_tests SET data_points = ?, calculated = 0 WHERE job_id = ?",
            (data_points_json, job_id)
        )
    else:
        conn.execute(
            "INSERT INTO blower_door_tests (id, job_id, data_points) VALUES (?, ?, ?)",
            (str(uuid.uuid4()), job_id, data_points_json)
        )
    conn.commit()
    
    check_job_completion(conn, job_id)
    
    return {"message": "Blower door data saved", "points_count": len(req.data_points)}

@app.post("/api/jobs/{job_id}/blower-door/calculate")
def calculate_blower_door(job_id: str, conn=Depends(get_db), user=Depends(get_user)):
    job = conn.execute("SELECT * FROM jobs WHERE id = ? AND user_id = ?", (job_id, user["id"])).fetchone()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    bd = conn.execute("SELECT * FROM blower_door_tests WHERE job_id = ?", (job_id,)).fetchone()
    if not bd or not bd["data_points"]:
        raise HTTPException(status_code=400, detail="No blower door data saved")
    
    points = json.loads(bd["data_points"])
    if len(points) < 5:
        raise HTTPException(status_code=400, detail="Need at least 5 data points")
    
    # Calculate CFM for each point
    house_pressures = []
    cfm_values = []
    for p in points:
        hp = p["house_pressure"]
        fp = p["fan_pressure"]
        rc = p["ring_config"]
        cfm = calc_cfm(BLOWER_DOOR_CALIB, rc, fp)
        house_pressures.append(hp)
        cfm_values.append(cfm)
    
    # Log-log regression: log(CFM) = log(C) + n * log(house_pressure)
    # Actually: CFM = C * P^n  => log(CFM) = log(C) + n * log(P)
    log_p = np.log(house_pressures)
    log_q = np.log(cfm_values)
    
    # Simple linear regression using numpy
    n = len(log_p)
    x_mean = np.mean(log_p)
    y_mean = np.mean(log_q)
    slope = np.sum((log_p - x_mean) * (log_q - y_mean)) / np.sum((log_p - x_mean) ** 2)
    intercept = y_mean - slope * x_mean
    y_pred = slope * log_p + intercept
    ss_res = np.sum((log_q - y_pred) ** 2)
    ss_tot = np.sum((log_q - y_mean) ** 2)
    r_squared = 1 - (ss_res / ss_tot) if ss_tot != 0 else 0
    n_factor = slope
    log_cfm50 = intercept + n_factor * np.log(50)
    cfm50 = np.exp(log_cfm50)
    # r_squared computed above
    
    ach50 = (cfm50 * 60) / job["house_volume"]
    compliance = bool(ach50 <= 3.0)
    r_sq_warning = 1 if r_squared < MIN_CORRELATION else 0
    
    conn.execute(
        """UPDATE blower_door_tests SET 
           cfm50 = ?, ach50 = ?, n_factor = ?, r_squared = ?,
           compliance_pass = ?, r_squared_warning = ?, calculated = 1
           WHERE job_id = ?""",
        (cfm50, ach50, n_factor, r_squared, int(compliance), r_sq_warning, job_id)
    )
    conn.commit()
    
    check_job_completion(conn, job_id)
    
    result = {
        "cfm50": round(cfm50, 2),
        "ach50": round(ach50, 2),
        "n_factor": round(n_factor, 4),
        "r_squared": round(r_squared, 4),
        "compliance_pass": compliance,
    }
    if r_sq_warning:
        result["warning"] = "R² is below 0.98; correlation is low. Consider retaking measurements."
    
    return result

# ── Routes: Duct Leakage ──────────────────────────────────────────
@app.post("/api/jobs/{job_id}/duct-leakage")
def save_duct_leakage_data(job_id: str, req: DuctLeakageData,
                            conn=Depends(get_db), user=Depends(get_user)):
    job = conn.execute("SELECT * FROM jobs WHERE id = ? AND user_id = ?", (job_id, user["id"])).fetchone()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    # Validate required fields based on test_types
    if req.test_types in ("TDL", "BOTH"):
        if not req.tdl_ring_config or req.tdl_fan_pressure is None:
            raise HTTPException(status_code=400, detail="TDL ring config and fan pressure required")
    if req.test_types in ("DLO", "BOTH"):
        if req.dlo_house_pressure is None or not req.dlo_ring_config or req.dlo_fan_pressure is None:
            raise HTTPException(status_code=400, detail="DLO house pressure, ring config, and fan pressure required")
    
    existing = conn.execute("SELECT id FROM duct_leakage_tests WHERE job_id = ?", (job_id,)).fetchone()
    if existing:
        conn.execute(
            """UPDATE duct_leakage_tests SET 
               test_types = ?, tdl_ring_config = ?, tdl_fan_pressure = ?,
               dlo_house_pressure = ?, dlo_ring_config = ?, dlo_fan_pressure = ?,
               calculated = 0
               WHERE job_id = ?""",
            (req.test_types, req.tdl_ring_config, req.tdl_fan_pressure,
             req.dlo_house_pressure, req.dlo_ring_config, req.dlo_fan_pressure, job_id)
        )
    else:
        conn.execute(
            """INSERT INTO duct_leakage_tests 
               (id, job_id, test_types, tdl_ring_config, tdl_fan_pressure,
                dlo_house_pressure, dlo_ring_config, dlo_fan_pressure)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (str(uuid.uuid4()), job_id, req.test_types, req.tdl_ring_config, req.tdl_fan_pressure,
             req.dlo_house_pressure, req.dlo_ring_config, req.dlo_fan_pressure)
        )
    conn.commit()
    
    check_job_completion(conn, job_id)
    
    return {"message": "Duct leakage data saved", "test_types": req.test_types}

@app.post("/api/jobs/{job_id}/duct-leakage/calculate")
def calculate_duct_leakage(job_id: str, conn=Depends(get_db), user=Depends(get_user)):
    job = conn.execute("SELECT * FROM jobs WHERE id = ? AND user_id = ?", (job_id, user["id"])).fetchone()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    dl = conn.execute("SELECT * FROM duct_leakage_tests WHERE job_id = ?", (job_id,)).fetchone()
    if not dl:
        raise HTTPException(status_code=400, detail="No duct leakage data saved")
    
    conditioned_area = job["conditioned_floor_area"]
    result = {"test_types": dl["test_types"]}
    warnings = []
    overall_pass = True
    
    tdl_pass = None
    dlo_pass = None
    
    if dl["test_types"] in ("TDL", "BOTH"):
        tdl_ring = dl["tdl_ring_config"]
        tdl_fp = dl["tdl_fan_pressure"]
        tdl_cfm25 = calc_cfm(DUCT_BLASTER_CALIB, tdl_ring, tdl_fp)
        tdl_per_100 = (tdl_cfm25 * 100) / conditioned_area
        tdl_pass = bool(tdl_per_100 <= 4.0)
        
        conn.execute(
            """UPDATE duct_leakage_tests SET
               tdl_cfm25 = ?, tdl_cfm25_per_100 = ?, tdl_compliance_pass = ?
               WHERE job_id = ?""",
            (tdl_cfm25, tdl_per_100, int(tdl_pass), job_id)
        )
        
        result["tdl"] = {
            "cfm25": round(tdl_cfm25, 2),
            "cfm25_per_100_sqft": round(tdl_per_100, 2),
            "compliance_pass": tdl_pass
        }
        if not tdl_pass:
            overall_pass = False
    
    if dl["test_types"] in ("DLO", "BOTH"):
        dlo_ring = dl["dlo_ring_config"]
        dlo_fp = dl["dlo_fan_pressure"]
        dlo_hp = dl["dlo_house_pressure"]
        dlo_cfm25 = calc_cfm(DUCT_BLASTER_CALIB, dlo_ring, dlo_fp)
        dlo_per_100 = (dlo_cfm25 * 100) / conditioned_area
        dlo_pass = bool(dlo_per_100 <= 3.0)
        
        hp_warning = 0
        if dlo_hp < -27 or dlo_hp > -23:
            hp_warning = 1
            warnings.append(f"House pressure {dlo_hp} Pa is outside the recommended range of -23 to -27 Pa.")
        
        conn.execute(
            """UPDATE duct_leakage_tests SET
               dlo_cfm25 = ?, dlo_cfm25_per_100 = ?, dlo_compliance_pass = ?,
               dlo_house_pressure_warning = ?
               WHERE job_id = ?""",
            (dlo_cfm25, dlo_per_100, int(dlo_pass), hp_warning, job_id)
        )
        
        result["dlo"] = {
            "cfm25": round(dlo_cfm25, 2),
            "cfm25_per_100_sqft": round(dlo_per_100, 2),
            "compliance_pass": dlo_pass
        }
        if hp_warning:
            result["dlo"]["warning"] = warnings[-1]
        if not dlo_pass:
            overall_pass = False
    
    # Overall
    conn.execute(
        "UPDATE duct_leakage_tests SET overall_compliance_pass = ?, calculated = 1 WHERE job_id = ?",
        (int(overall_pass), job_id)
    )
    conn.commit()
    
    result["overall_compliance_pass"] = overall_pass
    if warnings:
        result["warnings"] = warnings
    
    check_job_completion(conn, job_id)
    
    return result

# ── Routes: Photos ─────────────────────────────────────────────────
PHOTOS_DIR = "photos"
os.makedirs(PHOTOS_DIR, exist_ok=True)

ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}

@app.post("/api/jobs/{job_id}/photos")
async def upload_photo(job_id: str, file: UploadFile = File(...),
                        conn=Depends(get_db), user=Depends(get_user)):
    job = conn.execute("SELECT * FROM jobs WHERE id = ? AND user_id = ?", (job_id, user["id"])).fetchone()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    # Check count
    count = conn.execute("SELECT COUNT(*) as cnt FROM photos WHERE job_id = ?", (job_id,)).fetchone()["cnt"]
    if count >= 10:
        raise HTTPException(status_code=400, detail="Maximum 10 photos per job")
    
    # Validate extension
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail="Only JPEG, PNG, and WebP files are allowed")
    
    photo_id = str(uuid.uuid4())
    filename = f"{photo_id}{ext}"
    filepath = os.path.join(PHOTOS_DIR, filename)
    
    content = await file.read()
    with open(filepath, "wb") as f:
        f.write(content)
    
    conn.execute(
        "INSERT INTO photos (id, job_id, filename, filepath) VALUES (?, ?, ?, ?)",
        (photo_id, job_id, file.filename, filepath)
    )
    conn.commit()
    
    return {"id": photo_id, "filename": file.filename}

@app.get("/api/jobs/{job_id}/photos/{photo_id}")
def get_photo(job_id: str, photo_id: str, conn=Depends(get_db), user=Depends(get_user)):
    job = conn.execute("SELECT * FROM jobs WHERE id = ? AND user_id = ?", (job_id, user["id"])).fetchone()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    photo = conn.execute("SELECT * FROM photos WHERE id = ? AND job_id = ?", (photo_id, job_id)).fetchone()
    if not photo:
        raise HTTPException(status_code=404, detail="Photo not found")
    
    return FileResponse(photo["filepath"], filename=photo["filename"])

@app.delete("/api/jobs/{job_id}/photos/{photo_id}")
def delete_photo(job_id: str, photo_id: str, conn=Depends(get_db), user=Depends(get_user)):
    job = conn.execute("SELECT * FROM jobs WHERE id = ? AND user_id = ?", (job_id, user["id"])).fetchone()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    photo = conn.execute("SELECT * FROM photos WHERE id = ? AND job_id = ?", (photo_id, job_id)).fetchone()
    if not photo:
        raise HTTPException(status_code=404, detail="Photo not found")
    
    # Delete file
    if os.path.exists(photo["filepath"]):
        os.remove(photo["filepath"])
    
    conn.execute("DELETE FROM photos WHERE id = ?", (photo_id,))
    conn.commit()
    
    return {"message": "Photo deleted"}

# ── Main ───────────────────────────────────────────────────────────
if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
