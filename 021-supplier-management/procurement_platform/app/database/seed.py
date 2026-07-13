from sqlalchemy.orm import Session
from sqlalchemy import text
import hashlib
import secrets
from datetime import datetime

def create_admin_user(db: Session):
    try:
        result = db.execute(text("SELECT id FROM users WHERE username = :username"), {"username": "admin"}).fetchone()
        if result:
            return

        password_hash = hashlib.pbkdf2_hmac('sha256', b'admin123', b'salt', 10000).hex()
        user_id = db.execute(
            text("INSERT INTO users (username, password_hash, email, full_name, is_active, role) VALUES (:username, :password_hash, :email, :full_name, :is_active, :role)"),
            {
                "username": "admin",
                "password_hash": password_hash,
                "email": "admin@procurement.com",
                "full_name": "System Administrator",
                "is_active": True,
                "role": "Admin"
            }
        ).lastrowid
        db.commit()
    except Exception as e:
        db.rollback()
        raise e

def create_default_categories(db: Session):
    categories = [
        {"name": "Raw Materials", "description": "Raw materials for production"},
        {"name": "Office Supplies", "description": "Office supplies and stationery"},
        {"name": "Equipment", "description": "Equipment and machinery"},
        {"name": "Services", "description": "Professional services"},
        {"name": "Other", "description": "Other categories"}
    ]

    for cat_data in categories:
        try:
            result = db.execute(text("SELECT id FROM categories WHERE name = :name"), {"name": cat_data["name"]}).fetchone()
            if not result:
                db.execute(
                    text("INSERT INTO categories (name, description) VALUES (:name, :description)"),
                    cat_data
                )
        except Exception as e:
            db.rollback()
            raise e

    db.commit()

def create_default_stages(db: Session):
    stages = [
        {"name": "New", "color": "#FFFF00", "order_index": 0, "is_default": True},
        {"name": "In Review", "color": "#FFA500", "order_index": 1, "is_default": False},
        {"name": "Approved", "color": "#008000", "order_index": 2, "is_default": False},
        {"name": "Ordered", "color": "#0000FF", "order_index": 3, "is_default": False}
    ]

    for stage_data in stages:
        try:
            result = db.execute(text("SELECT id FROM kanban_stages WHERE name = :name"), {"name": stage_data["name"]}).fetchone()
            if not result:
                db.execute(
                    text("INSERT INTO kanban_stages (name, color, order_index, is_default) VALUES (:name, :color, :order_index, :is_default)"),
                    stage_data
                )
        except Exception as e:
            db.rollback()
            raise e

    db.commit()

def generate_quote_token():
    return secrets.token_hex(32)

def init_db(db: Session):
    create_admin_user(db)
    create_default_categories(db)
    create_default_stages(db)

def seed_test_data(db: Session):
    init_db(db)
