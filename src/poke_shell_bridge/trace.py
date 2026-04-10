from __future__ import annotations

import json
import os
import time
from typing import Any
from urllib.parse import urlparse


TRACE_ENABLED = os.environ.get("POKE_BRIDGE_TRACE", "1").strip().lower() not in {
    "0",
    "false",
    "no",
    "off",
}


def _clip_text(value: object, limit: int = 160) -> str | None:
    if value is None:
        return None
    text = str(value).replace("\n", "\\n")
    if len(text) <= limit:
        return text
    return f"{text[:limit]}…"


def _decode_headers(raw_headers: list[tuple[bytes, bytes]]) -> dict[str, str]:
    return {
        key.decode("latin-1").lower(): value.decode("latin-1")
        for key, value in raw_headers
    }


def _body_fields(body: bytes, content_type: str) -> dict[str, object]:
    if "application/json" not in content_type.lower():
        return {"body_bytes": len(body)}
    try:
        payload = json.loads(body.decode("utf-8"))
    except Exception:
        return {"body_bytes": len(body), "body_json": "invalid"}

    if not isinstance(payload, dict):
        return {"body_bytes": len(body), "body_json": type(payload).__name__}

    result: dict[str, object] = {"body_bytes": len(body)}
    method = payload.get("method")
    request_id = payload.get("id")
    params = payload.get("params") if isinstance(payload.get("params"), dict) else {}

    if method is not None:
        result["rpc_method"] = method
    if request_id is not None:
        result["rpc_id"] = request_id

    if method == "tools/call":
        tool_name = params.get("name")
        arguments = params.get("arguments") if isinstance(params.get("arguments"), dict) else {}
        result["tool_name"] = tool_name
        if "command" in arguments:
            result["command_preview"] = _clip_text(arguments.get("command"))
        if "path" in arguments:
            result["path"] = _clip_text(arguments.get("path"), limit=120)
        if "cwd" in arguments:
            result["cwd"] = _clip_text(arguments.get("cwd"), limit=120)
    elif method == "initialize":
        result["protocol_version_param"] = params.get("protocolVersion")
        client_info = params.get("clientInfo") if isinstance(params.get("clientInfo"), dict) else {}
        result["client_name"] = client_info.get("name")
    return result


def emit_trace(event: str, **fields: object) -> None:
    if not TRACE_ENABLED:
        return
    payload = {
        "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
        "event": event,
        **{key: value for key, value in fields.items() if value is not None},
    }
    print(f"TRACE {json.dumps(payload, ensure_ascii=False)}", flush=True)


class MCPTraceMiddleware:
    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope.get("type") != "http" or not TRACE_ENABLED:
            await self.app(scope, receive, send)
            return

        method = scope.get("method", "")
        path = scope.get("path", "")
        headers = _decode_headers(scope.get("headers", []))
        client = scope.get("client") or ("", "")
        body_messages, body = await _read_body(receive, method)
        body_fields = _body_fields(body, headers.get("content-type", ""))
        status_code: int | None = None

        emit_trace(
            "http.request",
            http_method=method,
            path=path,
            client_ip=client[0] or None,
            session_id=headers.get("mcp-session-id"),
            protocol_version=headers.get("mcp-protocol-version"),
            callback_headers=bool(
                headers.get("x-poke-callback-token") and headers.get("x-poke-callback-url")
            ),
            callback_host=_callback_host(headers.get("x-poke-callback-url")),
            accept=_clip_text(headers.get("accept"), limit=120),
            **body_fields,
        )

        replay_receive = _replay_receive_factory(body_messages, receive)

        async def send_wrapper(message: dict[str, Any]) -> None:
            nonlocal status_code
            if message.get("type") == "http.response.start":
                status_code = message.get("status")
            await send(message)

        try:
            await self.app(scope, replay_receive, send_wrapper)
        except Exception as exc:
            emit_trace(
                "http.error",
                http_method=method,
                path=path,
                status_code=status_code,
                error=_clip_text(exc),
            )
            raise

        emit_trace(
            "http.response",
            http_method=method,
            path=path,
            status_code=status_code,
            rpc_method=body_fields.get("rpc_method"),
            rpc_id=body_fields.get("rpc_id"),
            tool_name=body_fields.get("tool_name"),
        )


async def _read_body(receive: Any, method: str) -> tuple[list[dict[str, Any]], bytes]:
    if method not in {"POST", "PUT", "PATCH"}:
        return [], b""

    messages: list[dict[str, Any]] = []
    chunks: list[bytes] = []
    while True:
        message = await receive()
        messages.append(message)
        if message.get("type") != "http.request":
            break
        chunks.append(message.get("body", b""))
        if not message.get("more_body", False):
            break
    return messages, b"".join(chunks)


def _replay_receive_factory(messages: list[dict[str, Any]], original_receive: Any) -> Any:
    if not messages:
        return original_receive

    state = {"index": 0}

    async def replay_receive() -> dict[str, Any]:
        if state["index"] < len(messages):
            message = messages[state["index"]]
            state["index"] += 1
            return message
        return await original_receive()

    return replay_receive


def _callback_host(callback_url: str | None) -> str | None:
    if not callback_url:
        return None
    try:
        parsed = urlparse(callback_url)
    except Exception:
        return None
    return parsed.netloc or None
