from __future__ import annotations

import os
from pathlib import Path

from .shell import resolve_shell_runtime

APP_NAME = "poke-shell-bridge"
HOST = os.environ.get("POKE_BRIDGE_HOST", "127.0.0.1")
PORT = int(os.environ.get("POKE_BRIDGE_PORT", "8765"))
WORKSPACE_ROOT = Path(
    os.environ.get("POKE_BRIDGE_WORKSPACE_ROOT", "~/workspace")
).expanduser().resolve()
STATE_DIR = Path(
    os.environ.get("POKE_BRIDGE_STATE_DIR", "~/.poke-shell-bridge")
).expanduser().resolve()
SHELL_RUNTIME = resolve_shell_runtime()
COMMAND_TIMEOUT = int(os.environ.get("POKE_BRIDGE_COMMAND_TIMEOUT", "30"))
MAX_READ_LINES = int(os.environ.get("POKE_BRIDGE_MAX_READ_LINES", "200"))
MAX_READ_BYTES = int(os.environ.get("POKE_BRIDGE_MAX_READ_BYTES", str(32 * 1024)))
MAX_OUTPUT_TAIL_LINES = int(os.environ.get("POKE_BRIDGE_MAX_OUTPUT_TAIL_LINES", "200"))
MAX_OUTPUT_TAIL_BYTES = int(
    os.environ.get("POKE_BRIDGE_MAX_OUTPUT_TAIL_BYTES", str(32 * 1024))
)
CALLBACK_HEARTBEAT_SECONDS = int(
    os.environ.get("POKE_BRIDGE_CALLBACK_HEARTBEAT_SECONDS", "5")
)


def ensure_runtime_directories() -> None:
    WORKSPACE_ROOT.mkdir(parents=True, exist_ok=True)
    (STATE_DIR / "runs").mkdir(parents=True, exist_ok=True)
