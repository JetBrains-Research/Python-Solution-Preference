from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_bcrypt import Bcrypt
import os

db = SQLAlchemy()
bcrypt = Bcrypt()
login_manager = LoginManager()

def create_app():
    app = Flask(__name__)

    # Configure from environment
    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key')
    app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///family_platform.db')
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

    db.init_app(app)
    bcrypt.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = 'auth.login'
    login_manager.login_message_category = 'info'

    from app.models import User, Profile, Relationship, Post
    with app.app_context():
        db.create_all()

    from app.routes.auth import bp as auth_bp
    from app.routes.profile import bp as profile_bp
    from app.routes.relationship import bp as relationship_bp
    from app.routes.post import bp as post_bp
    from app.routes.feed import bp as feed_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(profile_bp)
    app.register_blueprint(relationship_bp)
    app.register_blueprint(post_bp)
    app.register_blueprint(feed_bp)

    return app
