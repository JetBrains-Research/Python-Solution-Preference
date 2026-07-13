from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from routes import accounts, venues, search, blocked_dates, tours, weddings

app = FastAPI(
    title="Wedding Venue Platform API",
    description="API for wedding venue booking platform",
    version="1.0.0"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(accounts.router)
app.include_router(venues.router)
app.include_router(search.router)
app.include_router(blocked_dates.router)
app.include_router(tours.router)
app.include_router(weddings.router)

@app.get("/")
def root():
    return {
        "message": "Welcome to Wedding Venue Platform API",
        "docs": "/docs"
    }

@app.get("/health")
def health_check():
    return {"status": "healthy"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
