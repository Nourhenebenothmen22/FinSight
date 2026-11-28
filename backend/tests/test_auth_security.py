"""Unit tests for F1 security helpers, schemas, rate limiter, CSRF, and OIDC JWKS checks."""

import base64
import hashlib
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from fastapi import HTTPException
from jose import jwt
from pydantic import ValidationError
from starlette.requests import Request

from app import worker as worker_module
from app.api.deps import verify_cookie_csrf_origin
from app.core import security as security_module
from app.core.config import Settings
from app.core.rate_limit import extract_client_ip
from app.core.security import (
    _google_jwks_cache,
    generate_opaque_token,
    generate_pkce_pair,
    hash_token,
    verify_google_id_token,
    verify_password_constant_time,
)
from app.schemas.auth import RegisterRequest
from app.services.auth import sanitize_next_path
from app.services.email import (
    LoggingEmailSender,
    render_password_reset_email,
    render_verification_email,
)


def _make_request(
    *,
    peer_ip: str = "127.0.0.1",
    headers: dict[str, str] | None = None,
) -> Request:
    raw_headers = [
        (key.lower().encode("latin-1"), value.encode("latin-1"))
        for key, value in (headers or {}).items()
    ]
    scope: dict[str, Any] = {
        "type": "http",
        "method": "POST",
        "path": "/api/v1/auth/refresh",
        "headers": raw_headers,
        "client": (peer_ip, 12345),
    }
    return Request(scope)


def _generate_rsa_jwk_and_token(
    *,
    kid: str = "test-kid-1",
    claims_override: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], str]:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_numbers = private_key.public_key().public_numbers()

    def _b64uint(value: int) -> str:
        byte_len = (value.bit_length() + 7) // 8
        return (
            base64.urlsafe_b64encode(value.to_bytes(byte_len, "big")).rstrip(b"=").decode("ascii")
        )

    jwk_dict: dict[str, Any] = {
        "kty": "RSA",
        "kid": kid,
        "use": "sig",
        "alg": "RS256",
        "n": _b64uint(public_numbers.n),
        "e": _b64uint(public_numbers.e),
    }
    pem_private = private_key.private_bytes(
        encoding=Encoding.PEM,
        format=__import__(
            "cryptography.hazmat.primitives.serialization"
        ).hazmat.primitives.serialization.PrivateFormat.PKCS8,
        encryption_algorithm=__import__(
            "cryptography.hazmat.primitives.serialization"
        ).hazmat.primitives.serialization.NoEncryption(),
    )
    _ = private_key.public_key().public_bytes(
        encoding=Encoding.PEM,
        format=PublicFormat.SubjectPublicKeyInfo,
    )

    now = datetime.now(UTC)
    claims: dict[str, Any] = {
        "iss": "https://accounts.google.com",
        "aud": "google-client-123",
        "sub": "google-sub-999",
        "email": "alice@example.com",
        "email_verified": True,
        "name": "Alice Analyst",
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=10)).timestamp()),
    }
    if claims_override:
        claims.update(claims_override)

    token = jwt.encode(claims, pem_private, algorithm="RS256", headers={"kid": kid})
    return jwk_dict, token


class TestAuthSchemasAndSanitization:
    """Validate email normalization, password complexity, and redirect sanitization."""

    def test_register_schema_normalizes_and_validates_password(self) -> None:
        req = RegisterRequest(
            name="  Alice\n Analyst  ",
            email="  Alice.Tester@Example.COM ",
            password="Valid!Password2026",
        )
        assert req.name == "Alice Analyst"
        assert req.email == "alice.tester@example.com"

    @pytest.mark.parametrize(
        "bad_password",
        [
            "Short1!a",  # < 12 chars
            "nouppercase123!",
            "NOLOWERCASE123!",
            "NoDigitsHere!Aa",
            "NoSpecialChar123Aa",
            "A" * 130 + "a1!",  # > 128 chars
        ],
    )
    def test_register_schema_rejects_weak_passwords(self, bad_password: str) -> None:
        with pytest.raises(ValidationError):
            RegisterRequest(
                name="Alice",
                email="alice@example.com",
                password=bad_password,
            )

    @pytest.mark.parametrize(
        ("candidate", "expected"),
        [
            ("/profile", "/profile"),
            ("/dashboard?tab=health", "/dashboard?tab=health"),
            (None, "/profile"),
            ("https://evil.example/phish", "/profile"),
            ("//evil.example/phish", "/profile"),
            ("/\\evil.example", "/profile"),
            ("/profile\r\nInjected", "/profile"),
        ],
    )
    def test_sanitize_next_path_prevents_open_redirects(
        self, candidate: str | None, expected: str
    ) -> None:
        assert sanitize_next_path(candidate, default="/profile") == expected


