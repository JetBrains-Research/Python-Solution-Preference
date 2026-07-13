import os

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL', 'sqlite:////Users/ilia_all/Projects/routing-preference/data/workspaces/004-creative-community-events_dd0c7f36/community.db')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
