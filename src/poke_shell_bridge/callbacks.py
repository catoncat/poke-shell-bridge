from __future__ import annotations

import asyncio
import functools
import json
import urllib.error
import urllib.request
from contextvars import ContextVar, Token
from dataclasses import dataclass
from typing import Any, AsyncGenerator, Callable, Optional
from urllib.parse import urlparse

from .trace import emit_trace


@dataclass
class CallbackContext:
    callback_token: Optional[str]
    callback_url: Optional[str]


_callback_context: ContextVar[Optional[CallbackContext]] = ContextVar(
    "_callback_context", default=None
)


def set_callback_context(ctx: CallbackContext) -> Token[Optional[CallbackContext]]:
    return _callback_context.set(ctx)


def reset_callback_context(token: Token[Optional[CallbackContext]]) -> None:
    _callback_context.reset(token)


def _callback_host(url: str | None) -> str | None:
    if not url:
        return None
    try:
        return urlparse(url).netloc or None
    except Exception:
        return None


def _send_callback_sync(
    *,
    url: str,
    token: str,
    content: str,
    has_more: bool,
) -> dict[str, Any]:
    body = json.dumps({"content": content, "hasMore": has_more}).encode()
    req = urllib.request.Request(
        url,
        data=body,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req) as resp:
            raw = resp.read().decode()
            payload = json.loads(raw) if raw else {}
            if not isinstance(payload, dict):
                payload = {}
            payload["_status"] = getattr(resp, "status", 200)
            return payload
    except urllib.error.HTTPError as exc:
        raw = ""
        try:
            raw = exc.read().decode()
            payload = json.loads(raw) if raw else {}
            if not isinstance(payload, dict):
                payload = {}
        except Exception:
            payload = {}
        payload["_status"] = exc.code
        if exc.code == 429:
            payload["_retry"] = True
            payload["retryAfterMs"] = payload.get("retryAfterMs", 60_000)
        return payload
    except urllib.error.URLError as exc:
        return {"_network_error": str(exc.reason) if getattr(exc, "reason", None) else str(exc)}


async def _send_callback(
    *,
    url: str,
    token: str,
    content: str,
    has_more: bool,
) -> dict[str, Any]:
    while True:
        emit_trace(
            "callback.send",
            callback_host=_callback_host(url),
            has_more=has_more,
            content_preview=str(content).replace("\n", "\\n")[:160],
        )
        result = await asyncio.to_thread(
            _send_callback_sync,
            url=url,
            token=token,
            content=content,
            has_more=has_more,
        )
        if result.get("_retry"):
            delay_ms = int(result.get("retryAfterMs", 60_000))
            emit_trace(
                "callback.retry",
                callback_host=_callback_host(url),
                retry_after_ms=delay_ms,
            )
            await asyncio.sleep(delay_ms / 1000)
            continue

        emit_trace(
            "callback.result",
            callback_host=_callback_host(url),
            has_more=has_more,
            status=result.get("_status"),
            has_next_token="nextToken" in result and result.get("nextToken") is not None,
            network_error=result.get("_network_error"),
        )
        return result


def with_callbacks(
    handler: Callable[..., AsyncGenerator[str, None]],
) -> Callable[..., Any]:
    @functools.wraps(handler)
    async def wrapper(*args: Any, **kwargs: Any) -> str:
        ctx = _callback_context.get()
        callback_token = ctx.callback_token if ctx else None
        callback_url = ctx.callback_url if ctx else None

        gen = handler(*args, **kwargs)
        first = await gen.__anext__()

        if callback_token and callback_url:

            async def _background() -> None:
                current_token = callback_token
                try:
                    buffered = await gen.__anext__()
                except StopAsyncIteration:
                    return

                while True:
                    try:
                        next_val = await gen.__anext__()
                    except StopAsyncIteration:
                        await _send_callback(
                            url=callback_url,
                            token=current_token,
                            content=buffered,
                            has_more=False,
                        )
                        return

                    sent = await _send_callback(
                        url=callback_url,
                        token=current_token,
                        content=buffered,
                        has_more=True,
                    )
                    next_token = sent.get("nextToken")
                    if next_token:
                        current_token = str(next_token)
                    else:
                        emit_trace(
                            "callback.no_next_token",
                            callback_host=_callback_host(callback_url),
                            has_more=True,
                            status=sent.get("_status"),
                            network_error=sent.get("_network_error"),
                        )
                    buffered = next_val

            task = asyncio.create_task(_background())
            task.add_done_callback(_log_task_exception)
        else:
            await gen.aclose()

        return first

    return wrapper


def _log_task_exception(task: asyncio.Task[Any]) -> None:
    if task.cancelled():
        return
    exc = task.exception()
    if exc is not None:
        emit_trace("callback.error", error=str(exc)[:200])


class PokeCallbackMiddleware:
    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = dict(scope.get("headers", []))
        cb_token = headers.get(b"x-poke-callback-token")
        cb_url = headers.get(b"x-poke-callback-url")

        ctx = CallbackContext(
            callback_token=cb_token.decode() if cb_token else None,
            callback_url=cb_url.decode() if cb_url else None,
        )
        tok = _callback_context.set(ctx)
        try:
            await self.app(scope, receive, send)
        finally:
            _callback_context.reset(tok)