class TestSecurityPrimitives:
    """Validate token utilities, constant-time dummy verification, and email escaping."""

    def test_constant_time_verify_handles_absent_hash(self) -> None:
        assert verify_password_constant_time("anything", None) is False

    def test_opaque_token_and_pkce_s256(self) -> None:
        t1 = generate_opaque_token()
        t2 = generate_opaque_token()
        assert t1 != t2
        assert len(hash_token(t1)) == 64

        verifier, challenge = generate_pkce_pair()
        expected = (
            base64.urlsafe_b64encode(hashlib.sha256(verifier.encode("ascii")).digest())
            .rstrip(b"=")
            .decode("ascii")
        )
        assert challenge == expected

    def test_email_templates_escape_html_and_include_disclaimer(self) -> None:
        _, ver_text, ver_html = render_verification_email(
            "<script>alert(1)</script>",
            "http://localhost:3000/verify-email?token=abc",
        )
        assert "<script>" not in ver_html
        assert "&lt;script&gt;alert(1)&lt;/script&gt;" in ver_html
        assert "not investment advice" in ver_text.lower()

        _, rst_text, rst_html = render_password_reset_email(
            "Bob & Co",
            "http://localhost:3000/reset-password?token=xyz",
        )
        assert "Bob &amp; Co" in rst_html
        assert "not investment advice" in rst_text.lower()


class TestProxyCsrfAndConfigGuards:
    """Validate XFF resolution, CSRF origin check, and Google settings consistency."""

    def test_extract_client_ip_only_trusts_configured_proxies(
        self, test_settings: Settings
    ) -> None:
        trusted_req = _make_request(
            peer_ip="172.18.0.5",
            headers={"X-Forwarded-For": "203.0.113.10, 172.18.0.5"},
        )
        assert extract_client_ip(trusted_req, test_settings) == "203.0.113.10"

        untrusted_req = _make_request(
            peer_ip="198.51.100.77",
            headers={"X-Forwarded-For": "1.2.3.4"},
        )
        assert extract_client_ip(untrusted_req, test_settings) == "198.51.100.77"

    def test_verify_cookie_csrf_origin_blocks_cross_site(self, test_settings: Settings) -> None:
        allowed_req = _make_request(headers={"Origin": "http://localhost:3000"})
        verify_cookie_csrf_origin(allowed_req, test_settings)

        evil_req = _make_request(headers={"Origin": "https://evil.example"})
        with pytest.raises(HTTPException) as exc_info:
            verify_cookie_csrf_origin(evil_req, test_settings)
        assert exc_info.value.status_code == 403

    def test_google_settings_reject_partial_credentials(self, test_settings: Settings) -> None:
        dumped = test_settings.model_dump(
            exclude={
                "DATABASE_URL",
                "REDIS_URL",
                "QDRANT_URL",
                "S3_ENDPOINT",
                "S3_ENDPOINT_URL",
                "S3_ADMIN_URL",
                "OLLAMA_URL",
            }
        )
        dumped["GOOGLE_CLIENT_ID"] = "only-id-no-secret"
        dumped["GOOGLE_CLIENT_SECRET"] = ""
        with pytest.raises(ValueError, match="GOOGLE_CLIENT_ID"):
            Settings(**dumped)


