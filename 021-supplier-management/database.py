from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

def init_db(app):
    with app.app_context():
        db.init_app(app)
        db.create_all()
        
        # Seed data
        from models import User, Category, Stage
        
        # Create admin user
        if not User.query.filter_by(username='admin').first():
            admin = User(username='admin', password='admin123', role='admin')
            db.session.add(admin)
        
        # Create categories
        categories = ['Raw Materials', 'Office Supplies', 'Equipment', 'Services', 'Other']
        for cat_name in categories:
            if not Category.query.filter_by(name=cat_name).first():
                cat = Category(name=cat_name)
                db.session.add(cat)
        
        # Create stages
        stages_data = [
            ('New', '#28a745', 0),
            ('In Review', '#ffc107', 1),
            ('Approved', '#17a2b8', 2),
            ('Ordered', '#007bff', 3)
        ]
        for name, color, order in stages_data:
            if not Stage.query.filter_by(name=name).first():
                stage = Stage(name=name, color=color, order=order)
                db.session.add(stage)
        
        db.session.commit()
