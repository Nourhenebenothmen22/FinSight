"""Pure ASGI middleware for request-scoped correlation and tenant context tracking."""

import uuid

import structlog
from starlette.types import ASGIApp, Message, Receive, Scope, Send

_HEADER_REQUEST_ID = b"x-request-id"
_HEADER_TENANT_ID = b"x-tenant-id"


class TenantContextMiddleware:
    """ASGI middleware initializing per-request tenant state and structlog contextvars.

    Note: Reads `X-Tenant-ID` only as an untrusted client target hint stored in
    `request.state.requested_tenant_id`. Authoritative `request.state.tenant_id`
    is set only after server-side membership verification in `get_tenant_context`.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return

        headers = dict(scope.get("headers", []))
        raw_request_id = headers.get(_HEADER_REQUEST_ID, b"").decode("latin-1").strip()
        request_id = raw_request_id[:64] if raw_request_id else uuid.uuid4().hex

        raw_tenant_hint = headers.get(_HEADER_TENANT_ID, b"").decode("latin-1").strip()
        requested_tenant_id: str | None = None
        if raw_tenant_hint:
            try:
                requested_tenant_id = str(uuid.UUID(raw_tenant_hint))
            except ValueError:
                requested_tenant_id = None

        state = scope.setdefault("state", {})
        state["request_id"] = request_id
        state["requested_tenant_id"] = requested_tenant_id
        state["tenant_id"] = None

        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=request_id, tenant_id=None)

        async def send_with_request_id(message: Message) -> None:
            if message["type"] == "http.response.start":
                raw_headers = list(message.get("headers", []))
                raw_headers.append((_HEADER_REQUEST_ID, request_id.encode("latin-1")))
                message["headers"] = raw_headers
            await send(message)

        try:
            await self.app(scope, receive, send_with_request_id)
        finally:
            structlog.contextvars.clear_contextvars()
