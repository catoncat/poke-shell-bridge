from __future__ import annotations

from fastmcp import FastMCP

from .bash_exec import run_bash_exec
from .config import (
    APP_NAME,
    COMMAND_TIMEOUT,
    HOST,
    MAX_OUTPUT_TAIL_BYTES,
    MAX_OUTPUT_TAIL_LINES,
    MAX_READ_BYTES,
    MAX_READ_LINES,
    PORT,
    SHELL,
    STATE_DIR,
    WORKSPACE_ROOT,
    ensure_runtime_directories,
)
from .files import edit_file, read_file, write_file
from .pathing import resolve_cwd, resolve_path

mcp = FastMCP(
    APP_NAME,
    instructions=(
        "Local MCP bridge for a dedicated Mac sandbox. "
        "Use read/write/edit for file operations and bash_exec for shell commands. "
        "Relative paths resolve against workspace_root; absolute paths are also allowed."
    ),
)


@mcp.tool
def read(path: str, offset: int | None = None, limit: int | None = None) -> dict[str, object]:
    target = resolve_path(path, WORKSPACE_ROOT)
    return read_file(
        target,
        offset=offset,
        limit=limit,
        max_lines=MAX_READ_LINES,
        max_bytes=MAX_READ_BYTES,
    )


@mcp.tool
def write(path: str, content: str) -> dict[str, object]:
    target = resolve_path(path, WORKSPACE_ROOT)
    return write_file(target, content=content)


@mcp.tool
def edit(path: str, oldText: str, newText: str) -> dict[str, object]:
    target = resolve_path(path, WORKSPACE_ROOT)
    return edit_file(target, old_text=oldText, new_text=newText)


@mcp.tool
def bash_exec(command: str, cwd: str | None = None, timeout: int | None = None) -> dict[str, object]:
    resolved_cwd = resolve_cwd(cwd, WORKSPACE_ROOT)
    return run_bash_exec(
        command=command,
        cwd=resolved_cwd,
        shell=SHELL,
        timeout=timeout or COMMAND_TIMEOUT,
        state_dir=STATE_DIR,
        max_tail_lines=MAX_OUTPUT_TAIL_LINES,
        max_tail_bytes=MAX_OUTPUT_TAIL_BYTES,
    )


def main() -> None:
    ensure_runtime_directories()
    print(f"Starting {APP_NAME} on {HOST}:{PORT}")
    print(f"workspace_root={WORKSPACE_ROOT}")
    print(f"state_dir={STATE_DIR}")
    mcp.run(
        transport="http",
        host=HOST,
        port=PORT,
        path="/mcp",
        stateless_http=True,
    )


if __name__ == "__main__":
    main()
