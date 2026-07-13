from flask import Flask
import os
from dotenv import load_dotenv

load_dotenv()

def create_app():
    app = Flask(__name__)

    # Configuration
    app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'dev-secret-key-change-in-production')
    app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL', 'sqlite:///marketplace.db')
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['UPLOAD_FOLDER'] = os.path.join(os.path.dirname(__file__), 'uploads')
    app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max upload

    # Ensure upload folder exists
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

    # Import and initialize db from models
    from app.models import db
    db.init_app(app)

    # Import models to ensure they're registered with db
    from app.models import Product, Order

    # Register blueprints
    from app.routes.product import product_bp
    from app.routes.browse import browse_bp
    from app.routes.checkout import checkout_bp
    from app.routes.status import status_bp

    app.register_blueprint(product_bp)
    app.register_blueprint(browse_bp)
    app.register_blueprint(checkout_bp)
    app.register_blueprint(status_bp)

    # Create tables
    with app.app_context():
        db.create_all()

    return app
