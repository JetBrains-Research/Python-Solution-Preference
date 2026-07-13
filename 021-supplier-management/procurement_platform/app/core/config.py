from pydantic_settings import BaseSettings
from typing import Optional

class Settings(BaseSettings):
    app_name: str = "Supplier Relationship Management Platform"
    app_version: str = "1.0.0"
    secret_key: str = "super-secret-key-for-dev-only"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    database_url: str = "sqlite:///procurement.db"

    class Config:
        env_file = ".env"

settings = Settings()
