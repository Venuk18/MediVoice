import os
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from app.core.config import Settings, normalize_database_url
from app.core.security import authenticate_staff, is_demo_staff_auth_allowed
from app.main import app
from app.agent.adapters import create_reasoning_adapter
from app.services.speech.stt_service import GnaniPrismaSTT, SpeechServiceError
from app.services.speech.tts_service import GnaniTimbreTTS
from app.db.base import Base
from app.models.patient import Patient


# --- Phase 1 Validation: Config, CORS, & DB URL ---

def test_cors_origins_comma_separated():
    s = Settings(BACKEND_CORS_ORIGINS="https://medivoice.vercel.app, https://preview.vercel.app")
    assert s.BACKEND_CORS_ORIGINS == ["https://medivoice.vercel.app", "https://preview.vercel.app"]


def test_cors_origins_json_list():
    s = Settings(BACKEND_CORS_ORIGINS='["https://medivoice.vercel.app", "http://localhost:3000"]')
    assert s.BACKEND_CORS_ORIGINS == ["https://medivoice.vercel.app", "http://localhost:3000"]


def test_cors_origins_empty_string():
    s = Settings(BACKEND_CORS_ORIGINS="")
    assert s.BACKEND_CORS_ORIGINS == []


def test_cors_origins_default_list():
    s = Settings()
    assert len(s.BACKEND_CORS_ORIGINS) == 6
    assert "http://localhost:3000" in s.BACKEND_CORS_ORIGINS


def test_database_url_normalization_postgres_render():
    raw_render_url = "postgres://medivoice_user:secret_pass@dpg-xxxx-a.render.com/medivoice_db"
    normalized = normalize_database_url(raw_render_url)
    assert normalized == "postgresql+psycopg2://medivoice_user:secret_pass@dpg-xxxx-a.render.com/medivoice_db"


def test_database_url_normalization_postgresql():
    raw_url = "postgresql://medivoice_user:secret_pass@localhost:5432/medivoice_db"
    normalized = normalize_database_url(raw_url)
    assert normalized == "postgresql+psycopg2://medivoice_user:secret_pass@localhost:5432/medivoice_db"


def test_database_url_sqlite_unmodified():
    sqlite_url = "sqlite:///./medivoice.db"
    assert normalize_database_url(sqlite_url) == sqlite_url


# --- Phase 2 Validation: Alembic Metadata & Patient Model ---

def test_patient_model_metadata_registration():
    table_names = [t.name for t in Base.metadata.sorted_tables]
    assert "patients" in table_names, "patients table must be registered in Base.metadata"
    patients_table = Base.metadata.tables["patients"]
    col_names = [c.name for c in patients_table.columns]
    assert "id" in col_names
    assert "patient_reference" in col_names
    assert "full_name" in col_names
    assert "phone_number" in col_names
    assert "created_at" in col_names
    assert "updated_at" in col_names


# --- Phase 4 Validation: Demo Staff Auth Security ---

def test_demo_auth_allowed_in_development(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("ENABLE_DEMO_STAFF_AUTH", "false")
    assert is_demo_staff_auth_allowed() is True
    # Successfully authenticates demo account in dev
    account = authenticate_staff("dr.sharma", "demo-doctor-password")
    assert account["username"] == "dr.sharma"


def test_demo_auth_disabled_by_default_in_production(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("ENABLE_DEMO_STAFF_AUTH", "false")
    assert is_demo_staff_auth_allowed() is False

    with pytest.raises(HTTPException) as exc_info:
        authenticate_staff("dr.sharma", "demo-doctor-password")
    assert exc_info.value.status_code == 403
    assert exc_info.value.detail["code"] == "DEMO_AUTH_DISABLED"


def test_demo_auth_enabled_explicitly_in_production(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("ENABLE_DEMO_STAFF_AUTH", "true")
    assert is_demo_staff_auth_allowed() is True
    account = authenticate_staff("dr.sharma", "demo-doctor-password")
    assert account["username"] == "dr.sharma"


def test_auth_demo_accounts_endpoint_in_production(monkeypatch):
    client = TestClient(app)
    # When disabled in production: returns empty list
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("ENABLE_DEMO_STAFF_AUTH", "false")
    resp = client.get("/api/v1/auth/demo-accounts")
    assert resp.status_code == 200
    assert resp.json() == []

    # When enabled in production: returns demo profiles
    monkeypatch.setenv("ENABLE_DEMO_STAFF_AUTH", "true")
    resp_enabled = client.get("/api/v1/auth/demo-accounts")
    assert resp_enabled.status_code == 200
    assert len(resp_enabled.json()) > 0


# --- Phase 4 Validation: AI Fallback Production Guard ---

def test_ai_fallback_disabled_in_production(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("GEMINI_ENABLE_FALLBACK", "false")
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)

    with pytest.raises(RuntimeError, match="GEMINI_API_KEY must be configured in production"):
        create_reasoning_adapter(provider="gemini", api_key="")


def test_stt_fallback_disabled_in_production(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    stt = GnaniPrismaSTT(api_key="")

    # Dummy valid WAV header
    wav_bytes = b"RIFF" + b"\x00" * 4 + b"WAVEfmt " + b"\x10\x00\x00\x00" + b"\x01\x00\x01\x00" + b"\x40\x1f\x00\x00" + b"\x80\x3e\x00\x00" + b"\x02\x00\x10\x00" + b"data" + b"\x00" * 10

    with pytest.raises(SpeechServiceError) as exc_info:
        stt.transcribe(audio_bytes=wav_bytes)
    assert exc_info.value.code == "STT_PROVIDER_NOT_CONFIGURED"
    assert exc_info.value.status_code == 503

