from fastapi.testclient import TestClient

from app.main import app
from app.services.speech.tts_service import generate_synthetic_wav
import io


def test_no_secret_exposure_in_config_endpoint():
    """Config endpoints must NEVER reveal API keys or secret credentials."""
    client = TestClient(app)
    
    agent_config = client.get("/api/v1/agent/config").json()
    assert "api_key" not in str(agent_config).lower()
    
    voice_config = client.get("/api/v1/voice/config").json()
    assert "api_key" not in str(voice_config).lower()
    assert "secret" not in str(voice_config).lower()


def test_public_voice_cannot_access_staff_endpoints():
    """Unauthenticated public clients cannot access staff operations."""
    client = TestClient(app)
    
    # Doctor workspace slot creation requires doctor auth
    doc_res = client.post("/api/v1/doctors/doc-1/slots", json={})
    assert doc_res.status_code in (401, 403)
    
    # Staff /auth/me requires authentication token
    auth_res = client.get("/api/v1/auth/me")
    assert auth_res.status_code == 401


def test_arbitrary_tool_execution_strictly_blocked(db_session, seeded_hospital_data):
    """The tool router rejects any non-allowlisted tool regardless of source."""
    from app.agent.tool_router import RestrictedToolRouter
    from app.agent.schemas import ToolCallIntent
    
    router = RestrictedToolRouter()
    malicious_intents = [
        ToolCallIntent(tool_name="eval_python", arguments={"code": "import os; os.system('whoami')"}),
        ToolCallIntent(tool_name="raw_sql_query", arguments={"query": "DELETE FROM appointments"}),
        ToolCallIntent(tool_name="fetch_all_patient_identities", arguments={}),
    ]
    
    for intent in malicious_intents:
        result = router.execute_tool(db=db_session, intent=intent)
        assert result.success is False
        assert "not permitted" in result.error.lower()
