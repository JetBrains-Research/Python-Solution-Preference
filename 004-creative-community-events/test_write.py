import sys
sys.path.insert(0, '.')
from config import Config
from models import db, User
from flask import Flask

app = Flask(__name__)
app.config.from_object(Config)
db.init_app(app)

with app.app_context():
    db.create_all()
    # Try inserting a user
    u = User(username='test', email='test@test.com', password_hash='hash')
    db.session.add(u)
    db.session.commit()
    print(f"Inserted user with id={u.id}")
    print(f"Db file: {Config.SQLALCHEMY_DATABASE_URI}")
