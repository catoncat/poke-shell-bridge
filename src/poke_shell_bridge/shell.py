from __future__ import annotations

import os
import shutil
import subprocess
import time
import uuid
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ShellRuntime:
    executable: str
    args: tuple[str, ...]
    mode: str
    source: str
    env: dict[str, str]
    path_prefixes: tuple[str, ...]

    @property
    def command_prefix(self) -> str:
        return " ".join((self.executable, *self.args))

    def describe(self) -> str:
        return f"{self.command_prefix} (mode={self.mode}, source={self.source})"


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


def _coerce_output_text(value: str | bytes | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


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


def _dedupe(items: list[str]) -> tuple[str, ...]:
    seen: set[str] = set()
    ordered: list[str] = []
    for item in items:
        if not item or item in seen:
            continue
        seen.add(item)
        ordered.append(item)
    return tuple(ordered)


def _resolve_shell_path(base_env: dict[str, str]) -> tuple[str, str]:
    candidates = [
        (base_env.get("POKE_BRIDGE_SHELL"), "env:POKE_BRIDGE_SHELL", True),
        (base_env.get("SHELL"), "env:SHELL", False),
        ("/bin/zsh", "platform:/bin/zsh", False),
        (shutil.which("zsh"), "which:zsh", False),
        ("/bin/bash", "platform:/bin/bash", False),
        (shutil.which("bash"), "which:bash", False),
        ("/bin/sh", "platform:/bin/sh", False),
        (shutil.which("sh"), "which:sh", False),
    ]
    for candidate, source, strict in candidates:
        if not candidate:
            continue
        resolved = shutil.which(candidate) if os.path.sep not in candidate else candidate
        if resolved and Path(resolved).exists():
            return resolved, source
        if strict:
            raise RuntimeError(f"Configured shell not found: {candidate}")
    raise RuntimeError("No usable shell found for poke-shell-bridge.")


def _resolve_shell_mode(base_env: dict[str, str]) -> str:
    mode = (base_env.get("POKE_BRIDGE_SHELL_MODE") or "login").strip().lower()
    if mode not in {"login", "exec"}:
        raise RuntimeError("POKE_BRIDGE_SHELL_MODE must be one of: login, exec")
    return mode


def _resolve_shell_args(executable: str, mode: str) -> tuple[str, ...]:
    shell_name = Path(executable).name.lower()
    if mode == "exec":
        return ("-c",)
    if shell_name == "fish":
        return ("-l", "-c")
    return ("-lc",)


def _path_key(base_env: dict[str, str]) -> str:
    for key in base_env:
        if key.lower() == "path":
            return key
    return "PATH"


def _expand_existing_paths(paths: list[str]) -> tuple[str, ...]:
    expanded: list[str] = []
    for raw in paths:
        candidate = str(Path(raw).expanduser())
        if Path(candidate).exists():
            expanded.append(candidate)
    return _dedupe(expanded)


def _default_path_prefixes(home: Path) -> tuple[str, ...]:
    return _expand_existing_paths(
        [
            str(home / ".codex/scripts"),
            str(home / ".bun/bin"),
            str(home / ".local/bin"),
            str(home / ".npm-global/bin"),
            str(home / "Library/pnpm"),
            str(home / "go/bin"),
            str(home / ".cargo/bin"),
            str(home / ".antigravity/antigravity/bin"),
            str(home / ".amp/bin"),
            str(home / "bin"),
            "/opt/homebrew/bin",
            "/opt/homebrew/sbin",
            "/usr/local/bin",
        ]
    )


def _resolve_path_prefixes(base_env: dict[str, str]) -> tuple[str, ...]:
    home = Path(base_env.get("HOME", "~")).expanduser()
    configured = base_env.get("POKE_BRIDGE_PATH_PREFIX", "")
    configured_paths = configured.split(os.pathsep) if configured else []
    return _dedupe([*_expand_existing_paths(configured_paths), *_default_path_prefixes(home)])


def _build_shell_env(base_env: dict[str, str], path_prefixes: tuple[str, ...]) -> dict[str, str]:
    env = dict(base_env)
    path_key = _path_key(env)
    existing = env.get(path_key, "")
    merged = _dedupe([*path_prefixes, *[entry for entry in existing.split(os.pathsep) if entry]])
    env[path_key] = os.pathsep.join(merged)
    return env


def resolve_shell_runtime(base_env: dict[str, str] | None = None) -> ShellRuntime:
    resolved_env = dict(base_env or os.environ)
    executable, source = _resolve_shell_path(resolved_env)
    mode = _resolve_shell_mode(resolved_env)
    args = _resolve_shell_args(executable, mode)
    path_prefixes = _resolve_path_prefixes(resolved_env)
    env = _build_shell_env(resolved_env, path_prefixes)
    return ShellRuntime(
        executable=executable,
        args=args,
        mode=mode,
        source=source,
        env=env,
        path_prefixes=path_prefixes,
    )


def _shell_result(runtime: ShellRuntime, cwd: Path) -> dict[str, object]:
    return {
        "shell": runtime.executable,
        "shell_args": list(runtime.args),
        "shell_mode": runtime.mode,
        "shell_source": runtime.source,
        "path_prefixes": list(runtime.path_prefixes),
        "resolved_cwd": str(cwd),
    }


def run_shell_command(
    *,
    command: str,
    cwd: Path,
    runtime: ShellRuntime,
    timeout: int,
    state_dir: Path,
    max_tail_lines: int,
    max_tail_bytes: int,
    timeout_suggestion: str | None = None,
) -> dict[str, object]:
    if not cwd.exists():
        return {
            "success": False,
            "error": {"code": "cwd_not_found", "message": f"Working directory not found: {cwd}"},
            **_shell_result(runtime, cwd),
        }
    if not cwd.is_dir():
        return {
            "success": False,
            "error": {"code": "cwd_not_directory", "message": f"Working directory is not a directory: {cwd}"},
            **_shell_result(runtime, cwd),
        }

    started = time.monotonic()
    try:
        completed = subprocess.run(
            [runtime.executable, *runtime.args, command],
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=timeout,
            env=runtime.env,
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
            "exit_code": completed.returncode,
            "duration_ms": duration_ms,
            "stdout": stdout_tail,
            "stderr": stderr_tail,
            "truncated": stdout_truncated or stderr_truncated,
            "stdout_path": stdout_path,
            "stderr_path": stderr_path,
            **_shell_result(runtime, cwd),
        }
    except subprocess.TimeoutExpired as exc:
        duration_ms = int((time.monotonic() - started) * 1000)
        stdout_text = _coerce_output_text(exc.stdout)
        stderr_text = _coerce_output_text(exc.stderr)
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
        result = {
            "success": False,
            "error": {"code": "timeout", "message": f"Command timed out after {timeout} seconds."},
            "command": command,
            "exit_code": None,
            "duration_ms": duration_ms,
            "stdout": stdout_tail,
            "stderr": stderr_tail,
            "truncated": stdout_truncated or stderr_truncated,
            "stdout_path": stdout_path,
            "stderr_path": stderr_path,
            **_shell_result(runtime, cwd),
        }
        if timeout_suggestion:
            result["suggested_tool"] = timeout_suggestion
        return result
    except Exception as exc:  # pragma: no cover - runtime guard
        return {
            "success": False,
            "error": {"code": "spawn_failed", "message": str(exc)},
            "command": command,
            **_shell_result(runtime, cwd),
        }
