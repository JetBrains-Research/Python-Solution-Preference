from datetime import datetime
from flask import Blueprint, request, jsonify
from flask_login import current_user, login_required
from app import db
from app.models import User, Profile, Relationship, RelationshipStatus, Post
from app.utils.decorators import check_profile_complete

bp = Blueprint('post', __name__)

@bp.route('/api/posts', methods=['POST'])
@login_required
@check_profile_complete
def create_post():
    data = request.get_json()
    if not data:
        return jsonify({'error': 'No data provided'}), 400

    caption = data.get('caption')
    images = data.get('images', [])

    # Validate that at least one of caption or images is provided
    if not caption and not images:
        return jsonify({'error': 'Post must have a caption or at least one image'}), 400

    # Validate caption is non-empty if provided
    if caption and not caption.strip():
        return jsonify({'error': 'Caption cannot be empty'}), 400

    # Validate images (up to 4)
    if images:
        if not isinstance(images, list):
            return jsonify({'error': 'Images must be a list'}), 400
        if len(images) > 4:
            return jsonify({'error': 'Maximum 4 images allowed'}), 400
        for img in images:
            if not isinstance(img, str):
                return jsonify({'error': 'Images must be strings (URLs)'}), 400

    post = Post(
        user_id=current_user.id,
        caption=caption,
        images=images
    )

    db.session.add(post)
    db.session.commit()

    return jsonify({
        'message': 'Post created successfully',
        'post_id': post.id,
        'caption': post.caption,
        'images': post.images or [],
        'created_at': post.created_at.isoformat()
    }), 201

@bp.route('/api/posts/<int:post_id>', methods=['GET'])
@login_required
@check_profile_complete
def get_post(post_id):
    post = Post.query.get(post_id)
    if not post:
        return jsonify({'error': 'Post not found'}), 404

    author = post.author

    # Check visibility: author can always see, users with active relationship can see
    if current_user.id != author.id:
        rel = Relationship.query.filter(
            ((Relationship.requester_id == current_user.id) & (Relationship.recipient_id == author.id)) |
            ((Relationship.requester_id == author.id) & (Relationship.recipient_id == current_user.id))
        ).filter(Relationship.status == RelationshipStatus.ACTIVE).first()

        if not rel:
            return jsonify({'error': 'No active relationship with post author'}), 403

    return jsonify({
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
    }), 200

@bp.route('/api/posts/<int:post_id>', methods=['PUT'])
@login_required
@check_profile_complete
def update_post(post_id):
    post = Post.query.get(post_id)
    if not post:
        return jsonify({'error': 'Post not found'}), 404

    # Only author can edit
    if post.user_id != current_user.id:
        return jsonify({'error': 'You can only edit your own posts'}), 403

    data = request.get_json()
    if not data or 'caption' not in data:
        return jsonify({'error': 'Caption is required for update'}), 400

    caption = data['caption']

    # Validate caption
    if not caption.strip():
        return jsonify({'error': 'Caption cannot be empty'}), 400

    post.caption = caption
    post.updated_at = datetime.utcnow()
    db.session.commit()

    return jsonify({
        'message': 'Post updated successfully',
        'post_id': post.id,
        'caption': post.caption,
        'updated_at': post.updated_at.isoformat()
    }), 200

@bp.route('/api/posts/<int:post_id>', methods=['DELETE'])
@login_required
@check_profile_complete
def delete_post(post_id):
    post = Post.query.get(post_id)
    if not post:
        return jsonify({'error': 'Post not found'}), 404

    # Only author can delete
    if post.user_id != current_user.id:
        return jsonify({'error': 'You can only delete your own posts'}), 400

    db.session.delete(post)
    db.session.commit()

    return jsonify({'message': 'Post deleted successfully'}), 200
