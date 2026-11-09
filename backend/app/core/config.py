import os
from pathlib import Path
from typing import Any, List
from dotenv import load_dotenv
from pydantic import ConfigDict, field_validator
try:
    from pydantic_settings import BaseSettings
except ImportError:
    from pydantic import BaseModel as BaseSettings  # fallback for lightweight environments

# Explicitly load .env from backend/.env or root
_backend_env = Path(__file__).resolve().parent.parent.parent / ".env"
if _backend_env.exists():
    load_dotenv(dotenv_path=_backend_env)
else:
    load_dotenv()


def normalize_database_url(url: str) -> str:
    """Normalizes database connection URLs for PostgreSQL and SQLite.

    Render Managed PostgreSQL supplies connection URLs starting with 'postgres://',
    which SQLAlchemy 2.0 rejects. This converts them to 'postgresql+psycopg2://'
    to match the installed psycopg2 driver.
    """
    if not url:
        return url
    trimmed = url.strip()
    if trimmed.startswith("postgres://"):
        return trimmed.replace("postgres://", "postgresql+psycopg2://", 1)
    if trimmed.startswith("postgresql://") and not trimmed.startswith("postgresql+"):
        return trimmed.replace("postgresql://", "postgresql+psycopg2://", 1)
    return trimmed


# Default database path resolved to backend/medivoice.db if it exists
_default_db_file = Path(__file__).resolve().parent.parent.parent / "medivoice.db"
_default_db_url = f"sqlite:///{_default_db_file.as_posix()}" if _default_db_file.exists() else "sqlite:///./medivoice.db"


class Settings(BaseSettings):
    PROJECT_NAME: str = "MediVoice AI - Aarogya One Hospital"
    API_V1_STR: str = "/api/v1"
    DEBUG: bool = True
    ENVIRONMENT: str = "development"

    # Fictional Hospital Context
    DEFAULT_HOSPITAL_NAME: str = "Aarogya One Hospital"
    DEFAULT_HOSPITAL_ID: str = "11111111-1111-1111-1111-111111111111"

    # Local development works out of the box. Set DATABASE_URL to PostgreSQL in deployment.
    DATABASE_URL: str = normalize_database_url(os.getenv("DATABASE_URL", _default_db_url))

    # AI Reasoning Provider Configuration (Backend-only; never exposed to client)
    AI_PROVIDER: str = os.getenv("AI_PROVIDER", os.getenv("LLM_PROVIDER", "mock"))
    LLM_PROVIDER: str = os.getenv("LLM_PROVIDER", os.getenv("AI_PROVIDER", "mock"))
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
    GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-3.5-flash")
    GEMINI_TIMEOUT_SECONDS: float = float(os.getenv("GEMINI_TIMEOUT_SECONDS", "15.0"))
    GEMINI_MAX_TOOL_ROUNDS: int = int(os.getenv("GEMINI_MAX_TOOL_ROUNDS", "4"))
    GEMINI_THINKING_LEVEL: str = os.getenv("GEMINI_THINKING_LEVEL", "low")
    GEMINI_ENABLE_FALLBACK: bool = os.getenv("GEMINI_ENABLE_FALLBACK", "false").lower() in ("true", "1", "yes")

    # Gnani Speech-to-Text (Prisma) & Text-to-Speech (Timbre) Configuration
    GNANI_API_KEY: str = os.getenv("GNANI_API_KEY", "")
    GNANI_API_BASE: str = os.getenv("GNANI_API_BASE", "https://api.vachana.ai")
    GNANI_STT_MODEL: str = os.getenv("GNANI_STT_MODEL", "prisma-v3.0")
    GNANI_TTS_MODEL: str = os.getenv("GNANI_TTS_MODEL", "timbre-v3.0")
    GNANI_TTS_VOICE: str = os.getenv("GNANI_TTS_VOICE", "Shivani")
    GNANI_DEFAULT_LANGUAGE: str = os.getenv("GNANI_DEFAULT_LANGUAGE", "en-IN")

    # Voice Orchestration & Streaming Configuration
    VOICE_ENABLED: bool = os.getenv("VOICE_ENABLED", "true").lower() in ("true", "1", "yes")
    VOICE_MAX_DURATION_SECONDS: int = int(os.getenv("VOICE_MAX_DURATION_SECONDS", "60"))
    VOICE_REQUEST_TIMEOUT_SECONDS: float = float(os.getenv("VOICE_REQUEST_TIMEOUT_SECONDS", "35.0"))
    # Detailed voice timings are opt-in; enable with VOICE_DIAGNOSTICS_ENABLED=true.
    VOICE_DIAGNOSTICS_ENABLED: bool = os.getenv("VOICE_DIAGNOSTICS_ENABLED", "false").lower() in ("true", "1", "yes")

    # Lab Verification Code & Rate Limiting Configuration
    LAB_VERIFICATION_CODE_EXPIRY_HOURS: int = int(os.getenv("LAB_VERIFICATION_CODE_EXPIRY_HOURS", "72"))
    LAB_VERIFICATION_MAX_GENERATION_RETRIES: int = int(os.getenv("LAB_VERIFICATION_MAX_GENERATION_RETRIES", "20"))
    LAB_VERIFICATION_RATE_LIMIT_MAX_ATTEMPTS: int = int(os.getenv("LAB_VERIFICATION_RATE_LIMIT_MAX_ATTEMPTS", "5"))
    LAB_VERIFICATION_RATE_LIMIT_WINDOW_SECONDS: int = int(os.getenv("LAB_VERIFICATION_RATE_LIMIT_WINDOW_SECONDS", "300"))

    # Security & Synthetic Staff Auth
    ENABLE_DEMO_STAFF_AUTH: bool = os.getenv("ENABLE_DEMO_STAFF_AUTH", "false").lower() in ("true", "1", "yes")

    # CORS
    BACKEND_CORS_ORIGINS: List[str] = [
        "http://localhost:3000",
        "http://localhost:5173",
        "http://localhost:3001",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:3001",
    ]

    @field_validator("DATABASE_URL", mode="before")
    @classmethod
    def assemble_database_url(cls, v: Any) -> str:
        if isinstance(v, str):
            return normalize_database_url(v)
        return str(v)

    @field_validator("BACKEND_CORS_ORIGINS", mode="before")
    @classmethod
    def assemble_cors_origins(cls, v: Any) -> List[str]:
        if isinstance(v, str):
            v_stripped = v.strip()
            if not v_stripped:
                return []
            if v_stripped.startswith("[") and v_stripped.endswith("]"):
                try:
                    import json
                    parsed = json.loads(v_stripped)
                    if isinstance(parsed, list):
                        return [str(item).strip() for item in parsed if str(item).strip()]
                except Exception:
                    pass
            return [part.strip() for part in v_stripped.split(",") if part.strip()]
        elif isinstance(v, (list, tuple)):
            return [str(item).strip() for item in v if str(item).strip()]
        return v

    model_config = ConfigDict(extra="ignore", case_sensitive=True)


settings = Settings()
