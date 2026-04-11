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

from fastmcp import Context
from fastmcp.server.dependencies import get_http_request
from fastmcp.server.middleware.middleware import Middleware

from .trace import emit_trace

CALLBACK_STATE_KEY = "__poke_callback_context__"
FINAL_EVENT_NAME = "completed"
FINAL_RETRY_ATTEMPTS = 3
FINAL_RETRY_CAP_MS = 2000


@dataclass
class CallbackContext:
    callback_token: Optional[str]
    callback_url: Optional[str]


_callback_context: ContextVar[Optional[CallbackContext]] = ContextVar(
    "_callback_context", default=None
)
_background_tasks: set[asyncio.Task[Any]] = set()


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


async def _resolve_callback_context(args: tuple[Any, ...], kwargs: dict[str, Any]) -> CallbackContext:
    fastmcp_ctx = _find_fastmcp_context(args, kwargs)
    if fastmcp_ctx is not None:
        state = await fastmcp_ctx.get_state(CALLBACK_STATE_KEY)
        if isinstance(state, CallbackContext):
            return state
        if isinstance(state, dict):
            return CallbackContext(
                callback_token=state.get("callback_token"),
                callback_url=state.get("callback_url"),
            )
    return _callback_context.get() or CallbackContext(None, None)


def _find_fastmcp_context(args: tuple[Any, ...], kwargs: dict[str, Any]) -> Context | None:
    for value in (*args, *kwargs.values()):
        if isinstance(value, Context):
            return value
    return None


def _event_name(content: str) -> str | None:
    try:
        payload = json.loads(content)
    except Exception:
        return None
    if not isinstance(payload, dict):
        return None
    event = payload.get("event")
    return str(event) if isinstance(event, str) else None


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
    event_name: str | None,
) -> dict[str, Any]:
    is_final = event_name == FINAL_EVENT_NAME or not has_more
    attempts = 0

    while True:
        emit_trace(
            "callback.send",
            callback_host=_callback_host(url),
            has_more=has_more,
            event_name=event_name,
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
            retry_after_ms = int(result.get("retryAfterMs", 60_000))
            if not is_final:
                emit_trace(
                    "callback.drop",
                    callback_host=_callback_host(url),
                    event_name=event_name,
                    reason="rate_limited_intermediate",
                    retry_after_ms=retry_after_ms,
                )
                result["_dropped"] = True
                return result

            attempts += 1
            if attempts > FINAL_RETRY_ATTEMPTS:
                emit_trace(
                    "callback.drop",
                    callback_host=_callback_host(url),
                    event_name=event_name,
                    reason="rate_limited_final",
                    retry_after_ms=retry_after_ms,
                )
                result["_dropped"] = True
                return result

            sleep_ms = min(retry_after_ms, FINAL_RETRY_CAP_MS)
            emit_trace(
                "callback.retry",
                callback_host=_callback_host(url),
                event_name=event_name,
                retry_after_ms=retry_after_ms,
                sleep_ms=sleep_ms,
                attempt=attempts,
            )
            await asyncio.sleep(sleep_ms / 1000)
            continue

        emit_trace(
            "callback.result",
            callback_host=_callback_host(url),
            has_more=has_more,
            event_name=event_name,
            status=result.get("_status"),
            has_next_token="nextToken" in result and result.get("nextToken") is not None,
            network_error=result.get("_network_error"),
        )
        return result


def _register_background_task(task: asyncio.Task[Any], callback_url: str) -> None:
    callback_host = _callback_host(callback_url)
    _background_tasks.add(task)
    emit_trace(
        "callback.task_spawned",
        callback_host=callback_host,
        active_tasks=len(_background_tasks),
    )

    def _finalize(done_task: asyncio.Task[Any]) -> None:
        _background_tasks.discard(done_task)
        if done_task.cancelled():
            emit_trace(
                "callback.task_done",
                callback_host=callback_host,
                cancelled=True,
                active_tasks=len(_background_tasks),
            )
            return
        exc = done_task.exception()
        emit_trace(
            "callback.task_done",
            callback_host=callback_host,
            cancelled=False,
            active_tasks=len(_background_tasks),
            error=str(exc)[:200] if exc is not None else None,
        )
        if exc is not None:
            emit_trace("callback.error", error=str(exc)[:200])

    task.add_done_callback(_finalize)


def with_callbacks(
    handler: Callable[..., AsyncGenerator[str, None]],
) -> Callable[..., Any]:
    @functools.wraps(handler)
    async def wrapper(*args: Any, **kwargs: Any) -> str:
        ctx = await _resolve_callback_context(args, kwargs)
        callback_token = ctx.callback_token
        callback_url = ctx.callback_url
        emit_trace(
            "callback.context",
            callback_host=_callback_host(callback_url),
            token_present=bool(callback_token),
            url_present=bool(callback_url),
        )

        gen = handler(*args, **kwargs)
        first = await gen.__anext__()

        if callback_token and callback_url:

            async def _background() -> None:
                current_token = callback_token
                async for event in gen:
                    event_name = _event_name(event)
                    has_more = event_name != FINAL_EVENT_NAME
                    sent = await _send_callback(
                        url=callback_url,
                        token=current_token,
                        content=event,
                        has_more=has_more,
                        event_name=event_name,
                    )
                    next_token = sent.get("nextToken")
                    if next_token:
                        current_token = str(next_token)
                    elif has_more:
                        emit_trace(
                            "callback.no_next_token",
                            callback_host=_callback_host(callback_url),
                            event_name=event_name,
                            has_more=has_more,
                            status=sent.get("_status"),
                            network_error=sent.get("_network_error"),
                            dropped=sent.get("_dropped"),
                        )
                    if not has_more:
                        return

            task = asyncio.create_task(_background())
            _register_background_task(task, callback_url)
        else:
            await gen.aclose()

        return first

    return wrapper


class PokeCallbackMiddleware(Middleware):
    async def on_request(self, context: Any, call_next: Any) -> Any:
        fastmcp_ctx = context.fastmcp_context
        if fastmcp_ctx is not None:
            request = get_http_request()
            await fastmcp_ctx.set_state(
                CALLBACK_STATE_KEY,
                CallbackContext(
                    callback_token=request.headers.get("x-poke-callback-token"),
                    callback_url=request.headers.get("x-poke-callback-url"),
                ),
                serializable=False,
            )
        return await call_next(context)
