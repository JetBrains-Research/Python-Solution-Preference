from fastapi import APIRouter

from .endpoints import auth, users, categories, stages, suppliers, purchase_requests, rfqs, quotes, orders, dashboard

api_router = APIRouter()
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(users.router, prefix="/users", tags=["users"])
api_router.include_router(categories.router, prefix="/categories", tags=["categories"])
api_router.include_router(stages.router, prefix="/stages", tags=["stages"])
api_router.include_router(suppliers.router, prefix="/suppliers", tags=["suppliers"])
api_router.include_router(purchase_requests.router, prefix="/purchase-requests", tags=["purchase_requests"])
api_router.include_router(rfqs.router, prefix="/rfqs", tags=["rfqs"])
api_router.include_router(quotes.router, prefix="/quotes", tags=["quotes"])
api_router.include_router(orders.router, prefix="/orders", tags=["orders"])
api_router.include_router(dashboard.router, prefix="/dashboard", tags=["dashboard"])
