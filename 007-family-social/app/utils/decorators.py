from functools import wraps
from flask import jsonify
from flask_login import current_user

def check_profile_complete(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            return jsonify({'error': 'Authentication required'}), 401

        if not current_user.profile or not current_user.profile.is_complete:
            return jsonify({'error': 'Profile not complete. Please complete your profile.'}), 403

        return f(*args, **kwargs)
    return decorated_function
