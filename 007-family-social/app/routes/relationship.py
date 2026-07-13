from datetime import datetime
from flask import Blueprint, request, jsonify
from flask_login import current_user, login_required
from app import db
from app.models import User, Profile, Relationship, RelationshipType, RelationshipStatus
from app.utils.decorators import check_profile_complete

bp = Blueprint('relationship', __name__)

def get_reciprocal_type(rel_type):
    """Get the reciprocal relationship type"""
    if rel_type == RelationshipType.PARENT:
        return RelationshipType.CHILD
    elif rel_type == RelationshipType.CHILD:
        return RelationshipType.PARENT
    else:
        return rel_type

@bp.route('/api/relationship/request', methods=['POST'])
@login_required
@check_profile_complete
def send_relationship_request():
    data = request.get_json()
    if not data or 'recipient_username' not in data or 'type' not in data:
        return jsonify({'error': 'Recipient username and type are required'}), 400

    recipient_username = data['recipient_username']
    rel_type_str = data['type']

    # Validate type
    valid_types = [RelationshipType.PARENT, RelationshipType.CHILD, RelationshipType.SPOUSE, RelationshipType.SIBLING]
    if rel_type_str not in valid_types:
        return jsonify({'error': 'Invalid relationship type. Must be Parent, Child, Spouse, or Sibling'}), 400

    rel_type = rel_type_str

    # Check if recipient exists
    recipient_profile = Profile.query.filter(Profile.username.ilike(recipient_username)).first()
    if not recipient_profile:
        return jsonify({'error': 'Recipient not found'}), 404

    recipient = recipient_profile.user

    # Cannot request relationship with self
    if current_user.id == recipient.id:
        return jsonify({'error': 'Cannot request relationship with yourself'}), 400

    # Check if there's already a relationship (Pending or Active) between these users
    existing_rel = Relationship.query.filter(
        (
            ((Relationship.requester_id == current_user.id) & (Relationship.recipient_id == recipient.id)) |
            ((Relationship.requester_id == recipient.id) & (Relationship.recipient_id == current_user.id))
        )
    ).filter(
        Relationship.status.in_([RelationshipStatus.PENDING, RelationshipStatus.ACTIVE])
    ).first()

    if existing_rel:
        return jsonify({'error': 'A relationship request already exists between these users'}), 400

    # Create the relationship request
    reciprocal_type = get_reciprocal_type(rel_type)

    relationship = Relationship(
        requester_id=current_user.id,
        recipient_id=recipient.id,
        requester_type=rel_type,
        recipient_type=reciprocal_type,
        status=RelationshipStatus.PENDING
    )

    db.session.add(relationship)
    db.session.commit()

    return jsonify({
        'message': 'Relationship request sent',
        'relationship_id': relationship.id
    }), 201

@bp.route('/api/relationship/incoming', methods=['GET'])
@login_required
@check_profile_complete
def get_incoming_requests():
    relationships = Relationship.query.filter(
        Relationship.recipient_id == current_user.id,
        Relationship.status == RelationshipStatus.PENDING
    ).all()

    requests = []
    for rel in relationships:
        requester = rel.requester
        if requester and requester.profile:
            requests.append({
                'id': rel.id,
                'requester': {
                    'user_id': requester.id,
                    'username': requester.profile.username,
                    'display_name': requester.profile.display_name
                },
                'type': rel.requester_type,
                'created_at': rel.created_at.isoformat()
            })

    return jsonify({'incoming_requests': requests}), 200

@bp.route('/api/relationship/outgoing', methods=['GET'])
@login_required
@check_profile_complete
def get_outgoing_requests():
    relationships = Relationship.query.filter(
        Relationship.requester_id == current_user.id,
        Relationship.status == RelationshipStatus.PENDING
    ).all()

    requests = []
    for rel in relationships:
        recipient = rel.recipient
        if recipient and recipient.profile:
            requests.append({
                'id': rel.id,
                'recipient': {
                    'user_id': recipient.id,
                    'username': recipient.profile.username,
                    'display_name': recipient.profile.display_name
                },
                'type': rel.requester_type,
                'created_at': rel.created_at.isoformat()
            })

    return jsonify({'outgoing_requests': requests}), 200

@bp.route('/api/relationship/active', methods=['GET'])
@login_required
@check_profile_complete
def get_active_relationships():
    relationships = Relationship.query.filter(
        (Relationship.requester_id == current_user.id) | (Relationship.recipient_id == current_user.id)
    ).filter(
        Relationship.status == RelationshipStatus.ACTIVE
    ).all()

    active = []
    for rel in relationships:
        if rel.requester_id == current_user.id:
            other_user = rel.recipient
            rel_type = rel.requester_type
        else:
            other_user = rel.requester
            rel_type = rel.recipient_type

        if other_user and other_user.profile:
            active.append({
                'user_id': other_user.id,
                'username': other_user.profile.username,
                'display_name': other_user.profile.display_name,
                'type': rel_type,
                'relationship_id': rel.id
            })

    # Sort alphabetically by username
    active.sort(key=lambda x: x['username'].lower())

    return jsonify({'active_relationships': active}), 200

