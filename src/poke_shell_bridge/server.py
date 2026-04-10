from __future__ import annotations

from typing import Annotated

import uvicorn
from fastmcp import FastMCP
from pydantic import Field
from poke.mcp import PokeCallbackMiddleware, with_callbacks

from .callback_shell import stream_shell_command
from .config import (
    APP_NAME,
    CALLBACK_HEARTBEAT_SECONDS,
    HOST,
    MAX_OUTPUT_TAIL_BYTES,
    MAX_OUTPUT_TAIL_LINES,
    MAX_READ_BYTES,
    MAX_READ_LINES,
    PORT,
    SHELL_TIMEOUT,
    SHELL_RUNTIME,
    STATE_DIR,
    WORKSPACE_ROOT,
    ensure_runtime_directories,
)
from .files import edit_file, read_file, write_file
from .pathing import resolve_cwd, resolve_path
from .session_recovery import SSEStreamTakeoverMiddleware
from .trace import MCPTraceMiddleware
from .workspace_profile import collect_workspace_profile

mcp = FastMCP(
    APP_NAME,
    instructions=(
        "Computer control MCP server for a computer exposed to Poke. "
        "Use read/write/edit for file operations inside the workspace. "
        "Use shell for command execution. "
        f"It always runs through Poke callbacks and uses a default timeout of {SHELL_TIMEOUT} seconds unless overridden per call. "
        "Fast commands complete immediately; longer commands first emit started, then heartbeat updates, then completed. "
        "Use workspace_profile before git-aware tools like codex review, git diff, or gh. "
        "Relative paths resolve against workspace_root; absolute paths are also allowed. "
        f"The shell tool runs via {SHELL_RUNTIME.describe()}."
    ),
)


@mcp.tool(
    description=(
        "Read a text file from the workspace or an absolute path. "
        "Use this before edit when you need exact context, line offsets, or a bounded slice of a file."
    )
)
def read(
    path: Annotated[
        str,
        Field(description="Path to a text file. Relative paths resolve against the workspace root."),
    ],
    offset: Annotated[
        int | None,
        Field(description="Optional 0-based line offset to start reading from."),
    ] = None,
    limit: Annotated[
        int | None,
        Field(description="Optional maximum number of lines to return from the offset."),
    ] = None,
) -> dict[str, object]:
    target = resolve_path(path, WORKSPACE_ROOT)
    return read_file(
        target,
        offset=offset,
        limit=limit,
        max_lines=MAX_READ_LINES,
        max_bytes=MAX_READ_BYTES,
    )


@mcp.tool(
    description=(
        "Write full text content to a file, creating parent directories when needed. "
        "Use this for complete file replacement; use edit for precise in-place changes."
    )
)
def write(
    path: Annotated[
        str,
        Field(description="Target file path. Relative paths resolve against the workspace root."),
    ],
    content: Annotated[
        str,
        Field(description="Full text content that should replace the file."),
    ],
) -> dict[str, object]:
    target = resolve_path(path, WORKSPACE_ROOT)
    return write_file(target, content=content)


@mcp.tool(
    description=(
        "Replace one exact text fragment inside a file. "
        "Use this for surgical edits after reading the file and providing a unique oldText match."
    )
)
def edit(
    path: Annotated[
        str,
        Field(description="Target file path. Relative paths resolve against the workspace root."),
    ],
    oldText: Annotated[
        str,
        Field(description="Exact existing text to replace. The match should be unique and copied verbatim."),
    ],
    newText: Annotated[
        str,
        Field(description="Replacement text that will be inserted in place of oldText."),
    ],
) -> dict[str, object]:
    target = resolve_path(path, WORKSPACE_ROOT)
    return edit_file(target, old_text=oldText, new_text=newText)


@mcp.tool(
    description=(
        "Inspect the current workspace and shell runtime before repo-aware commands. "
        "Use this to check shell resolution, git status, codex availability, and trusted-path context."
    )
)
def workspace_profile(
    cwd: Annotated[
        str | None,
        Field(
            description=(
                "Optional working directory to inspect. Relative paths resolve against the workspace root."
            )
        ),
    ] = None,
) -> dict[str, object]:
    resolved_cwd = resolve_cwd(cwd, WORKSPACE_ROOT)
    return collect_workspace_profile(resolved_cwd, SHELL_RUNTIME)


@mcp.tool(
    description=(
        "Run a shell command on the computer through Poke callbacks. "
        "Fast commands complete immediately; longer commands stream started, heartbeat, and completed events. "
        "This tool requires a Poke callback-aware client."
    )
)
@with_callbacks
async def shell(
    command: Annotated[
        str,
        Field(description="Shell command to execute."),
    ],
    cwd: Annotated[
        str | None,
        Field(
            description=(
                "Optional working directory for the command. Relative paths resolve against the workspace root."
            )
        ),
    ] = None,
    timeout: Annotated[
        int | None,
        Field(
            description=(
                "Optional per-call timeout in seconds for this command. "
                "If omitted, the default shell timeout is used."
            )
        ),
    ] = None,
) -> str:
    resolved_cwd = resolve_cwd(cwd, WORKSPACE_ROOT)
    async for event in stream_shell_command(
        command=command,
        cwd=resolved_cwd,
        runtime=SHELL_RUNTIME,
        timeout=timeout if timeout is not None else SHELL_TIMEOUT,
        state_dir=STATE_DIR,
        max_tail_lines=MAX_OUTPUT_TAIL_LINES,
        max_tail_bytes=MAX_OUTPUT_TAIL_BYTES,
        heartbeat_seconds=CALLBACK_HEARTBEAT_SECONDS,
    ):
        yield event


def main() -> None:
    ensure_runtime_directories()
    print(f"Starting {APP_NAME} on {HOST}:{PORT}")
    print(f"workspace_root={WORKSPACE_ROOT}")
    print(f"state_dir={STATE_DIR}")
    print(f"shell_runtime={SHELL_RUNTIME.describe()}")
    mcp_http_app = mcp.http_app(
        path="/mcp",
        transport="http",
    )
    app = MCPTraceMiddleware(
        PokeCallbackMiddleware(
            SSEStreamTakeoverMiddleware(
                mcp_http_app,
                transport_path="/mcp",
            )
        )
    )
    uvicorn.run(app, host=HOST, port=PORT)


if __name__ == "__main__":
    main()
