from fastapi import FastAPI, Depends, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer
from app.core.config import settings
from app.database import engine, Base, get_db
from app.database.seed import init_db, seed_test_data
from app.api.v1 import api_router
from app.api.v1.endpoints.auth import get_current_active_user, get_current_admin_user, User
import logging
from typing import Optional

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def create_tables():
    Base.metadata.create_all(bind=engine)

def init_app():
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description="Supplier Relationship Management Platform API"
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.on_event("startup")
    async def on_startup():
        create_tables()
        db = next(get_db())
        try:
            init_db(db)
        finally:
            db.close()

    @app.get("/")
    async def root():
        return {"name": settings.app_name, "version": settings.app_version}

    @app.get("/health")
    async def health():
        return {"status": "healthy"}

    app.include_router(api_router, prefix="/api/v1")

    return app

app = init_app()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
