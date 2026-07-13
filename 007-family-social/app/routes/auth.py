from datetime import datetime
from flask import Blueprint, request, jsonify
from flask_login import login_user, logout_user, current_user, login_required
from app import db, bcrypt
from app.models import User, Profile, Relationship, RelationshipStatus
import re

bp = Blueprint('auth', __name__)

@bp.route('/api/register', methods=['POST'])
def register():
    data = request.get_json()
    if not data or 'email' not in data or 'password' not in data:
        return jsonify({'error': 'Email and password are required'}), 400

    email = data['email'].strip().lower()
    password = data['password']

    # Validate email
    if not re.match(r'^[^@]+@[^@]+\.[^@]+$', email):
        return jsonify({'error': 'Invalid email format'}), 400

    # Check if email exists
    if User.query.filter_by(email=email).first():
        return jsonify({'error': 'Email already registered'}), 400

    # Validate password
    if len(password) < 8:
        return jsonify({'error': 'Password must be at least 8 characters'}), 400

    # Create user
    user = User(email=email)
    user.set_password(password)
    db.session.add(user)
    db.session.commit()

    return jsonify({'message': 'Registration successful. Please complete your profile.', 'user_id': user.id}), 201

@bp.route('/api/login', methods=['POST'])
def login():
    data = request.get_json()
    if not data or 'email' not in data or 'password' not in data:
        return jsonify({'error': 'Email and password are required'}), 400

    email = data['email'].strip().lower()
    password = data['password']

    user = User.query.filter_by(email=email).first()

    # Generic error message to not reveal if email or password was wrong
    if not user or not user.check_password(password):
        return jsonify({'error': 'Invalid email or password'}), 401

    login_user(user)
    return jsonify({'message': 'Login successful', 'user_id': user.id}), 200

@bp.route('/api/logout', methods=['POST'])
@login_required
def logout():
    logout_user()
    return jsonify({'message': 'Logout successful'}), 200

@bp.route('/api/account/delete', methods=['DELETE'])
@login_required
def delete_account():
    user = current_user

    # Get all relationships where user is requester or recipient
    relationships = Relationship.query.filter(
        (Relationship.requester_id == user.id) | (Relationship.recipient_id == user.id)
    ).all()

    for rel in relationships:
        if rel.status == RelationshipStatus.ACTIVE:
            rel.status = RelationshipStatus.ENDED
            rel.updated_at = datetime.utcnow()

    # Delete user's posts
    from app.models import Post
    Post.query.filter_by(user_id=user.id).delete()

    # Delete profile
    if user.profile:
        db.session.delete(user.profile)

    # Delete user
    db.session.delete(user)
    db.session.commit()

    logout_user()
    return jsonify({'message': 'Account deleted successfully'}), 200