class TestGoogleIdTokenVerification:
    """Validate Google OIDC JWKS verification and failure modes."""

    @pytest.mark.asyncio
    async def test_verify_google_id_token_valid_and_key_rotation(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _google_jwks_cache.keys = []
        _google_jwks_cache.fetched_at = 0.0

        jwk_dict, id_token = _generate_rsa_jwk_and_token(kid="kid-valid")

        async def fake_fetch_jwks(timeout_seconds: float = 10.0) -> list[dict[str, Any]]:
            _ = timeout_seconds
            return [jwk_dict]

        monkeypatch.setattr(security_module, "fetch_google_jwks", fake_fetch_jwks)

        claims = await verify_google_id_token(id_token, client_id="google-client-123")
        assert claims["sub"] == "google-sub-999"
        assert claims["email"] == "alice@example.com"

    @pytest.mark.asyncio
    async def test_verify_google_id_token_rejects_unverified_or_wrong_claims(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _google_jwks_cache.keys = []
        _google_jwks_cache.fetched_at = 0.0

        jwk_unverified, tok_unverified = _generate_rsa_jwk_and_token(
            kid="k1", claims_override={"email_verified": False}
        )
        jwk_issuer, tok_issuer = _generate_rsa_jwk_and_token(
            kid="k2", claims_override={"iss": "https://evil.example"}
        )
        jwk_aud, tok_aud = _generate_rsa_jwk_and_token(
            kid="k3", claims_override={"aud": "other-client"}
        )
        jwk_exp, tok_exp = _generate_rsa_jwk_and_token(
            kid="k4",
            claims_override={"exp": int((datetime.now(UTC) - timedelta(minutes=5)).timestamp())},
        )

        async def fake_fetch_jwks(timeout_seconds: float = 10.0) -> list[dict[str, Any]]:
            _ = timeout_seconds
            return [jwk_unverified, jwk_issuer, jwk_aud, jwk_exp]

        monkeypatch.setattr(security_module, "fetch_google_jwks", fake_fetch_jwks)

        for bad_token in (tok_unverified, tok_issuer, tok_aud, tok_exp):
            with pytest.raises(HTTPException) as exc_info:
                await verify_google_id_token(bad_token, client_id="google-client-123")
            assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_verify_google_id_token_validates_at_hash_with_access_token(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _google_jwks_cache.keys = []
        _google_jwks_cache.fetched_at = 0.0

        google_access_token = "ya29.test-google-access-token"
        digest = hashlib.sha256(google_access_token.encode("utf-8")).digest()
        at_hash = base64.urlsafe_b64encode(digest[:16]).rstrip(b"=").decode("ascii")

        jwk_dict, id_token_with_at_hash = _generate_rsa_jwk_and_token(
            kid="kid-at-hash",
            claims_override={"at_hash": at_hash},
        )

        async def fake_fetch_jwks(timeout_seconds: float = 10.0) -> list[dict[str, Any]]:
            _ = timeout_seconds
            return [jwk_dict]

        monkeypatch.setattr(security_module, "fetch_google_jwks", fake_fetch_jwks)

        claims = await verify_google_id_token(
            id_token_with_at_hash,
            client_id="google-client-123",
            access_token=google_access_token,
        )
        assert claims["sub"] == "google-sub-999"

        for bad_access_token in (None, "ya29.tampered-access-token"):
            with pytest.raises(HTTPException) as exc_info:
                await verify_google_id_token(
                    id_token_with_at_hash,
                    client_id="google-client-123",
                    access_token=bad_access_token,
                )
            assert exc_info.value.status_code == 401


class TestWorkerEmailTasks:
    """Validate ARQ email worker task invocations."""

    @pytest.mark.asyncio
    async def test_worker_email_tasks_dispatch_cleanly(
        self,
        test_settings: Settings,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        sent: list[tuple[str, str]] = []

        class SpySender(LoggingEmailSender):
            async def send_email(
                self,
                *,
                to_email: str,
                subject: str,
                text_body: str,
                html_body: str,
            ) -> None:
                sent.append((to_email, subject))
                await super().send_email(
                    to_email=to_email,
                    subject=subject,
                    text_body=text_body,
                    html_body=html_body,
                )

        monkeypatch.setattr(worker_module, "get_email_sender", lambda: SpySender(test_settings))

        await worker_module.send_verification_email_task(
            {},
            "alice@example.com",
            "Alice",
            "http://localhost:3000/verify-email?token=abc",
        )
        await worker_module.send_password_reset_email_task(
            {},
            "alice@example.com",
            "Alice",
            "http://localhost:3000/reset-password?token=def",
        )
        assert sent == [
            ("alice@example.com", "Verify your FinSight email address"),
            ("alice@example.com", "Reset your FinSight password"),
        ]
