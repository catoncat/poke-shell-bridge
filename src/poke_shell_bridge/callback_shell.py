from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from typing import AsyncGenerator

from .shell import ShellRuntime, run_shell_command
from .trace import emit_trace

FAST_COMPLETION_GRACE_SECONDS = 0.25


def _json_line(payload: dict[str, object]) -> str:
    return json.dumps(payload, ensure_ascii=False)


def _started_event(command: str, cwd: Path, runtime: ShellRuntime, timeout: int) -> str:
    return _json_line(
        {
            "event": "started",
            "command": command,
            "resolved_cwd": str(cwd),
            "shell": runtime.executable,
            "shell_args": list(runtime.args),
            "timeout_seconds": timeout,
        }
    )


def _heartbeat_event(command: str, elapsed_seconds: int) -> str:
    return _json_line(
        {
            "event": "heartbeat",
            "command": command,
            "elapsed_seconds": elapsed_seconds,
        }
    )


def _completed_event(result: dict[str, object]) -> str:
    return _json_line({"event": "completed", **result})


async def stream_shell_command(
    *,
    command: str,
    cwd: Path,
    runtime: ShellRuntime,
    timeout: int,
    state_dir: Path,
    max_tail_lines: int,
    max_tail_bytes: int,
    heartbeat_seconds: int,
) -> AsyncGenerator[str, None]:
    emit_trace(
        "shell.run",
        command_preview=command[:160],
        resolved_cwd=str(cwd),
        timeout_seconds=timeout,
    )
    task = asyncio.create_task(
        asyncio.to_thread(
            run_shell_command,
            command=command,
            cwd=cwd,
            runtime=runtime,
            timeout=timeout,
            state_dir=state_dir,
            max_tail_lines=max_tail_lines,
            max_tail_bytes=max_tail_bytes,
        )
    )
    started = time.monotonic()
    heartbeat_interval = max(heartbeat_seconds, 1)

    try:
        result = await asyncio.wait_for(
            asyncio.shield(task),
            timeout=FAST_COMPLETION_GRACE_SECONDS,
        )
    except asyncio.TimeoutError:
        event = _started_event(command, cwd, runtime, timeout)
        emit_trace("shell.started", command_preview=command[:160], timeout_seconds=timeout)
        yield event
    else:
        event = _completed_event(result)
        emit_trace(
            "shell.completed",
            command_preview=command[:160],
            success=result.get("success"),
            exit_code=result.get("exit_code"),
            duration_ms=result.get("duration_ms"),
        )
        yield event
        return

    while not task.done():
        try:
            result = await asyncio.wait_for(
                asyncio.shield(task),
                timeout=heartbeat_interval,
            )
        except asyncio.TimeoutError:
            elapsed_seconds = int(time.monotonic() - started)
            event = _heartbeat_event(command, elapsed_seconds)
            emit_trace(
                "shell.heartbeat",
                command_preview=command[:160],
                elapsed_seconds=elapsed_seconds,
            )
            yield event
        else:
            event = _completed_event(result)
            emit_trace(
                "shell.completed",
                command_preview=command[:160],
                success=result.get("success"),
                exit_code=result.get("exit_code"),
                duration_ms=result.get("duration_ms"),
            )
            yield event
            return

    result = await task
    event = _completed_event(result)
    emit_trace(
        "shell.completed",
        command_preview=command[:160],
        success=result.get("success"),
        exit_code=result.get("exit_code"),
        duration_ms=result.get("duration_ms"),
    )
    yield event
