from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.api.v1.router import api_router

app = FastAPI(
    title=settings.PROJECT_NAME,
    description=(
        "MediVoice AI - Voice-First Hospital Operations Platform for Aarogya One Hospital. "
        "Phase 1: Backend Foundation, PostgreSQL/SQLAlchemy Schemas, Transaction-Safe Slot Booking, "
        "and AI Tool Interface Readiness."
    ),
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
)

# CORS Middleware
if settings.BACKEND_CORS_ORIGINS:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.BACKEND_CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

# Include v1 API routes
app.include_router(api_router, prefix=settings.API_V1_STR)


@app.get("/", tags=["Health"])
def root_health():
    """Healthcheck endpoint confirming backend readiness."""
    return {
        "status": "healthy",
        "service": settings.PROJECT_NAME,
        "hospital": settings.DEFAULT_HOSPITAL_NAME,
        "phase": "Phase 1 - Backend Foundation & Database Design",
        "docs_url": "/docs",
        "api_v1": settings.API_V1_STR,
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="127.0.0.1", port=8001, reload=True)

