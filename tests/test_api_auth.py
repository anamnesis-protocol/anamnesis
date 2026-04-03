"""
tests/test_api_auth.py — Tests for /auth/signup, /auth/login, /auth/status

Uses FastAPI TestClient with mocked Supabase so no real network calls are made.
"""

import os
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

# ── App setup ─────────────────────────────────────────────────────────────────

os.environ.setdefault("SOVEREIGN_ENV", "testnet") # testnet bypasses subscription checks
os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_KEY", "test-service-key")
os.environ.setdefault("SUPABASE_ANON_KEY", "test-anon-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-jwt-secret-that-is-long-enough-32b")
os.environ.setdefault("HEDERA_NETWORK", "testnet")
os.environ.setdefault("OPERATOR_ID", "0.0.1234")
os.environ.setdefault("OPERATOR_KEY", "302e020100300506032b657004220420" + "a" * 64)

from api.main import app # noqa: E402

client = TestClient(app)


# ── Helpers ────────────────────────────────────────────────────────────────────

def _make_mock_supabase(
    sign_up_user=None,
    sign_in_session=None,
    sign_in_user=None,
    ):
    """Build a mock Supabase client for auth endpoint tests."""
    mock_sb = MagicMock()

    # signup
    mock_user = MagicMock()
    mock_user.id = "user-uuid-1234"
    mock_user.email = "test@example.com"
    mock_signup_res = MagicMock()
    mock_signup_res.user = sign_up_user if sign_up_user is not None else mock_user
    mock_signup_res.session = None # email confirmation required by default
    mock_sb.auth.sign_up.return_value = mock_signup_res

    # subscriptions insert
    mock_sb.table.return_value.insert.return_value.execute.return_value = MagicMock(data=[])
    mock_sb.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(data={"status": "inactive"})

    # login
    mock_session = MagicMock()
    mock_session.access_token = "test-access-token"
    mock_login_user = MagicMock()
    mock_login_user.id = "user-uuid-1234"
    mock_login_user.email = "test@example.com"
    mock_login_res = MagicMock()
    mock_login_res.session = sign_in_session if sign_in_session is not None else mock_session
    mock_login_res.user = sign_in_user if sign_in_user is not None else mock_login_user
    mock_sb.auth.sign_in_with_password.return_value = mock_login_res

    return mock_sb


    # ── POST /auth/signup ──────────────────────────────────────────────────────────

    class TestSignup:
        def test_signup_email_confirmation_required(self):
            """Successful signup with email confirmation pending returns 200 + message."""
            with patch("api.routes.auth._supabase_service", return_value=_make_mock_supabase()):
                res = client.post("/auth/signup", json={"email": "test@example.com", "password": "password123"})
                assert res.status_code == 200
                data = res.json()
                assert data["confirm_email"] is True
                assert data["access_token"] is None
                assert data["email"] == "test@example.com"

            def test_signup_immediate_session(self):
                """Successful signup when email confirmation disabled returns access_token."""
                mock_session = MagicMock()
                mock_session.access_token = "immediate-token"
                mock_sb = _make_mock_supabase()
                mock_sb.auth.sign_up.return_value.session = mock_session

                with patch("api.routes.auth._supabase_service", return_value=mock_sb):
                    res = client.post("/auth/signup", json={"email": "test@example.com", "password": "password123"})
                    assert res.status_code == 200
                    assert res.json()["access_token"] == "immediate-token"
                    assert res.json()["confirm_email"] is False

                def test_signup_supabase_error_returns_400(self):
                    """Supabase auth exception propagates as 400."""
                    mock_sb = _make_mock_supabase()
                    mock_sb.auth.sign_up.side_effect = Exception("Email already registered")

                    with patch("api.routes.auth._supabase_service", return_value=mock_sb):
                        res = client.post("/auth/signup", json={"email": "taken@example.com", "password": "password123"})
                        assert res.status_code == 400

                    def test_signup_null_user_returns_400(self):
                        """Null user in signup response returns 400."""
                        mock_sb = _make_mock_supabase(sign_up_user=None)
                        mock_sb.auth.sign_up.return_value.user = None

                        with patch("api.routes.auth._supabase_service", return_value=mock_sb):
                            res = client.post("/auth/signup", json={"email": "test@example.com", "password": "pw"})
                            assert res.status_code == 400

                        def test_signup_missing_fields_returns_422(self):
                            """Missing required fields returns 422 from Pydantic."""
                            res = client.post("/auth/signup", json={"email": "test@example.com"})
                            assert res.status_code == 422


                            # ── POST /auth/login ───────────────────────────────────────────────────────────

                            class TestLogin:
                                def test_login_success(self):
                                    """Valid credentials return access_token."""
                                    with patch("api.routes.auth._supabase_anon", return_value=_make_mock_supabase()):
                                        res = client.post("/auth/login", json={"email": "test@example.com", "password": "password123"})
                                        assert res.status_code == 200
                                        data = res.json()
                                        assert data["access_token"] == "test-access-token"
                                        assert data["email"] == "test@example.com"

                                    def test_login_wrong_credentials_returns_401(self):
                                        """Failed sign-in returns 401."""
                                        mock_sb = _make_mock_supabase()
                                        mock_sb.auth.sign_in_with_password.side_effect = Exception("Invalid credentials")

                                        with patch("api.routes.auth._supabase_anon", return_value=mock_sb):
                                            res = client.post("/auth/login", json={"email": "test@example.com", "password": "wrongpass"})
                                            assert res.status_code == 401

                                        def test_login_no_session_returns_401(self):
                                            """Successful Supabase call but no session returns 401."""
                                            mock_sb = _make_mock_supabase(sign_in_session=None)
                                            mock_sb.auth.sign_in_with_password.return_value.session = None

                                            with patch("api.routes.auth._supabase_anon", return_value=mock_sb):
                                                res = client.post("/auth/login", json={"email": "test@example.com", "password": "password123"})
                                                assert res.status_code == 401

                                            def test_login_missing_fields_returns_422(self):
                                                res = client.post("/auth/login", json={"email": "test@example.com"})
                                                assert res.status_code == 422


                                                # ── GET /auth/status ───────────────────────────────────────────────────────────

                                                class TestAuthStatus:
                                                    def _make_token(self, user_id: str = "user-uuid-1234", email: str = "test@example.com") -> str:
                                                        """Create a valid JWT for testing."""
                                                        import jwt
                                                        import time
                                                        payload = {
                                                            "sub": user_id,
                                                            "email": email,
                                                            "aud": "authenticated",
                                                            "exp": int(time.time()) + 3600,
                                                            }
                                                        return jwt.encode(payload, "test-jwt-secret-that-is-long-enough-32b", algorithm="HS256")

                                                        def test_status_valid_token(self):
                                                            """Valid token returns user info and subscription status."""
                                                            token = self._make_token()
                                                            mock_sb = _make_mock_supabase()
                                                            mock_sb.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(
                                                                data={"status": "active", "current_period_end": "2026-04-17T00:00:00Z"}
                                                                )

                                                            with patch("api.routes.auth._supabase_service", return_value=mock_sb):
                                                                res = client.get("/auth/status", headers={"Authorization": f"Bearer {token}"})
                                                                assert res.status_code == 200
                                                                data = res.json()
                                                                assert data["user_id"] == "user-uuid-1234"
                                                                assert data["subscription_status"] == "active"

                                                            def test_status_no_token_returns_401(self):
                                                                res = client.get("/auth/status")
                                                                assert res.status_code == 401

                                                                def test_status_expired_token_returns_401(self):
                                                                    import jwt
                                                                    import time
                                                                    payload = {
                                                                        "sub": "user-uuid-1234",
                                                                        "email": "test@example.com",
                                                                        "aud": "authenticated",
                                                                        "exp": int(time.time()) - 3600, # expired
                                                                        }
                                                                    token = jwt.encode(payload, "test-jwt-secret-that-is-long-enough-32b", algorithm="HS256")
                                                                    res = client.get("/auth/status", headers={"Authorization": f"Bearer {token}"})
                                                                    assert res.status_code == 401

                                                                    def test_status_no_subscription_returns_inactive(self):
                                                                        """No subscription row → returns inactive."""
                                                                        token = self._make_token()
                                                                        mock_sb = _make_mock_supabase()
                                                                        mock_sb.table.return_value.select.return_value.eq.return_value.single.return_value.execute.side_effect = Exception("No row")

                                                                        with patch("api.routes.auth._supabase_service", return_value=mock_sb):
                                                                            res = client.get("/auth/status", headers={"Authorization": f"Bearer {token}"})
                                                                            assert res.status_code == 200
                                                                            assert res.json()["subscription_status"] == "inactive"
