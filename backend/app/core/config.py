import os
from typing import List, Union
from pydantic import ConfigDict, AnyHttpUrl, field_validator
try:
    from pydantic_settings import BaseSettings
except ImportError:
    from pydantic import BaseModel as BaseSettings  # fallback for lightweight environments


class Settings(BaseSettings):
    PROJECT_NAME: str = "MediVoice AI - Aarogya One Hospital"
    API_V1_STR: str = "/api/v1"
    DEBUG: bool = True
    ENVIRONMENT: str = "development"

    # Fictional Hospital Context
    DEFAULT_HOSPITAL_NAME: str = "Aarogya One Hospital"
    DEFAULT_HOSPITAL_ID: str = "11111111-1111-1111-1111-111111111111"

    # Database Configuration
    # Uses PostgreSQL syntax by default; will accept sqlite for test / lightweight runners
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL",
        "postgresql+psycopg2://postgres:postgres@localhost:5432/aarogya_one_db"
    )

    # AI Reasoning Provider Configuration (Backend-only; never exposed to client)
    LLM_PROVIDER: str = os.getenv("LLM_PROVIDER", "auto")
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
    GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-3.6-flash")
    GEMINI_TIMEOUT_SECONDS: float = float(os.getenv("GEMINI_TIMEOUT_SECONDS", "15.0"))
    GEMINI_MAX_TOOL_ROUNDS: int = int(os.getenv("GEMINI_MAX_TOOL_ROUNDS", "4"))

    # Lab Verification Code & Rate Limiting Configuration
    LAB_VERIFICATION_CODE_EXPIRY_HOURS: int = int(os.getenv("LAB_VERIFICATION_CODE_EXPIRY_HOURS", "72"))
    LAB_VERIFICATION_MAX_GENERATION_RETRIES: int = int(os.getenv("LAB_VERIFICATION_MAX_GENERATION_RETRIES", "20"))
    LAB_VERIFICATION_RATE_LIMIT_MAX_ATTEMPTS: int = int(os.getenv("LAB_VERIFICATION_RATE_LIMIT_MAX_ATTEMPTS", "5"))
    LAB_VERIFICATION_RATE_LIMIT_WINDOW_SECONDS: int = int(os.getenv("LAB_VERIFICATION_RATE_LIMIT_WINDOW_SECONDS", "300"))

    # CORS
    BACKEND_CORS_ORIGINS: List[str] = [
        "http://localhost:3000",
        "http://localhost:5173",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:5173",
        "*"
    ]

    model_config = ConfigDict(extra="ignore", case_sensitive=True)


settings = Settings()

