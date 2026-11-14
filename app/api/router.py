from fastapi import APIRouter

from app.api.v1.decisions import router as decisions_router
from app.api.v1.health import router as health_router
from app.api.v1.profile import router as profile_router
from app.api.v1.recommendations import router as recommendations_router
from app.api.v1.scheduler import router as scheduler_router
from app.api.v1.sync import router as sync_router

api_router = APIRouter(prefix="/api")
api_router.include_router(health_router)
api_router.include_router(sync_router)
api_router.include_router(profile_router)
api_router.include_router(recommendations_router)
api_router.include_router(decisions_router)
api_router.include_router(scheduler_router)
