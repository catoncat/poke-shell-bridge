from __future__ import annotations

import os
from pathlib import Path

APP_NAME = "poke-m1-bridge"
HOST = os.environ.get("POKE_BRIDGE_HOST", "127.0.0.1")
PORT = int(os.environ.get("POKE_BRIDGE_PORT", "8765"))
WORKSPACE_ROOT = Path(
    os.environ.get("POKE_BRIDGE_WORKSPACE_ROOT", "~/work/agent-sandbox")
).expanduser().resolve()
STATE_DIR = Path(
    os.environ.get("POKE_BRIDGE_STATE_DIR", "~/.poke-m1-bridge")
).expanduser().resolve()
SHELL = os.environ.get("POKE_BRIDGE_SHELL", "/bin/zsh")
COMMAND_TIMEOUT = int(os.environ.get("POKE_BRIDGE_COMMAND_TIMEOUT", "30"))
MAX_READ_LINES = int(os.environ.get("POKE_BRIDGE_MAX_READ_LINES", "200"))
MAX_READ_BYTES = int(os.environ.get("POKE_BRIDGE_MAX_READ_BYTES", str(32 * 1024)))
MAX_OUTPUT_TAIL_LINES = int(os.environ.get("POKE_BRIDGE_MAX_OUTPUT_TAIL_LINES", "200"))
MAX_OUTPUT_TAIL_BYTES = int(
    os.environ.get("POKE_BRIDGE_MAX_OUTPUT_TAIL_BYTES", str(32 * 1024))
)


def ensure_runtime_directories() -> None:
    WORKSPACE_ROOT.mkdir(parents=True, exist_ok=True)
    (STATE_DIR / "runs").mkdir(parents=True, exist_ok=True)
