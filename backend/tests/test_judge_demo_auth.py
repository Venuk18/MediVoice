import base64
import hashlib
import hmac
import json
import time

from app.core.security import StaffRole, _AUTH_SECRET, require_staff_roles
from fastapi import HTTPException
from starlette.requests import Request


def _encoded_hash(password: str) -> str:
    salt = b"judge-demo-test!!"
    digest = hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1, dklen=32)
    return f"scrypt$16384$8$1${salt.hex()}${digest.hex()}"


def test_judge_demo_login_and_session_profile(client, monkeypatch):
    monkeypatch.setenv("ENABLE_JUDGE_DEMO_LOGIN", "true")
    monkeypatch.setenv("JUDGE_DEMO_PASSWORD_HASH", _encoded_hash("synthetic-test-password"))

    response = client.post(
        "/api/v1/auth/login",
        json={"username": "judge.viewer", "password": "synthetic-test-password"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["staff"]["role"] == StaffRole.DEMO_VIEWER.value
    assert body["staff"]["username"] == "judge.viewer"
    assert body["expires_at"] <= int(time.time()) + 1800

    profile = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {body['access_token']}"})
    assert profile.status_code == 200
    assert profile.json()["role"] == StaffRole.DEMO_VIEWER.value


def test_judge_demo_login_is_disabled_without_explicit_configuration(client, monkeypatch):
    monkeypatch.delenv("ENABLE_JUDGE_DEMO_LOGIN", raising=False)
    monkeypatch.delenv("JUDGE_DEMO_PASSWORD_HASH", raising=False)
    response = client.post(
        "/api/v1/auth/login",
        json={"username": "judge.viewer", "password": "synthetic-test-password"},
    )
    assert response.status_code == 403


def test_judge_demo_wrong_password_and_staff_api_are_denied(client, monkeypatch):
    monkeypatch.setenv("ENABLE_JUDGE_DEMO_LOGIN", "true")
    monkeypatch.setenv("JUDGE_DEMO_PASSWORD_HASH", _encoded_hash("synthetic-test-password"))
    wrong_password = client.post(
        "/api/v1/auth/login",
        json={"username": "judge.viewer", "password": "incorrect-password"},
    )
    assert wrong_password.status_code == 401

    login = client.post(
        "/api/v1/auth/login",
        json={"username": "judge.viewer", "password": "synthetic-test-password"},
    )
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    forbidden = client.get("/api/v1/maintenance/work-orders", headers=headers)
    assert forbidden.status_code == 403


def test_judge_role_is_denied_by_other_staff_role_dependencies():
    dependency = require_staff_roles([StaffRole.MAINTENANCE_STAFF])
    claims = {"role": StaffRole.DEMO_VIEWER.value, "exp": int(time.time()) + 300}
    raw = json.dumps(claims, separators=(",", ":"), sort_keys=True).encode()
    b64_payload = base64.urlsafe_b64encode(raw).decode().rstrip("=")
    signature = hmac.new(_AUTH_SECRET.encode(), b64_payload.encode(), hashlib.sha256).hexdigest()
    request = Request({"type": "http", "headers": []})
    try:
        dependency(request, f"Bearer {b64_payload}.{signature}", None, None)
        assert False, "DEMO_VIEWER must not be authorized for maintenance routes"
    except HTTPException as exc:
        assert exc.status_code == 403
