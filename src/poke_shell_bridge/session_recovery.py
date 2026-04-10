from __future__ import annotations

import anyio
from typing import Any

from mcp.server.streamable_http import GET_STREAM_KEY, LAST_EVENT_ID_HEADER, MCP_SESSION_ID_HEADER

from .trace import emit_trace


def _decode_headers(raw_headers: list[tuple[bytes, bytes]]) -> dict[str, str]:
    return {
        key.decode("latin-1").lower(): value.decode("latin-1")
        for key, value in raw_headers
    }


class SSEStreamTakeoverMiddleware:
    def __init__(self, app: Any, *, transport_path: str = "/mcp") -> None:
        self.app = app
        self.transport_path = transport_path
        self._endpoint = self._find_endpoint(app, transport_path)

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if self._should_attempt_takeover(scope):
            await self._take_over_existing_stream(scope)
        await self.app(scope, receive, send)

    def _find_endpoint(self, app: Any, path: str) -> Any | None:
        for route in getattr(app, "routes", []):
            if getattr(route, "path", None) == path:
                return getattr(route, "endpoint", None)
        return None

    def _should_attempt_takeover(self, scope: dict[str, Any]) -> bool:
        if scope.get("type") != "http":
            return False
        if scope.get("method") != "GET":
            return False
        if scope.get("path") != self.transport_path:
            return False
        return True

    async def _take_over_existing_stream(self, scope: dict[str, Any]) -> None:
        session_manager = getattr(self._endpoint, "session_manager", None)
        if session_manager is None:
            return

        headers = _decode_headers(scope.get("headers", []))
        session_id = headers.get(MCP_SESSION_ID_HEADER)
        if not session_id:
            return
        if headers.get(LAST_EVENT_ID_HEADER):
            return

        transport = session_manager._server_instances.get(session_id)
        if transport is None or transport.is_terminated:
            return
        if GET_STREAM_KEY not in getattr(transport, "_request_streams", {}):
            return

        emit_trace(
            "sse.takeover",
            session_id=session_id,
            path=self.transport_path,
        )
        transport.close_standalone_sse_stream()
        await anyio.sleep(0)
