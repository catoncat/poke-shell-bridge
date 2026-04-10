from __future__ import annotations

import subprocess
import time
import uuid
from pathlib import Path


def _tail_output(text: str, *, max_lines: int, max_bytes: int) -> tuple[str, bool]:
    truncated = False
    lines = text.splitlines()
    if len(lines) > max_lines:
        lines = lines[-max_lines:]
        truncated = True
    joined = "\n".join(lines)
    encoded = joined.encode("utf-8")
    if len(encoded) > max_bytes:
        joined = encoded[-max_bytes:].decode("utf-8", errors="ignore")
        truncated = True
    return joined, truncated


def _persist_outputs(
    *,
    state_dir: Path,
    stdout_text: str,
    stderr_text: str,
) -> tuple[str, str]:
    run_dir = state_dir / "runs" / f"{int(time.time())}-{uuid.uuid4().hex[:8]}"
    run_dir.mkdir(parents=True, exist_ok=True)
    stdout_path = run_dir / "stdout.log"
    stderr_path = run_dir / "stderr.log"
    stdout_path.write_text(stdout_text, encoding="utf-8")
    stderr_path.write_text(stderr_text, encoding="utf-8")
    return str(stdout_path), str(stderr_path)


def run_bash_exec(
    *,
    command: str,
    cwd: Path,
    shell: str,
    timeout: int,
    state_dir: Path,
    max_tail_lines: int,
    max_tail_bytes: int,
) -> dict[str, object]:
    if not cwd.exists():
        return {
            "success": False,
            "error": {"code": "cwd_not_found", "message": f"Working directory not found: {cwd}"},
            "resolved_cwd": str(cwd),
        }
    if not cwd.is_dir():
        return {
            "success": False,
            "error": {"code": "cwd_not_directory", "message": f"Working directory is not a directory: {cwd}"},
            "resolved_cwd": str(cwd),
        }

    started = time.monotonic()
    try:
        completed = subprocess.run(
            [shell, "-lc", command],
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        duration_ms = int((time.monotonic() - started) * 1000)
        stdout_tail, stdout_truncated = _tail_output(
            completed.stdout,
            max_lines=max_tail_lines,
            max_bytes=max_tail_bytes,
        )
        stderr_tail, stderr_truncated = _tail_output(
            completed.stderr,
            max_lines=max_tail_lines,
            max_bytes=max_tail_bytes,
        )
        stdout_path = None
        stderr_path = None
        if stdout_truncated or stderr_truncated:
            stdout_path, stderr_path = _persist_outputs(
                state_dir=state_dir,
                stdout_text=completed.stdout,
                stderr_text=completed.stderr,
            )

        return {
            "success": completed.returncode == 0,
            "command": command,
            "resolved_cwd": str(cwd),
            "exit_code": completed.returncode,
            "duration_ms": duration_ms,
            "stdout": stdout_tail,
            "stderr": stderr_tail,
            "truncated": stdout_truncated or stderr_truncated,
            "stdout_path": stdout_path,
            "stderr_path": stderr_path,
        }
    except subprocess.TimeoutExpired as exc:
        duration_ms = int((time.monotonic() - started) * 1000)
        stdout_text = exc.stdout or ""
        stderr_text = exc.stderr or ""
        stdout_tail, stdout_truncated = _tail_output(
            stdout_text,
            max_lines=max_tail_lines,
            max_bytes=max_tail_bytes,
        )
        stderr_tail, stderr_truncated = _tail_output(
            stderr_text,
            max_lines=max_tail_lines,
            max_bytes=max_tail_bytes,
        )
        stdout_path, stderr_path = _persist_outputs(
            state_dir=state_dir,
            stdout_text=stdout_text,
            stderr_text=stderr_text,
        )
        return {
            "success": False,
            "error": {"code": "timeout", "message": f"Command timed out after {timeout} seconds."},
            "command": command,
            "resolved_cwd": str(cwd),
            "exit_code": None,
            "duration_ms": duration_ms,
            "stdout": stdout_tail,
            "stderr": stderr_tail,
            "truncated": stdout_truncated or stderr_truncated,
            "stdout_path": stdout_path,
            "stderr_path": stderr_path,
        }
    except Exception as exc:  # pragma: no cover - runtime guard
        return {
            "success": False,
            "error": {"code": "spawn_failed", "message": str(exc)},
            "command": command,
            "resolved_cwd": str(cwd),
        }