@bp.route('/api/relationship/past', methods=['GET'])
@login_required
@check_profile_complete
def get_past_relationships():
    relationships = Relationship.query.filter(
        (Relationship.requester_id == current_user.id) | (Relationship.recipient_id == current_user.id)
    ).filter(
        Relationship.status.in_([RelationshipStatus.DECLINED, RelationshipStatus.CANCELED, RelationshipStatus.ENDED])
    ).all()

    past = []
    for rel in relationships:
        if rel.requester_id == current_user.id:
            other_user = rel.recipient
            rel_type = rel.requester_type
        else:
            other_user = rel.requester
            rel_type = rel.recipient_type

        if not other_user or not other_user.profile:
            other_username = "Deleted User"
            other_display_name = "Deleted User"
        else:
            other_username = other_user.profile.username
            other_display_name = other_user.profile.display_name

        past.append({
            'other_user': {
                'username': other_username,
                'display_name': other_display_name
            },
            'type': rel_type,
            'status': rel.status,
            'date': rel.updated_at.isoformat()
        })

    # Sort by date descending (newest first)
    past.sort(key=lambda x: x['date'], reverse=True)

    return jsonify({'past_relationships': past}), 200

@bp.route('/api/relationship/<int:relationship_id>/accept', methods=['POST'])
@login_required
@check_profile_complete
def accept_relationship(relationship_id):
    relationship = Relationship.query.get(relationship_id)
    if not relationship:
        return jsonify({'error': 'Relationship not found'}), 404

    # Only recipient can accept
    if relationship.recipient_id != current_user.id:
        return jsonify({'error': 'You can only accept incoming requests'}), 403

    # Can only accept pending requests
    if relationship.status != RelationshipStatus.PENDING:
        return jsonify({'error': 'Only pending requests can be accepted'}), 400

    relationship.status = RelationshipStatus.ACTIVE
    relationship.updated_at = datetime.utcnow()
    db.session.commit()

    return jsonify({'message': 'Relationship accepted'}), 200

@bp.route('/api/relationship/<int:relationship_id>/decline', methods=['POST'])
@login_required
@check_profile_complete
def decline_relationship(relationship_id):
    relationship = Relationship.query.get(relationship_id)
    if not relationship:
        return jsonify({'error': 'Relationship not found'}), 404

    # Only recipient can decline
    if relationship.recipient_id != current_user.id:
        return jsonify({'error': 'You can only decline incoming requests'}), 403

    # Can only decline pending requests
    if relationship.status != RelationshipStatus.PENDING:
        return jsonify({'error': 'Only pending requests can be declined'}), 400

    relationship.status = RelationshipStatus.DECLINED
    relationship.updated_at = datetime.utcnow()
    db.session.commit()

    return jsonify({'message': 'Relationship declined'}), 200

@bp.route('/api/relationship/<int:relationship_id>/cancel', methods=['POST'])
@login_required
@check_profile_complete
def cancel_relationship(relationship_id):
    relationship = Relationship.query.get(relationship_id)
    if not relationship:
        return jsonify({'error': 'Relationship not found'}), 404

    # Only requester can cancel
    if relationship.requester_id != current_user.id:
        return jsonify({'error': 'You can only cancel outgoing requests'}), 403

    # Can only cancel pending requests
    if relationship.status != RelationshipStatus.PENDING:
        return jsonify({'error': 'Only pending requests can be canceled'}), 400

    relationship.status = RelationshipStatus.CANCELED
    relationship.updated_at = datetime.utcnow()
    db.session.commit()

    return jsonify({'message': 'Relationship request canceled'}), 200

@bp.route('/api/relationship/<int:relationship_id>/end', methods=['POST'])
@login_required
@check_profile_complete
def end_relationship(relationship_id):
    relationship = Relationship.query.get(relationship_id)
    if not relationship:
        return jsonify({'error': 'Relationship not found'}), 404

    # Either party can end an active relationship
    if relationship.requester_id != current_user.id and relationship.recipient_id != current_user.id:
        return jsonify({'error': 'You can only end relationships you are part of'}), 403

    # Can only end active relationships
    if relationship.status != RelationshipStatus.ACTIVE:
        return jsonify({'error': 'Only active relationships can be ended'}), 400

    relationship.status = RelationshipStatus.ENDED
    relationship.updated_at = datetime.utcnow()
    db.session.commit()

    return jsonify({'message': 'Relationship ended'}), 200
