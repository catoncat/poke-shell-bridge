from __future__ import annotations

from pathlib import Path


def resolve_path(path: str, workspace_root: Path) -> Path:
    raw = Path(path).expanduser()
    if raw.is_absolute():
        return raw.resolve(strict=False)
    return (workspace_root / raw).resolve(strict=False)


def resolve_cwd(cwd: str | None, workspace_root: Path) -> Path:
    if not cwd:
        return workspace_root
    return resolve_path(cwd, workspace_root)
