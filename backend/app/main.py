import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.api.v1.router import api_router

app = FastAPI(
    title=settings.PROJECT_NAME,
    description=(
        "MediVoice AI development demo for Aarogya One Hospital. Provides patient workflows, "
        "staff workspaces, and synthetic operational data."
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
        allow_credentials=False,
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
        "environment": settings.ENVIRONMENT,
        "docs_url": "/docs",
        "api_v1": settings.API_V1_STR,
    }


if __name__ == "__main__":
    import uvicorn

    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8001"))
    reload = os.getenv("ENVIRONMENT", settings.ENVIRONMENT).lower() not in ("production", "prod")
    uvicorn.run("app.main:app", host=host, port=port, reload=reload)
