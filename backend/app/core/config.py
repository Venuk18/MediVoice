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
