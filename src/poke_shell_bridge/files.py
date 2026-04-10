from __future__ import annotations

from difflib import unified_diff
from pathlib import Path


def error_result(code: str, message: str, **extra: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "success": False,
        "error": {
            "code": code,
            "message": message,
        },
    }
    payload.update(extra)
    return payload


def _read_raw(path: Path) -> bytes:
    return path.read_bytes()


def _read_text(path: Path) -> str:
    raw = _read_raw(path)
    if b"\x00" in raw[:1024]:
        raise ValueError("File appears to be binary and is not supported by read/edit.")
    return raw.decode("utf-8", errors="replace")


def read_file(
    path: Path,
    *,
    offset: int | None,
    limit: int | None,
    max_lines: int,
    max_bytes: int,
) -> dict[str, object]:
    if not path.exists():
        return error_result("file_not_found", f"File not found: {path}", resolved_path=str(path))
    if not path.is_file():
        return error_result("not_a_file", f"Path is not a file: {path}", resolved_path=str(path))

    try:
        text = _read_text(path)
    except ValueError as exc:
        return error_result("not_text_file", str(exc), resolved_path=str(path))

    lines = text.splitlines()
    start = max(offset or 1, 1)
    total_lines = len(lines)

    if total_lines > 0 and start > total_lines:
        return error_result(
            "offset_out_of_range",
            f"Offset {start} is beyond end of file ({total_lines} lines).",
            resolved_path=str(path),
            total_lines=total_lines,
        )

    line_limit = max(limit or max_lines, 1)
    selected = lines[start - 1 : start - 1 + line_limit] if total_lines else []
    content = "\n".join(selected)
    truncated = start - 1 + line_limit < total_lines
    truncated_by = "line_limit" if truncated else None

    encoded = content.encode("utf-8")
    if len(encoded) > max_bytes:
        content = encoded[:max_bytes].decode("utf-8", errors="ignore")
        truncated = True
        truncated_by = "byte_limit"

    next_offset = start + len(selected) if truncated and selected else None
    return {
        "success": True,
        "resolved_path": str(path),
        "offset": start,
        "limit": line_limit,
        "total_lines": total_lines,
        "truncated": truncated,
        "truncated_by": truncated_by,
        "next_offset": next_offset,
        "content": content,
    }


def write_file(path: Path, *, content: str) -> dict[str, object]:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return {
        "success": True,
        "resolved_path": str(path),
        "bytes_written": len(content.encode("utf-8")),
    }


def edit_file(path: Path, *, old_text: str, new_text: str) -> dict[str, object]:
    if not path.exists():
        return error_result("file_not_found", f"File not found: {path}", resolved_path=str(path))
    if not path.is_file():
        return error_result("not_a_file", f"Path is not a file: {path}", resolved_path=str(path))

    try:
        original = _read_text(path)
    except ValueError as exc:
        return error_result("not_text_file", str(exc), resolved_path=str(path))

    occurrences = original.count(old_text)
    if occurrences == 0:
        return error_result(
            "match_not_found",
            "oldText was not found in the target file.",
            resolved_path=str(path),
        )
    if occurrences > 1:
        return error_result(
            "match_not_unique",
            f"oldText matched {occurrences} times; provide more context so the match is unique.",
            resolved_path=str(path),
            occurrences=occurrences,
        )

    updated = original.replace(old_text, new_text, 1)
    path.write_text(updated, encoding="utf-8")

    diff_lines = list(
        unified_diff(
            original.splitlines(),
            updated.splitlines(),
            fromfile=str(path),
            tofile=str(path),
            lineterm="",
        )
    )
    diff_preview = "\n".join(diff_lines[:200])
    return {
        "success": True,
        "resolved_path": str(path),
        "diff": diff_preview,
        "changed": True,
    }
