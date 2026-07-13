from datetime import date
from flask import Blueprint, request, jsonify
from flask_login import current_user, login_required
from app import db
from app.models import User, Profile, Relationship, RelationshipStatus, RelationshipType
from app.utils.decorators import check_profile_complete
import re

bp = Blueprint('profile', __name__)

def validate_username(username):
    """Validate username: 3-30 chars, alphanumeric + underscores only"""
    if not 3 <= len(username) <= 30:
        return False
    if not re.match(r'^[a-zA-Z0-9_]+$', username):
        return False
    return True

@bp.route('/api/profile', methods=['GET'])
@login_required
@check_profile_complete
def get_profile():
    profile = current_user.profile
    return jsonify({
        'username': profile.username,
        'display_name': profile.display_name,
        'bio': profile.bio,
        'profile_photo': profile.profile_photo,
        'birth_date': profile.birth_date.isoformat() if profile.birth_date else None,
        'is_complete': profile.is_complete
    }), 200

@bp.route('/api/profile', methods=['PUT'])
@login_required
def update_profile():
    if current_user.profile and current_user.profile.is_complete:
        return jsonify({'error': 'Profile already complete and cannot be modified'}), 400

    data = request.get_json()
    if not data:
        return jsonify({'error': 'No data provided'}), 400

    username = data.get('username')
    display_name = data.get('display_name')
    bio = data.get('bio')
    profile_photo = data.get('profile_photo')
    birth_date_str = data.get('birth_date')

    # Validate required fields
    if not username or not display_name:
        return jsonify({'error': 'Username and display name are required'}), 400

    # Validate username
    if not validate_username(username):
        return jsonify({'error': 'Username must be 3-30 alphanumeric characters or underscores'}), 400

    # Check username uniqueness (case-insensitive)
    existing_profile = Profile.query.filter(Profile.username.ilike(username)).first()
    if existing_profile and existing_profile.user_id != current_user.id:
        return jsonify({'error': 'Username already taken'}), 400

    # Validate birth date
    birth_date = None
    if birth_date_str:
        try:
            birth_date = date.fromisoformat(birth_date_str)
            if birth_date > date.today():
                return jsonify({'error': 'Birth date cannot be in the future'}), 400
        except ValueError:
            return jsonify({'error': 'Invalid birth date format. Use YYYY-MM-DD'}), 400

    # Create or update profile
    if not current_user.profile:
        profile = Profile(
            user_id=current_user.id,
            username=username,
            display_name=display_name,
            bio=bio,
            profile_photo=profile_photo,
            birth_date=birth_date,
            is_complete=True
        )
        db.session.add(profile)
    else:
        profile = current_user.profile
        profile.username = username
        profile.display_name = display_name
        if bio is not None:
            profile.bio = bio
        if profile_photo is not None:
            profile.profile_photo = profile_photo
        if birth_date_str is not None:
            profile.birth_date = birth_date
        profile.is_complete = True

    db.session.commit()

    return jsonify({'message': 'Profile updated successfully'}), 200

@bp.route('/api/profile/<username>', methods=['GET'])
@login_required
@check_profile_complete
def get_public_profile(username):
    # Find user by username (case-insensitive)
    profile = Profile.query.filter(Profile.username.ilike(username)).first()
    if not profile:
        return jsonify({'error': 'Profile not found'}), 404

    user = profile.user

    # Get active relationships grouped by type, sorted alphabetically by username
    active_relationships = []
    relationships = Relationship.query.filter(
        (Relationship.requester_id == user.id) | (Relationship.recipient_id == user.id)
    ).filter(Relationship.status == RelationshipStatus.ACTIVE).all()

    for rel in relationships:
        if rel.requester_id == user.id:
            other_user = rel.recipient
            rel_type = rel.requester_type
        else:
            other_user = rel.requester
            rel_type = rel.recipient_type

        if other_user and other_user.profile:
            active_relationships.append({
                'username': other_user.profile.username,
                'display_name': other_user.profile.display_name,
                'type': rel_type
            })

    # Sort by username alphabetically
    active_relationships.sort(key=lambda x: x['username'].lower())

    # Group by type
    grouped_relationships = {}
    for rel in active_relationships:
        rel_type = rel['type']
        if rel_type not in grouped_relationships:
            grouped_relationships[rel_type] = []
        grouped_relationships[rel_type].append({
            'username': rel['username'],
            'display_name': rel['display_name']
        })

    # Check if current user can see private info (birth date)
    can_see_private = False
    if current_user.id == user.id:
        can_see_private = True
    else:
        rel = Relationship.query.filter(
            ((Relationship.requester_id == current_user.id) & (Relationship.recipient_id == user.id)) |
            ((Relationship.requester_id == user.id) & (Relationship.recipient_id == current_user.id))
        ).filter(Relationship.status == RelationshipStatus.ACTIVE).first()
        if rel:
            can_see_private = True

    result = {
        'username': profile.username,
        'display_name': profile.display_name,
        'bio': profile.bio,
        'profile_photo': profile.profile_photo,
        'active_relationships': grouped_relationships
    }

    if can_see_private and profile.birth_date:
        result['birth_date'] = profile.birth_date.isoformat()

    return jsonify(result), 200

@bp.route('/api/profile/<username>/posts', methods=['GET'])
@login_required
@check_profile_complete
def get_user_posts(username):
    profile = Profile.query.filter(Profile.username.ilike(username)).first()
    if not profile:
        return jsonify({'error': 'Profile not found'}), 404

    user = profile.user

    # Check if current user can see posts (must have active relationship or be the user)
    if current_user.id != user.id:
        rel = Relationship.query.filter(
            ((Relationship.requester_id == current_user.id) & (Relationship.recipient_id == user.id)) |
            ((Relationship.requester_id == user.id) & (Relationship.recipient_id == current_user.id))
        ).filter(Relationship.status == RelationshipStatus.ACTIVE).first()

        if not rel:
            return jsonify({'error': 'No active relationship with this user'}), 403

    posts = Post.query.filter_by(user_id=user.id).order_by(Post.created_at.desc()).all()

    posts_data = []
    for post in posts:
        posts_data.append({
            'id': post.id,
            'caption': post.caption,
            'images': post.images or [],
            'created_at': post.created_at.isoformat(),
            'updated_at': post.updated_at.isoformat(),
            'author': {
                'username': user.profile.username,
                'display_name': user.profile.display_name
            }
        })

    return jsonify({'posts': posts_data}), 200
