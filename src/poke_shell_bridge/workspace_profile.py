from __future__ import annotations

import os
import shutil
import subprocess
import tomllib
from pathlib import Path

from .shell import ShellRuntime


def _probe(command: list[str], cwd: Path, env: dict[str, str]) -> dict[str, object]:
    try:
        completed = subprocess.run(
            command,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=5,
            env=env,
        )
    except Exception as exc:
        return {"ok": False, "error": str(exc)}
    return {
        "ok": completed.returncode == 0,
        "exit_code": completed.returncode,
        "stdout": completed.stdout.strip(),
        "stderr": completed.stderr.strip(),
    }


def _load_codex_trust_entries() -> dict[str, str]:
    config_path = Path.home() / ".codex" / "config.toml"
    if not config_path.exists():
        return {}
    try:
        data = tomllib.loads(config_path.read_text())
    except Exception:
        return {}
    projects = data.get("projects", {})
    return {
        str(path): str(config.get("trust_level", ""))
        for path, config in projects.items()
        if isinstance(config, dict)
    }


def _matching_trust_entries(cwd: Path, trust_entries: dict[str, str]) -> list[dict[str, str]]:
    matches: list[dict[str, str]] = []
    cwd_text = str(cwd)
    for path, level in trust_entries.items():
        if cwd_text == path or cwd_text.startswith(f"{path}{os.sep}"):
            matches.append({"path": path, "trust_level": level})
    return sorted(matches, key=lambda item: len(item["path"]), reverse=True)


def collect_workspace_profile(cwd: Path, runtime: ShellRuntime) -> dict[str, object]:
    git_path = shutil.which("git", path=runtime.env.get("PATH"))
    codex_path = shutil.which("codex", path=runtime.env.get("PATH"))
    git_root = _probe(["git", "rev-parse", "--show-toplevel"], cwd, runtime.env)
    git_status = _probe(["git", "status", "--short"], cwd, runtime.env)
    codex_version = _probe(["codex", "--version"], cwd, runtime.env)
    trust_entries = _load_codex_trust_entries()
    return {
        "resolved_cwd": str(cwd),
        "exists": cwd.exists(),
        "is_dir": cwd.is_dir(),
        "shell": runtime.executable,
        "shell_args": list(runtime.args),
        "shell_mode": runtime.mode,
        "shell_source": runtime.source,
        "path_prefixes": list(runtime.path_prefixes),
        "git_path": git_path,
        "codex_path": codex_path,
        "git_root": git_root,
        "git_status": git_status,
        "codex_version": codex_version,
        "trusted_entries": _matching_trust_entries(cwd, trust_entries),
    }
