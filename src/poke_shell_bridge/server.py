from __future__ import annotations

from fastmcp import FastMCP

from .shell import run_shell_command
from .config import (
    APP_NAME,
    COMMAND_TIMEOUT,
    HOST,
    MAX_OUTPUT_TAIL_BYTES,
    MAX_OUTPUT_TAIL_LINES,
    MAX_READ_BYTES,
    MAX_READ_LINES,
    PORT,
    SHELL_RUNTIME,
    STATE_DIR,
    WORKSPACE_ROOT,
    ensure_runtime_directories,
)
from .files import edit_file, read_file, write_file
from .pathing import resolve_cwd, resolve_path

mcp = FastMCP(
    APP_NAME,
    instructions=(
        "Local MCP shell bridge for a computer exposed to Poke. "
        "Use read/write/edit for file operations and shell for shell commands. "
        "Relative paths resolve against workspace_root; absolute paths are also allowed. "
        f"The shell tool runs via {SHELL_RUNTIME.describe()}."
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
def shell(command: str, cwd: str | None = None, timeout: int | None = None) -> dict[str, object]:
    resolved_cwd = resolve_cwd(cwd, WORKSPACE_ROOT)
    return run_shell_command(
        command=command,
        cwd=resolved_cwd,
        runtime=SHELL_RUNTIME,
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
    print(f"shell_runtime={SHELL_RUNTIME.describe()}")
    if SHELL_RUNTIME.path_prefixes:
        print(f"path_prefixes={list(SHELL_RUNTIME.path_prefixes)}")
    mcp.run(
        transport="http",
        host=HOST,
        port=PORT,
        path="/mcp",
        stateless_http=True,
    )


if __name__ == "__main__":
    main()
