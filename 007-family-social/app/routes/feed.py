from flask import Blueprint, request, jsonify
from flask_login import current_user, login_required
from app.models import User, Profile, Relationship, RelationshipStatus, Post
from app.utils.decorators import check_profile_complete
from app import db

bp = Blueprint('feed', __name__)

@bp.route('/api/feed', methods=['GET'])
@login_required
@check_profile_complete
def get_feed():
    # Get all user IDs with active relationships with current user
    relationship_user_ids = [current_user.id]  # Include own posts

    # Find all active relationships
    relationships = Relationship.query.filter(
        (Relationship.requester_id == current_user.id) | (Relationship.recipient_id == current_user.id)
    ).filter(
        Relationship.status == RelationshipStatus.ACTIVE
    ).all()

    for rel in relationships:
        if rel.requester_id == current_user.id:
            relationship_user_ids.append(rel.recipient_id)
        else:
            relationship_user_ids.append(rel.requester_id)

    # Remove duplicates
    relationship_user_ids = list(set(relationship_user_ids))

    # Get posts from these users, ordered by newest first
    posts = Post.query.filter(Post.user_id.in_(relationship_user_ids))\
                     .order_by(Post.created_at.desc())\
                     .all()

    posts_data = []
    for post in posts:
        author = post.author
        posts_data.append({
            'id': post.id,
            'caption': post.caption,
            'images': post.images or [],
            'created_at': post.created_at.isoformat(),
            'updated_at': post.updated_at.isoformat(),
            'author': {
                'user_id': author.id,
                'username': author.profile.username,
                'display_name': author.profile.display_name
            }
        })

    return jsonify({'posts': posts_data}), 200

@bp.route('/api/search', methods=['GET'])
@login_required
@check_profile_complete
def search_users():
    query = request.args.get('q', '').strip()
    if not query:
        return jsonify({'error': 'Search query is required'}), 400

    # Search by username or display name (case-insensitive substring match)
    profiles = Profile.query.filter(
        (Profile.username.ilike(f'%{query}%')) | (Profile.display_name.ilike(f'%{query}%'))
    ).all()

    # Include current user (no self-exclusion)
    results = []
    for profile in profiles:
        if profile.user and profile.user.is_active:
            results.append({
                'user_id': profile.user.id,
                'username': profile.username,
                'display_name': profile.display_name,
                'profile_photo': profile.profile_photo
            })

    # Sort alphabetically by username
    results.sort(key=lambda x: x['username'].lower())

    return jsonify({'results': results}), 200
