from flask import Flask, request, jsonify, g
import sqlite3
import os
import secrets
import hashlib
from datetime import datetime, timedelta, date
from functools import wraps

DB_PATH = os.environ.get("SRM_DB", "srm.db")

app = Flask(__name__)


def get_db():
    db = getattr(g, "_db", None)
    if db is None:
        db = g._db = sqlite3.connect(DB_PATH)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys = ON")
    return db


@app.teardown_appcontext
def close_db(exc):
    db = getattr(g, "_db", None)
    if db is not None:
        db.close()


def hash_pw(pw):
    return hashlib.sha256(pw.encode()).hexdigest()


def now_iso():
    return datetime.utcnow().isoformat()


def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.executescript(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL,
            active INTEGER NOT NULL DEFAULT 1,
            full_name TEXT,
            email TEXT
        );
        CREATE TABLE IF NOT EXISTS tokens (
            token TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(id)
        );
        CREATE TABLE IF NOT EXISTS categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL
        );
        CREATE TABLE IF NOT EXISTS stages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            color TEXT,
            position INTEGER NOT NULL,
            is_default INTEGER NOT NULL DEFAULT 0,
            is_seed INTEGER NOT NULL DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS suppliers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            company_name TEXT NOT NULL,
            tax_id TEXT UNIQUE NOT NULL,
            email TEXT UNIQUE NOT NULL,
            phone TEXT,
            active INTEGER NOT NULL DEFAULT 1,
            punctuality INTEGER,
            quality INTEGER,
            reliability INTEGER,
            score INTEGER
        );
        CREATE TABLE IF NOT EXISTS supplier_categories (
            supplier_id INTEGER NOT NULL,
            category_id INTEGER NOT NULL,
            PRIMARY KEY(supplier_id, category_id),
            FOREIGN KEY(supplier_id) REFERENCES suppliers(id) ON DELETE CASCADE,
            FOREIGN KEY(category_id) REFERENCES categories(id)
        );
        CREATE TABLE IF NOT EXISTS purchase_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            category_id INTEGER,
            priority TEXT NOT NULL,
            deadline TEXT,
            notes TEXT,
            stage_id INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            created_by INTEGER,
            FOREIGN KEY(category_id) REFERENCES categories(id),
            FOREIGN KEY(stage_id) REFERENCES stages(id)
        );
        CREATE TABLE IF NOT EXISTS pr_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pr_id INTEGER NOT NULL,
            description TEXT NOT NULL,
            quantity INTEGER NOT NULL,
            unit TEXT,
            FOREIGN KEY(pr_id) REFERENCES purchase_requests(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS stage_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pr_id INTEGER NOT NULL,
            from_stage_id INTEGER,
            to_stage_id INTEGER NOT NULL,
            moved_at TEXT NOT NULL,
            automatic INTEGER NOT NULL DEFAULT 0,
            FOREIGN KEY(pr_id) REFERENCES purchase_requests(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS rfqs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pr_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            description TEXT,
            deadline TEXT NOT NULL,
            status TEXT NOT NULL,
            created_at TEXT NOT NULL,
            winner_supplier_id INTEGER,
            winner_justification TEXT,
            FOREIGN KEY(pr_id) REFERENCES purchase_requests(id)
        );
        CREATE TABLE IF NOT EXISTS rfq_suppliers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            rfq_id INTEGER NOT NULL,
            supplier_id INTEGER NOT NULL,
            token TEXT UNIQUE NOT NULL,
            FOREIGN KEY(rfq_id) REFERENCES rfqs(id) ON DELETE CASCADE,
            FOREIGN KEY(supplier_id) REFERENCES suppliers(id)
        );
        CREATE TABLE IF NOT EXISTS quotes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            rfq_id INTEGER NOT NULL,
            supplier_id INTEGER NOT NULL,
            delivery_days INTEGER NOT NULL,
            payment_terms TEXT NOT NULL,
            notes TEXT,
            revision INTEGER NOT NULL DEFAULT 1,
            submitted_at TEXT NOT NULL,
            reference TEXT NOT NULL,
            total REAL NOT NULL,
            UNIQUE(rfq_id, supplier_id),
            FOREIGN KEY(rfq_id) REFERENCES rfqs(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS quote_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            quote_id INTEGER NOT NULL,
            pr_item_id INTEGER NOT NULL,
            unit_price REAL NOT NULL,
            FOREIGN KEY(quote_id) REFERENCES quotes(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_number TEXT UNIQUE NOT NULL,
            rfq_id INTEGER NOT NULL,
            supplier_id INTEGER NOT NULL,
            total REAL NOT NULL,
            payment_terms TEXT NOT NULL,
            expected_delivery TEXT NOT NULL,
            created_at TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'Pending',
            FOREIGN KEY(rfq_id) REFERENCES rfqs(id),
            FOREIGN KEY(supplier_id) REFERENCES suppliers(id)
        );
        CREATE TABLE IF NOT EXISTS order_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id INTEGER NOT NULL,
            description TEXT NOT NULL,
            quantity INTEGER NOT NULL,
            unit_price REAL NOT NULL,
            FOREIGN KEY(order_id) REFERENCES orders(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS order_status_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id INTEGER NOT NULL,
            status TEXT NOT NULL,
            changed_at TEXT NOT NULL,
            FOREIGN KEY(order_id) REFERENCES orders(id) ON DELETE CASCADE
        );
        """
    )
    # seed
    cur = c.execute("SELECT COUNT(*) FROM users")
    if cur.fetchone()[0] == 0:
        c.execute(
            "INSERT INTO users(username,password_hash,role,active) VALUES(?,?,?,1)",
            ("admin", hash_pw("admin123"), "admin"),
        )
    cur = c.execute("SELECT COUNT(*) FROM categories")
    if cur.fetchone()[0] == 0:
        for n in ["Raw Materials", "Office Supplies", "Equipment", "Services", "Other"]:
            c.execute("INSERT INTO categories(name) VALUES(?)", (n,))
    cur = c.execute("SELECT COUNT(*) FROM stages")
    if cur.fetchone()[0] == 0:
        stages = [("New", "#888888", 0, 1, 1), ("In Review", "#f59e0b", 1, 0, 1),
                  ("Approved", "#10b981", 2, 0, 1), ("Ordered", "#3b82f6", 3, 0, 1)]
        for s in stages:
            c.execute("INSERT INTO stages(name,color,position,is_default,is_seed) VALUES(?,?,?,?,?)", s)
    conn.commit()
    conn.close()


def err(msg, code=400):
    return jsonify({"error": msg}), code


def get_user_from_token():
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return None
    tok = auth[7:]
    db = get_db()
    row = db.execute(
        "SELECT u.* FROM tokens t JOIN users u ON t.user_id=u.id WHERE t.token=?",
        (tok,),
    ).fetchone()
    if row and row["active"]:
        return row
    return None


def require_auth(roles=None):
    def deco(f):
        @wraps(f)
        def w(*a, **kw):
            u = get_user_from_token()
            if not u:
                return err("Unauthorized", 401)
            if roles and u["role"] not in roles:
                return err("Forbidden", 403)
            g.user = u
            return f(*a, **kw)
        return w
    return deco


# ---------- AUTH ----------
@app.post("/api/auth/login")
def login():
    data = request.get_json() or {}
    u = data.get("username")
    p = data.get("password")
    db = get_db()
    row = db.execute("SELECT * FROM users WHERE username=?", (u,)).fetchone()
    if not row or row["password_hash"] != hash_pw(p or ""):
        return err("Invalid credentials", 401)
    if not row["active"]:
        return err("Account inactive", 403)
    tok = secrets.token_hex(24)
    db.execute("INSERT INTO tokens(token,user_id,created_at) VALUES(?,?,?)", (tok, row["id"], now_iso()))
    db.commit()
    return jsonify({"token": tok, "user": {"id": row["id"], "username": row["username"], "role": row["role"]}})


@app.post("/api/auth/logout")
@require_auth()
def logout():
    auth = request.headers.get("Authorization", "")[7:]
    db = get_db()
    db.execute("DELETE FROM tokens WHERE token=?", (auth,))
    db.commit()
    return jsonify({"ok": True})


# ---------- USERS (admin only) ----------
def user_dict(r):
    return {"id": r["id"], "username": r["username"], "role": r["role"], "active": bool(r["active"]),
            "full_name": r["full_name"], "email": r["email"]}


@app.get("/api/users")
@require_auth(["admin"])
def list_users():
    db = get_db()
    rows = db.execute("SELECT * FROM users ORDER BY id").fetchall()
    return jsonify([user_dict(r) for r in rows])


@app.post("/api/users")
@require_auth(["admin"])
def create_user():
    d = request.get_json() or {}
    if not d.get("username") or not d.get("password") or not d.get("role"):
        return err("Missing fields")
    if d["role"] not in ("admin", "buyer"):
        return err("Invalid role")
    db = get_db()
    if db.execute("SELECT 1 FROM users WHERE username=?", (d["username"],)).fetchone():
        return err("Username exists")
    cur = db.execute(
        "INSERT INTO users(username,password_hash,role,active,full_name,email) VALUES(?,?,?,?,?,?)",
        (d["username"], hash_pw(d["password"]), d["role"], 1 if d.get("active", True) else 0,
         d.get("full_name"), d.get("email")),
    )
    db.commit()
    return jsonify(user_dict(db.execute("SELECT * FROM users WHERE id=?", (cur.lastrowid,)).fetchone())), 201


@app.put("/api/users/<int:uid>")
@require_auth(["admin"])
def edit_user(uid):
    d = request.get_json() or {}
    db = get_db()
    row = db.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
    if not row:
        return err("Not found", 404)
    # username immutable
    if "username" in d and d["username"] != row["username"]:
        return err("Username is immutable")
    fields = []
    vals = []
    if "password" in d and d["password"]:
        fields.append("password_hash=?"); vals.append(hash_pw(d["password"]))
    if "role" in d:
        if d["role"] not in ("admin", "buyer"):
            return err("Invalid role")
        fields.append("role=?"); vals.append(d["role"])
    if "full_name" in d:
        fields.append("full_name=?"); vals.append(d["full_name"])
    if "email" in d:
        fields.append("email=?"); vals.append(d["email"])
    if fields:
        vals.append(uid)
        db.execute(f"UPDATE users SET {','.join(fields)} WHERE id=?", vals)
        db.commit()
    return jsonify(user_dict(db.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()))


@app.post("/api/users/<int:uid>/toggle")
@require_auth(["admin"])
def toggle_user(uid):
    db = get_db()
    row = db.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
    if not row:
        return err("Not found", 404)
    if uid == g.user["id"]:
        return err("Cannot deactivate your own account")
    new_active = 0 if row["active"] else 1
    db.execute("UPDATE users SET active=? WHERE id=?", (new_active, uid))
    if not new_active:
        db.execute("DELETE FROM tokens WHERE user_id=?", (uid,))
    db.commit()
    return jsonify(user_dict(db.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()))


# ---------- CATEGORIES ----------
@app.get("/api/categories")
@require_auth()
def list_categories():
    db = get_db()
    rows = db.execute("SELECT * FROM categories ORDER BY id").fetchall()
    return jsonify([{"id": r["id"], "name": r["name"]} for r in rows])


@app.post("/api/categories")
@require_auth(["admin"])
def create_category():
    d = request.get_json() or {}
    if not d.get("name"):
        return err("Name required")
    db = get_db()
    if db.execute("SELECT 1 FROM categories WHERE name=?", (d["name"],)).fetchone():
        return err("Exists")
    cur = db.execute("INSERT INTO categories(name) VALUES(?)", (d["name"],))
    db.commit()
    return jsonify({"id": cur.lastrowid, "name": d["name"]}), 201


@app.put("/api/categories/<int:cid>")
@require_auth(["admin"])
def edit_category(cid):
    d = request.get_json() or {}
    db = get_db()
    if not db.execute("SELECT 1 FROM categories WHERE id=?", (cid,)).fetchone():
        return err("Not found", 404)
    if "name" in d:
        db.execute("UPDATE categories SET name=? WHERE id=?", (d["name"], cid))
        db.commit()
    return jsonify({"id": cid, "name": d.get("name")})


@app.delete("/api/categories/<int:cid>")
@require_auth(["admin"])
def del_category(cid):
    db = get_db()
    if db.execute("SELECT 1 FROM purchase_requests WHERE category_id=?", (cid,)).fetchone():
        return err("Category in use by purchase request")
    if db.execute("SELECT 1 FROM supplier_categories WHERE category_id=?", (cid,)).fetchone():
        return err("Category in use by supplier")
    db.execute("DELETE FROM categories WHERE id=?", (cid,))
    db.commit()
    return jsonify({"ok": True})


# ---------- STAGES ----------
@app.get("/api/stages")
@require_auth()
def list_stages():
    db = get_db()
    rows = db.execute("SELECT * FROM stages ORDER BY position").fetchall()
    return jsonify([{"id": r["id"], "name": r["name"], "color": r["color"], "position": r["position"],
                     "is_default": bool(r["is_default"]), "is_seed": bool(r["is_seed"])} for r in rows])


@app.post("/api/stages")
@require_auth(["admin"])
def create_stage():
    d = request.get_json() or {}
    if not d.get("name"):
        return err("Name required")
    db = get_db()
    if db.execute("SELECT 1 FROM stages WHERE name=?", (d["name"],)).fetchone():
        return err("Exists")
    pos = db.execute("SELECT COALESCE(MAX(position),-1)+1 FROM stages").fetchone()[0]
    cur = db.execute("INSERT INTO stages(name,color,position) VALUES(?,?,?)", (d["name"], d.get("color"), pos))
    db.commit()
    return jsonify({"id": cur.lastrowid, "name": d["name"], "color": d.get("color"), "position": pos}), 201


@app.put("/api/stages/<int:sid>")
@require_auth(["admin"])
def edit_stage(sid):
    d = request.get_json() or {}
    db = get_db()
    row = db.execute("SELECT * FROM stages WHERE id=?", (sid,)).fetchone()
    if not row:
        return err("Not found", 404)
    if row["is_seed"] and "name" in d and d["name"] != row["name"]:
        return err("Cannot rename seed stage")
    fields = []; vals = []
    if "name" in d:
        fields.append("name=?"); vals.append(d["name"])
    if "color" in d:
        fields.append("color=?"); vals.append(d["color"])
    if fields:
        vals.append(sid)
        db.execute(f"UPDATE stages SET {','.join(fields)} WHERE id=?", vals)
        db.commit()
    return jsonify({"ok": True})


@app.post("/api/stages/reorder")
@require_auth(["admin"])
def reorder_stages():
    d = request.get_json() or {}
    order = d.get("order")
    if not isinstance(order, list):
        return err("order list required")
    db = get_db()
    for i, sid in enumerate(order):
        db.execute("UPDATE stages SET position=? WHERE id=?", (i, sid))
    db.commit()
    return jsonify({"ok": True})


@app.delete("/api/stages/<int:sid>")
@require_auth(["admin"])
def del_stage(sid):
    db = get_db()
    row = db.execute("SELECT * FROM stages WHERE id=?", (sid,)).fetchone()
    if not row:
        return err("Not found", 404)
    if row["is_seed"]:
        return err("Cannot delete seed stage")
    if db.execute("SELECT 1 FROM purchase_requests WHERE stage_id=?", (sid,)).fetchone():
        return err("Stage contains requests")
    db.execute("DELETE FROM stages WHERE id=?", (sid,))
    db.commit()
    return jsonify({"ok": True})


# ---------- SUPPLIERS ----------
def supplier_dict(db, r):
    cats = db.execute(
        "SELECT c.id,c.name FROM supplier_categories sc JOIN categories c ON sc.category_id=c.id WHERE sc.supplier_id=?",
        (r["id"],),
    ).fetchall()
    return {
        "id": r["id"], "company_name": r["company_name"], "tax_id": r["tax_id"],
        "email": r["email"], "phone": r["phone"], "active": bool(r["active"]),
        "punctuality": r["punctuality"], "quality": r["quality"], "reliability": r["reliability"],
        "score": r["score"], "categories": [{"id": c["id"], "name": c["name"]} for c in cats],
    }


def compute_score(p, q, rl):
    if p is None or q is None or rl is None:
        return None
    return round(p * 0.35 + q * 0.35 + rl * 0.30)


@app.get("/api/suppliers")
@require_auth()
def list_suppliers():
    db = get_db()
    q = request.args
    sql = "SELECT DISTINCT s.* FROM suppliers s"
    conds = []; params = []
    if q.get("category"):
        sql += " JOIN supplier_categories sc ON sc.supplier_id=s.id"
        conds.append("sc.category_id=?"); params.append(int(q["category"]))
    if q.get("status") in ("active", "inactive"):
        conds.append("s.active=?"); params.append(1 if q["status"] == "active" else 0)
    if q.get("search"):
        conds.append("(s.company_name LIKE ? OR s.email LIKE ?)")
        params += [f"%{q['search']}%", f"%{q['search']}%"]
    if conds:
        sql += " WHERE " + " AND ".join(conds)
    sort = q.get("sort", "name")
    if sort == "score":
        sql += " ORDER BY COALESCE(s.score,-1) DESC"
    else:
        sql += " ORDER BY s.company_name"
    rows = db.execute(sql, params).fetchall()
    return jsonify([supplier_dict(db, r) for r in rows])


@app.get("/api/suppliers/<int:sid>")
@require_auth()
def get_supplier(sid):
    db = get_db()
    r = db.execute("SELECT * FROM suppliers WHERE id=?", (sid,)).fetchone()
    if not r:
        return err("Not found", 404)
    return jsonify(supplier_dict(db, r))


@app.post("/api/suppliers")
@require_auth()
def create_supplier():
    d = request.get_json() or {}
    for f in ("company_name", "tax_id", "email"):
        if not d.get(f):
            return err(f"{f} required")
    cats = d.get("categories") or []
    if not cats:
        return err("At least one category required")
    db = get_db()
    if db.execute("SELECT 1 FROM suppliers WHERE tax_id=?", (d["tax_id"],)).fetchone():
        return err("tax_id must be unique")
    if db.execute("SELECT 1 FROM suppliers WHERE email=?", (d["email"],)).fetchone():
        return err("email must be unique")
    cur = db.execute(
        "INSERT INTO suppliers(company_name,tax_id,email,phone,active) VALUES(?,?,?,?,1)",
        (d["company_name"], d["tax_id"], d["email"], d.get("phone")),
    )
    sid = cur.lastrowid
    for cid in cats:
        db.execute("INSERT INTO supplier_categories(supplier_id,category_id) VALUES(?,?)", (sid, cid))
    db.commit()
    return jsonify(supplier_dict(db, db.execute("SELECT * FROM suppliers WHERE id=?", (sid,)).fetchone())), 201


@app.put("/api/suppliers/<int:sid>")
@require_auth()
def edit_supplier(sid):
    d = request.get_json() or {}
    db = get_db()
    r = db.execute("SELECT * FROM suppliers WHERE id=?", (sid,)).fetchone()
    if not r:
        return err("Not found", 404)
    fields = []; vals = []
    for f in ("company_name", "phone"):
        if f in d:
            fields.append(f"{f}=?"); vals.append(d[f])
    if "tax_id" in d and d["tax_id"] != r["tax_id"]:
        if db.execute("SELECT 1 FROM suppliers WHERE tax_id=? AND id<>?", (d["tax_id"], sid)).fetchone():
            return err("tax_id must be unique")
        fields.append("tax_id=?"); vals.append(d["tax_id"])
    if "email" in d and d["email"] != r["email"]:
        if db.execute("SELECT 1 FROM suppliers WHERE email=? AND id<>?", (d["email"], sid)).fetchone():
            return err("email must be unique")
        fields.append("email=?"); vals.append(d["email"])
    if fields:
        vals.append(sid)
        db.execute(f"UPDATE suppliers SET {','.join(fields)} WHERE id=?", vals)
    if "categories" in d:
        if not d["categories"]:
            return err("At least one category required")
        db.execute("DELETE FROM supplier_categories WHERE supplier_id=?", (sid,))
        for cid in d["categories"]:
            db.execute("INSERT INTO supplier_categories(supplier_id,category_id) VALUES(?,?)", (sid, cid))
    db.commit()
    return jsonify(supplier_dict(db, db.execute("SELECT * FROM suppliers WHERE id=?", (sid,)).fetchone()))


@app.post("/api/suppliers/<int:sid>/toggle")
@require_auth()
def toggle_supplier(sid):
    db = get_db()
    r = db.execute("SELECT * FROM suppliers WHERE id=?", (sid,)).fetchone()
    if not r:
        return err("Not found", 404)
    if r["active"]:
        # cannot deactivate if invited to active RFQ (awaiting quotes)
        row = db.execute(
            """SELECT 1 FROM rfq_suppliers rs JOIN rfqs r ON rs.rfq_id=r.id
               WHERE rs.supplier_id=? AND r.status IN ('Awaiting Quotes','Overdue')""",
            (sid,),
        ).fetchone()
        if row:
            return err("Cannot deactivate: supplier invited to active RFQ")
    db.execute("UPDATE suppliers SET active=? WHERE id=?", (0 if r["active"] else 1, sid))
    db.commit()
    return jsonify(supplier_dict(db, db.execute("SELECT * FROM suppliers WHERE id=?", (sid,)).fetchone()))


@app.delete("/api/suppliers/<int:sid>")
@require_auth()
def del_supplier(sid):
    db = get_db()
    if db.execute("SELECT 1 FROM rfq_suppliers WHERE supplier_id=?", (sid,)).fetchone():
        return err("Supplier has RFQs")
    if db.execute("SELECT 1 FROM orders WHERE supplier_id=?", (sid,)).fetchone():
        return err("Supplier has orders")
    db.execute("DELETE FROM supplier_categories WHERE supplier_id=?", (sid,))
    db.execute("DELETE FROM suppliers WHERE id=?", (sid,))
    db.commit()
    return jsonify({"ok": True})


# ---------- PURCHASE REQUESTS ----------
def pr_dict(db, r):
    items = db.execute("SELECT * FROM pr_items WHERE pr_id=?", (r["id"],)).fetchall()
    stage = db.execute("SELECT * FROM stages WHERE id=?", (r["stage_id"],)).fetchone()
    cat = db.execute("SELECT * FROM categories WHERE id=?", (r["category_id"],)).fetchone() if r["category_id"] else None
    created = datetime.fromisoformat(r["created_at"])
    age_days = (datetime.utcnow() - created).days
    return {
        "id": r["id"], "title": r["title"], "priority": r["priority"],
        "category": {"id": cat["id"], "name": cat["name"]} if cat else None,
        "deadline": r["deadline"], "notes": r["notes"],
        "stage": {"id": stage["id"], "name": stage["name"]} if stage else None,
        "created_at": r["created_at"], "age_days": age_days,
        "item_count": len(items),
        "items": [{"id": i["id"], "description": i["description"], "quantity": i["quantity"], "unit": i["unit"]} for i in items],
    }


@app.get("/api/purchase-requests")
@require_auth()
def list_prs():
    db = get_db()
    q = request.args
    sql = "SELECT DISTINCT p.* FROM purchase_requests p"
    conds = []; params = []
    if q.get("search"):
        sql += " LEFT JOIN pr_items i ON i.pr_id=p.id"
        conds.append("(p.title LIKE ? OR i.description LIKE ?)")
        params += [f"%{q['search']}%", f"%{q['search']}%"]
    if q.get("category"):
        conds.append("p.category_id=?"); params.append(int(q["category"]))
    if q.get("priority"):
        conds.append("p.priority=?"); params.append(q["priority"])
    if q.get("stage"):
        conds.append("p.stage_id=?"); params.append(int(q["stage"]))
    if conds:
        sql += " WHERE " + " AND ".join(conds)
    sql += " ORDER BY p.id DESC"
    rows = db.execute(sql, params).fetchall()
    return jsonify([pr_dict(db, r) for r in rows])


@app.get("/api/purchase-requests/<int:pid>")
@require_auth()
def get_pr(pid):
    db = get_db()
    r = db.execute("SELECT * FROM purchase_requests WHERE id=?", (pid,)).fetchone()
    if not r:
        return err("Not found", 404)
    return jsonify(pr_dict(db, r))


def default_stage(db):
    return db.execute("SELECT * FROM stages WHERE is_default=1").fetchone()


@app.post("/api/purchase-requests")
@require_auth()
def create_pr():
    d = request.get_json() or {}
    if not d.get("title"):
        return err("Title required")
    items = d.get("items") or []
    if not items:
        return err("At least one line item required")
    for it in items:
        if not it.get("description"):
            return err("Item description required")
        if int(it.get("quantity", 0)) < 1:
            return err("Item quantity must be >=1")
    priority = d.get("priority", "Medium")
    if priority not in ("Low", "Medium", "High", "Urgent"):
        return err("Invalid priority")
    db = get_db()
    stage = default_stage(db)
    cur = db.execute(
        "INSERT INTO purchase_requests(title,category_id,priority,deadline,notes,stage_id,created_at,created_by) VALUES(?,?,?,?,?,?,?,?)",
        (d["title"], d.get("category_id"), priority, d.get("deadline"), d.get("notes"),
         stage["id"], now_iso(), g.user["id"]),
    )
    pid = cur.lastrowid
    for it in items:
        db.execute("INSERT INTO pr_items(pr_id,description,quantity,unit) VALUES(?,?,?,?)",
                   (pid, it["description"], int(it["quantity"]), it.get("unit")))
    db.execute("INSERT INTO stage_history(pr_id,from_stage_id,to_stage_id,moved_at,automatic) VALUES(?,?,?,?,0)",
               (pid, None, stage["id"], now_iso()))
    db.commit()
    return jsonify(pr_dict(db, db.execute("SELECT * FROM purchase_requests WHERE id=?", (pid,)).fetchone())), 201


@app.put("/api/purchase-requests/<int:pid>")
@require_auth()
def edit_pr(pid):
    d = request.get_json() or {}
    db = get_db()
    r = db.execute("SELECT * FROM purchase_requests WHERE id=?", (pid,)).fetchone()
    if not r:
        return err("Not found", 404)
    fields = []; vals = []
    for f in ("title", "notes", "deadline"):
        if f in d:
            fields.append(f"{f}=?"); vals.append(d[f])
    if "category_id" in d:
        fields.append("category_id=?"); vals.append(d["category_id"])
    if "priority" in d:
        if d["priority"] not in ("Low", "Medium", "High", "Urgent"):
            return err("Invalid priority")
        fields.append("priority=?"); vals.append(d["priority"])
    if fields:
        vals.append(pid)
        db.execute(f"UPDATE purchase_requests SET {','.join(fields)} WHERE id=?", vals)
    if "items" in d:
        items = d["items"]
        if not items:
            return err("At least one item")
        for it in items:
            if not it.get("description") or int(it.get("quantity", 0)) < 1:
                return err("Invalid item")
        db.execute("DELETE FROM pr_items WHERE pr_id=?", (pid,))
        for it in items:
            db.execute("INSERT INTO pr_items(pr_id,description,quantity,unit) VALUES(?,?,?,?)",
                       (pid, it["description"], int(it["quantity"]), it.get("unit")))
    db.commit()
    return jsonify(pr_dict(db, db.execute("SELECT * FROM purchase_requests WHERE id=?", (pid,)).fetchone()))


@app.post("/api/purchase-requests/<int:pid>/move")
@require_auth()
def move_pr(pid):
    d = request.get_json() or {}
    sid = d.get("stage_id")
    db = get_db()
    r = db.execute("SELECT * FROM purchase_requests WHERE id=?", (pid,)).fetchone()
    if not r:
        return err("Not found", 404)
    if not db.execute("SELECT 1 FROM stages WHERE id=?", (sid,)).fetchone():
        return err("Invalid stage")
    move_pr_stage(db, pid, sid, automatic=False)
    db.commit()
    return jsonify(pr_dict(db, db.execute("SELECT * FROM purchase_requests WHERE id=?", (pid,)).fetchone()))


def move_pr_stage(db, pid, to_stage_id, automatic=False):
    r = db.execute("SELECT stage_id FROM purchase_requests WHERE id=?", (pid,)).fetchone()
    from_id = r["stage_id"]
    if from_id == to_stage_id:
        return
    db.execute("UPDATE purchase_requests SET stage_id=? WHERE id=?", (to_stage_id, pid))
    db.execute(
        "INSERT INTO stage_history(pr_id,from_stage_id,to_stage_id,moved_at,automatic) VALUES(?,?,?,?,?)",
        (pid, from_id, to_stage_id, now_iso(), 1 if automatic else 0),
    )


def stage_by_name(db, name):
    return db.execute("SELECT * FROM stages WHERE name=?", (name,)).fetchone()


@app.get("/api/purchase-requests/<int:pid>/history")
@require_auth()
def pr_history(pid):
    db = get_db()
    rows = db.execute(
        """SELECT h.*, sf.name AS from_name, st.name AS to_name
           FROM stage_history h
           LEFT JOIN stages sf ON h.from_stage_id=sf.id
           LEFT JOIN stages st ON h.to_stage_id=st.id
           WHERE h.pr_id=? ORDER BY h.id""",
        (pid,),
    ).fetchall()
    return jsonify([{"from": r["from_name"], "to": r["to_name"], "at": r["moved_at"],
                     "automatic": bool(r["automatic"])} for r in rows])


@app.delete("/api/purchase-requests/<int:pid>")
@require_auth()
def del_pr(pid):
    db = get_db()
    if db.execute("SELECT 1 FROM rfqs WHERE pr_id=?", (pid,)).fetchone():
        return err("Cannot delete PR with RFQ")
    db.execute("DELETE FROM purchase_requests WHERE id=?", (pid,))
    db.commit()
    return jsonify({"ok": True})


@app.post("/api/purchase-requests/<int:pid>/clone")
@require_auth()
def clone_pr(pid):
    db = get_db()
    r = db.execute("SELECT * FROM purchase_requests WHERE id=?", (pid,)).fetchone()
    if not r:
        return err("Not found", 404)
    stage = default_stage(db)
    cur = db.execute(
        "INSERT INTO purchase_requests(title,category_id,priority,deadline,notes,stage_id,created_at,created_by) VALUES(?,?,?,?,?,?,?,?)",
        (r["title"], r["category_id"], r["priority"], r["deadline"], r["notes"],
         stage["id"], now_iso(), g.user["id"]),
    )
    npid = cur.lastrowid
    for it in db.execute("SELECT * FROM pr_items WHERE pr_id=?", (pid,)).fetchall():
        db.execute("INSERT INTO pr_items(pr_id,description,quantity,unit) VALUES(?,?,?,?)",
                   (npid, it["description"], it["quantity"], it["unit"]))
    db.execute("INSERT INTO stage_history(pr_id,from_stage_id,to_stage_id,moved_at,automatic) VALUES(?,?,?,?,0)",
               (npid, None, stage["id"], now_iso()))
    db.commit()
    return jsonify(pr_dict(db, db.execute("SELECT * FROM purchase_requests WHERE id=?", (npid,)).fetchone())), 201


# ---------- RFQs ----------
def rfq_status_effective(db, r):
    st = r["status"]
    if st == "Awaiting Quotes":
        try:
            dl = datetime.fromisoformat(r["deadline"])
            if datetime.utcnow() > dl:
                return "Overdue"
        except Exception:
            pass
    return st


def rfq_dict(db, r, include_token=False):
    suppliers = db.execute(
        """SELECT rs.*, s.company_name FROM rfq_suppliers rs
           JOIN suppliers s ON s.id=rs.supplier_id WHERE rs.rfq_id=?""",
        (r["id"],),
    ).fetchall()
    sup_list = []
    for s in suppliers:
        d = {"id": s["id"], "supplier_id": s["supplier_id"], "company_name": s["company_name"]}
        if include_token:
            d["token"] = s["token"]
        # has quote?
        qr = db.execute("SELECT * FROM quotes WHERE rfq_id=? AND supplier_id=?", (r["id"], s["supplier_id"])).fetchone()
        d["has_quote"] = qr is not None
        if qr:
            d["revision"] = qr["revision"]
        sup_list.append(d)
    status = rfq_status_effective(db, r)
    return {
        "id": r["id"], "pr_id": r["pr_id"], "title": r["title"], "description": r["description"],
        "deadline": r["deadline"], "status": status, "created_at": r["created_at"],
        "suppliers": sup_list, "winner_supplier_id": r["winner_supplier_id"],
        "winner_justification": r["winner_justification"],
    }


@app.get("/api/rfqs")
@require_auth()
def list_rfqs():
    db = get_db()
    rows = db.execute("SELECT * FROM rfqs ORDER BY id DESC").fetchall()
    return jsonify([rfq_dict(db, r) for r in rows])


@app.get("/api/rfqs/<int:rid>")
@require_auth()
def get_rfq(rid):
    db = get_db()
    r = db.execute("SELECT * FROM rfqs WHERE id=?", (rid,)).fetchone()
    if not r:
        return err("Not found", 404)
    return jsonify(rfq_dict(db, r, include_token=True))


@app.post("/api/rfqs")
@require_auth()
def create_rfq():
    d = request.get_json() or {}
    pr_id = d.get("pr_id")
    if not pr_id or not d.get("title") or not d.get("deadline"):
        return err("pr_id, title, deadline required")
    db = get_db()
    pr = db.execute("SELECT * FROM purchase_requests WHERE id=?", (pr_id,)).fetchone()
    if not pr:
        return err("PR not found", 404)
    # Only one active RFQ
    existing = db.execute("SELECT * FROM rfqs WHERE pr_id=? AND status<>'Cancelled'", (pr_id,)).fetchone()
    if existing:
        return err("PR already has active RFQ")
    suppliers = d.get("supplier_ids")
    include_all = d.get("include_all_active", False)
    if not suppliers:
        # default: suppliers matching PR category
        if include_all:
            rows = db.execute("SELECT id FROM suppliers WHERE active=1").fetchall()
        else:
            rows = db.execute(
                """SELECT DISTINCT s.id FROM suppliers s
                   JOIN supplier_categories sc ON sc.supplier_id=s.id
                   WHERE s.active=1 AND sc.category_id=?""",
                (pr["category_id"],),
            ).fetchall()
        suppliers = [r["id"] for r in rows]
    if not suppliers:
        return err("At least one supplier required")
    # validate suppliers active
    for sid in suppliers:
        s = db.execute("SELECT * FROM suppliers WHERE id=?", (sid,)).fetchone()
        if not s or not s["active"]:
            return err(f"Supplier {sid} not active")
    cur = db.execute(
        "INSERT INTO rfqs(pr_id,title,description,deadline,status,created_at) VALUES(?,?,?,?,?,?)",
        (pr_id, d["title"], d.get("description"), d["deadline"], "Awaiting Quotes", now_iso()),
    )
    rid = cur.lastrowid
    for sid in suppliers:
        tok = secrets.token_hex(16)
        db.execute("INSERT INTO rfq_suppliers(rfq_id,supplier_id,token) VALUES(?,?,?)", (rid, sid, tok))
    # Move PR to In Review
    ir = stage_by_name(db, "In Review")
    move_pr_stage(db, pr_id, ir["id"], automatic=True)
    db.commit()
    return jsonify(rfq_dict(db, db.execute("SELECT * FROM rfqs WHERE id=?", (rid,)).fetchone(), include_token=True)), 201


@app.put("/api/rfqs/<int:rid>")
@require_auth()
def edit_rfq(rid):
    d = request.get_json() or {}
    db = get_db()
    r = db.execute("SELECT * FROM rfqs WHERE id=?", (rid,)).fetchone()
    if not r:
        return err("Not found", 404)
    status = rfq_status_effective(db, r)
    if status in ("Winner Selected", "Cancelled"):
        return err("RFQ locked")
    has_quotes = db.execute("SELECT 1 FROM quotes WHERE rfq_id=?", (rid,)).fetchone()
    if status == "Ready for Review":
        return err("Cannot edit; only winner selection or cancel")
    if status == "Overdue":
        return err("Cannot edit; only winner selection or cancel")
    if has_quotes:
        # extend deadline only
        if set(d.keys()) - {"deadline"}:
            return err("Only deadline can be extended after first quote")
        new_deadline = d.get("deadline")
        if not new_deadline or new_deadline <= r["deadline"]:
            return err("Deadline must be later than current")
        db.execute("UPDATE rfqs SET deadline=? WHERE id=?", (new_deadline, rid))
        db.commit()
        return jsonify(rfq_dict(db, db.execute("SELECT * FROM rfqs WHERE id=?", (rid,)).fetchone()))
    # No quotes yet: edit all fields
    fields = []; vals = []
    for f in ("title", "description", "deadline"):
        if f in d:
            fields.append(f"{f}=?"); vals.append(d[f])
    if fields:
        vals.append(rid)
        db.execute(f"UPDATE rfqs SET {','.join(fields)} WHERE id=?", vals)
    if "supplier_ids" in d:
        ids = d["supplier_ids"]
        if not ids:
            return err("At least one supplier")
        db.execute("DELETE FROM rfq_suppliers WHERE rfq_id=?", (rid,))
        for sid in ids:
            s = db.execute("SELECT * FROM suppliers WHERE id=?", (sid,)).fetchone()
            if not s or not s["active"]:
                return err(f"Supplier {sid} not active")
            tok = secrets.token_hex(16)
            db.execute("INSERT INTO rfq_suppliers(rfq_id,supplier_id,token) VALUES(?,?,?)", (rid, sid, tok))
    db.commit()
    return jsonify(rfq_dict(db, db.execute("SELECT * FROM rfqs WHERE id=?", (rid,)).fetchone()))


@app.post("/api/rfqs/<int:rid>/cancel")
@require_auth()
def cancel_rfq(rid):
    db = get_db()
    r = db.execute("SELECT * FROM rfqs WHERE id=?", (rid,)).fetchone()
    if not r:
        return err("Not found", 404)
    if r["status"] in ("Cancelled", "Winner Selected"):
        return err("Already finalized")
    db.execute("UPDATE rfqs SET status='Cancelled' WHERE id=?", (rid,))
    # Move PR back to New
    new_st = stage_by_name(db, "New")
    move_pr_stage(db, r["pr_id"], new_st["id"], automatic=True)
    db.commit()
    return jsonify(rfq_dict(db, db.execute("SELECT * FROM rfqs WHERE id=?", (rid,)).fetchone()))


# ---------- QUOTE SUBMISSION (no login) ----------
@app.get("/api/quote/<token>")
def quote_view(token):
    db = get_db()
    rs = db.execute("SELECT * FROM rfq_suppliers WHERE token=?", (token,)).fetchone()
    if not rs:
        return err("Invalid token", 404)
    rfq = db.execute("SELECT * FROM rfqs WHERE id=?", (rs["rfq_id"],)).fetchone()
    sup = db.execute("SELECT * FROM suppliers WHERE id=?", (rs["supplier_id"],)).fetchone()
    pr = db.execute("SELECT * FROM purchase_requests WHERE id=?", (rfq["pr_id"],)).fetchone()
    items = db.execute("SELECT * FROM pr_items WHERE pr_id=?", (pr["id"],)).fetchall()
    quote = db.execute("SELECT * FROM quotes WHERE rfq_id=? AND supplier_id=?",
                       (rfq["id"], rs["supplier_id"])).fetchone()
    quote_data = None
    if quote:
        qi = db.execute("SELECT * FROM quote_items WHERE quote_id=?", (quote["id"],)).fetchall()
        quote_data = {
            "reference": quote["reference"], "revision": quote["revision"],
            "delivery_days": quote["delivery_days"], "payment_terms": quote["payment_terms"],
            "notes": quote["notes"], "total": quote["total"],
            "items": [{"pr_item_id": q["pr_item_id"], "unit_price": q["unit_price"]} for q in qi],
        }
    return jsonify({
        "rfq": {"title": rfq["title"], "description": rfq["description"], "deadline": rfq["deadline"],
                "status": rfq_status_effective(db, rfq)},
        "supplier": {"company_name": sup["company_name"]},
        "items": [{"id": i["id"], "description": i["description"], "quantity": i["quantity"], "unit": i["unit"]} for i in items],
        "quote": quote_data,
    })


@app.post("/api/quote/<token>")
def quote_submit(token):
    d = request.get_json() or {}
    db = get_db()
    rs = db.execute("SELECT * FROM rfq_suppliers WHERE token=?", (token,)).fetchone()
    if not rs:
        return err("Invalid token", 404)
    rfq = db.execute("SELECT * FROM rfqs WHERE id=?", (rs["rfq_id"],)).fetchone()
    if rfq["status"] in ("Cancelled", "Winner Selected"):
        return err("RFQ closed")
    try:
        dl = datetime.fromisoformat(rfq["deadline"])
        if datetime.utcnow() > dl:
            return err("Deadline passed")
    except Exception:
        pass
    delivery_days = d.get("delivery_days")
    if not delivery_days or int(delivery_days) < 1:
        return err("delivery_days must be >=1")
    payment_terms = d.get("payment_terms")
    if not payment_terms:
        return err("payment_terms required")
    items = d.get("items") or []
    pr = db.execute("SELECT * FROM purchase_requests WHERE id=?", (rfq["pr_id"],)).fetchone()
    pr_items = db.execute("SELECT * FROM pr_items WHERE pr_id=?", (pr["id"],)).fetchall()
    prices = {}
    for it in items:
        pid = it.get("pr_item_id")
        price = it.get("unit_price")
        if price is None or float(price) <= 0:
            return err("unit_price must be positive")
        prices[pid] = float(price)
    for pi in pr_items:
        if pi["id"] not in prices:
            return err(f"Missing price for item {pi['id']}")
    total = sum(prices[pi["id"]] * pi["quantity"] for pi in pr_items)
    existing = db.execute("SELECT * FROM quotes WHERE rfq_id=? AND supplier_id=?",
                          (rfq["id"], rs["supplier_id"])).fetchone()
    if existing:
        rev = existing["revision"] + 1
        ref = existing["reference"]
        db.execute(
            "UPDATE quotes SET delivery_days=?, payment_terms=?, notes=?, revision=?, submitted_at=?, total=? WHERE id=?",
            (int(delivery_days), payment_terms, d.get("notes"), rev, now_iso(), total, existing["id"]),
        )
        db.execute("DELETE FROM quote_items WHERE quote_id=?", (existing["id"],))
        qid = existing["id"]
    else:
        ref = f"Q-{rfq['id']}-{rs['supplier_id']}-{secrets.token_hex(3).upper()}"
        cur = db.execute(
            "INSERT INTO quotes(rfq_id,supplier_id,delivery_days,payment_terms,notes,revision,submitted_at,reference,total) VALUES(?,?,?,?,?,?,?,?,?)",
            (rfq["id"], rs["supplier_id"], int(delivery_days), payment_terms, d.get("notes"), 1, now_iso(), ref, total),
        )
        qid = cur.lastrowid
        rev = 1
    for pi in pr_items:
        db.execute("INSERT INTO quote_items(quote_id,pr_item_id,unit_price) VALUES(?,?,?)",
                   (qid, pi["id"], prices[pi["id"]]))
    # Check if all responded -> Ready for Review
    total_sup = db.execute("SELECT COUNT(*) c FROM rfq_suppliers WHERE rfq_id=?", (rfq["id"],)).fetchone()["c"]
    total_q = db.execute("SELECT COUNT(*) c FROM quotes WHERE rfq_id=?", (rfq["id"],)).fetchone()["c"]
    if total_q >= total_sup and rfq["status"] == "Awaiting Quotes":
        db.execute("UPDATE rfqs SET status='Ready for Review' WHERE id=?", (rfq["id"],))
    db.commit()
    return jsonify({"reference": ref, "revision": rev, "total": total})


# ---------- QUOTE COMPARISON & WINNER ----------
@app.get("/api/rfqs/<int:rid>/quotes")
@require_auth()
def rfq_quotes(rid):
    db = get_db()
    r = db.execute("SELECT * FROM rfqs WHERE id=?", (rid,)).fetchone()
    if not r:
        return err("Not found", 404)
    quotes = db.execute("SELECT * FROM quotes WHERE rfq_id=?", (rid,)).fetchall()
    pr_items = db.execute("SELECT * FROM pr_items WHERE pr_id=?", (r["pr_id"],)).fetchall()
    result = []
    for q in quotes:
        sup = db.execute("SELECT * FROM suppliers WHERE id=?", (q["supplier_id"],)).fetchone()
        qi = db.execute("SELECT * FROM quote_items WHERE quote_id=?", (q["id"],)).fetchall()
        prices = {x["pr_item_id"]: x["unit_price"] for x in qi}
        line_items = []
        for pi in pr_items:
            up = prices.get(pi["id"], 0)
            line_items.append({"pr_item_id": pi["id"], "description": pi["description"],
                               "quantity": pi["quantity"], "unit_price": up,
                               "line_total": up * pi["quantity"]})
        result.append({
            "quote_id": q["id"], "supplier_id": sup["id"], "supplier_name": sup["company_name"],
            "supplier_score": sup["score"], "delivery_days": q["delivery_days"],
            "payment_terms": q["payment_terms"], "revision": q["revision"],
            "line_items": line_items, "total": q["total"], "reference": q["reference"],
        })
    if result:
        min_total = min(x["total"] for x in result)
        for x in result:
            x["recommended"] = x["total"] == min_total
    return jsonify(result)


@app.post("/api/rfqs/<int:rid>/select-winner")
@require_auth()
def select_winner(rid):
    d = request.get_json() or {}
    qid = d.get("quote_id")
    justification = d.get("justification")
    db = get_db()
    r = db.execute("SELECT * FROM rfqs WHERE id=?", (rid,)).fetchone()
    if not r:
        return err("Not found", 404)
    status = rfq_status_effective(db, r)
    if status not in ("Ready for Review", "Overdue"):
        return err("Cannot select winner in this state")
    if r["winner_supplier_id"]:
        return err("Winner already selected")
    q = db.execute("SELECT * FROM quotes WHERE id=? AND rfq_id=?", (qid, rid)).fetchone()
    if not q:
        return err("Quote not found", 404)
    quotes = db.execute("SELECT * FROM quotes WHERE rfq_id=?", (rid,)).fetchall()
    min_total = min(x["total"] for x in quotes)
    if q["total"] != min_total and not justification:
        return err("Justification required for non-lowest quote")
    db.execute(
        "UPDATE rfqs SET status='Winner Selected', winner_supplier_id=?, winner_justification=? WHERE id=?",
        (q["supplier_id"], justification, rid),
    )
    # Move PR to Approved then Ordered
    approved = stage_by_name(db, "Approved")
    ordered = stage_by_name(db, "Ordered")
    move_pr_stage(db, r["pr_id"], approved["id"], automatic=True)
    # Auto-create order
    pr_items = db.execute("SELECT * FROM pr_items WHERE pr_id=?", (r["pr_id"],)).fetchall()
    qi = db.execute("SELECT * FROM quote_items WHERE quote_id=?", (q["id"],)).fetchall()
    prices = {x["pr_item_id"]: x["unit_price"] for x in qi}
    year = datetime.utcnow().year
    seq = db.execute("SELECT COUNT(*)+1 c FROM orders WHERE order_number LIKE ?", (f"PO-{year}-%",)).fetchone()["c"]
    order_number = f"PO-{year}-{seq:05d}"
    expected = (datetime.utcnow() + timedelta(days=q["delivery_days"])).date().isoformat()
    cur = db.execute(
        "INSERT INTO orders(order_number,rfq_id,supplier_id,total,payment_terms,expected_delivery,created_at,status) VALUES(?,?,?,?,?,?,?,?)",
        (order_number, rid, q["supplier_id"], q["total"], q["payment_terms"], expected, now_iso(), "Pending"),
    )
    oid = cur.lastrowid
    for pi in pr_items:
        db.execute("INSERT INTO order_items(order_id,description,quantity,unit_price) VALUES(?,?,?,?)",
                   (oid, pi["description"], pi["quantity"], prices.get(pi["id"], 0)))
    db.execute("INSERT INTO order_status_history(order_id,status,changed_at) VALUES(?,?,?)",
               (oid, "Pending", now_iso()))
    move_pr_stage(db, r["pr_id"], ordered["id"], automatic=True)
    db.commit()
    return jsonify({"ok": True, "order_id": oid, "order_number": order_number})


# ---------- ORDERS ----------
def order_dict(db, o):
    items = db.execute("SELECT * FROM order_items WHERE order_id=?", (o["id"],)).fetchall()
    hist = db.execute("SELECT * FROM order_status_history WHERE order_id=? ORDER BY id", (o["id"],)).fetchall()
    sup = db.execute("SELECT * FROM suppliers WHERE id=?", (o["supplier_id"],)).fetchone()
    is_overdue = False
    if o["status"] != "Delivered":
        try:
            if datetime.fromisoformat(o["expected_delivery"]).date() < date.today():
                is_overdue = True
        except Exception:
            pass
    return {
        "id": o["id"], "order_number": o["order_number"], "supplier": {"id": sup["id"], "name": sup["company_name"]},
        "total": o["total"], "payment_terms": o["payment_terms"],
        "expected_delivery": o["expected_delivery"], "status": o["status"],
        "created_at": o["created_at"], "overdue": is_overdue,
        "items": [{"description": i["description"], "quantity": i["quantity"], "unit_price": i["unit_price"]} for i in items],
        "status_history": [{"status": h["status"], "at": h["changed_at"]} for h in hist],
        "rfq_id": o["rfq_id"],
    }


@app.get("/api/orders")
@require_auth()
def list_orders():
    db = get_db()
    rows = db.execute("SELECT * FROM orders ORDER BY id DESC").fetchall()
    return jsonify([order_dict(db, r) for r in rows])


@app.get("/api/orders/<int:oid>")
@require_auth()
def get_order(oid):
    db = get_db()
    r = db.execute("SELECT * FROM orders WHERE id=?", (oid,)).fetchone()
    if not r:
        return err("Not found", 404)
    return jsonify(order_dict(db, r))


STATUS_ORDER = ["Pending", "Confirmed", "Shipped", "Delivered"]


@app.post("/api/orders/<int:oid>/advance")
@require_auth()
def advance_order(oid):
    db = get_db()
    r = db.execute("SELECT * FROM orders WHERE id=?", (oid,)).fetchone()
    if not r:
        return err("Not found", 404)
    idx = STATUS_ORDER.index(r["status"])
    if idx == len(STATUS_ORDER) - 1:
        return err("Already delivered")
    new_status = STATUS_ORDER[idx + 1]
    db.execute("UPDATE orders SET status=? WHERE id=?", (new_status, oid))
    db.execute("INSERT INTO order_status_history(order_id,status,changed_at) VALUES(?,?,?)",
               (oid, new_status, now_iso()))
    db.commit()
    return jsonify(order_dict(db, db.execute("SELECT * FROM orders WHERE id=?", (oid,)).fetchone()))


@app.post("/api/orders/<int:oid>/rate")
@require_auth()
def rate_order(oid):
    d = request.get_json() or {}
    db = get_db()
    o = db.execute("SELECT * FROM orders WHERE id=?", (oid,)).fetchone()
    if not o:
        return err("Not found", 404)
    if o["status"] != "Delivered":
        return err("Can only rate delivered orders")
    for f in ("punctuality", "quality", "reliability"):
        v = d.get(f)
        if v is None or not (0 <= int(v) <= 100):
            return err(f"{f} 0-100 required")
    p, q, rl = int(d["punctuality"]), int(d["quality"]), int(d["reliability"])
    score = compute_score(p, q, rl)
    db.execute(
        "UPDATE suppliers SET punctuality=?, quality=?, reliability=?, score=? WHERE id=?",
        (p, q, rl, score, o["supplier_id"]),
    )
    db.commit()
    return jsonify({"ok": True, "supplier_id": o["supplier_id"], "score": score})


@app.post("/api/orders/<int:oid>/reorder")
@require_auth()
def reorder(oid):
    db = get_db()
    o = db.execute("SELECT * FROM orders WHERE id=?", (oid,)).fetchone()
    if not o:
        return err("Not found", 404)
    items = db.execute("SELECT * FROM order_items WHERE order_id=?", (oid,)).fetchall()
    stage = default_stage(db)
    cur = db.execute(
        "INSERT INTO purchase_requests(title,category_id,priority,stage_id,created_at,created_by) VALUES(?,?,?,?,?,?)",
        (f"Re-order {o['order_number']}", None, "Medium", stage["id"], now_iso(), g.user["id"]),
    )
    pid = cur.lastrowid
    for it in items:
        db.execute("INSERT INTO pr_items(pr_id,description,quantity) VALUES(?,?,?)",
                   (pid, it["description"], it["quantity"]))
    db.execute("INSERT INTO stage_history(pr_id,from_stage_id,to_stage_id,moved_at,automatic) VALUES(?,?,?,?,0)",
               (pid, None, stage["id"], now_iso()))
    db.commit()
    return jsonify(pr_dict(db, db.execute("SELECT * FROM purchase_requests WHERE id=?", (pid,)).fetchone())), 201


# ---------- DASHBOARD ----------
@app.get("/api/dashboard")
@require_auth()
def dashboard():
    db = get_db()
    # RFQs ready for review
    ready = db.execute("SELECT * FROM rfqs WHERE status='Ready for Review'").fetchall()
    # Overdue orders
    orders = db.execute("SELECT * FROM orders WHERE status<>'Delivered'").fetchall()
    overdue_orders = []
    for o in orders:
        try:
            if datetime.fromisoformat(o["expected_delivery"]).date() < date.today():
                overdue_orders.append(o)
        except Exception:
            pass
    # Stale PRs in New > 7 days
    new_stage = stage_by_name(db, "New")
    stale = []
    if new_stage:
        prs = db.execute("SELECT * FROM purchase_requests WHERE stage_id=?", (new_stage["id"],)).fetchall()
        for p in prs:
            try:
                created = datetime.fromisoformat(p["created_at"])
                if (datetime.utcnow() - created).days > 7:
                    stale.append(p)
            except Exception:
                pass
    return jsonify({
        "rfqs_ready_for_review": [{"id": r["id"], "title": r["title"], "pr_id": r["pr_id"]} for r in ready],
        "overdue_orders": [{"id": o["id"], "order_number": o["order_number"],
                            "expected_delivery": o["expected_delivery"]} for o in overdue_orders],
        "stale_purchase_requests": [{"id": p["id"], "title": p["title"], "created_at": p["created_at"]} for p in stale],
    })


@app.get("/api/health")
def health():
    return jsonify({"ok": True})


if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=False)
else:
    init_db()
