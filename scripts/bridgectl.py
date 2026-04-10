#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import shlex
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Node:
    name: str
    host: str | None
    project_root: str
    workspace_root: str
    state_dir: str
    bridge_session: str
    tunnel_session: str
    tunnel_name: str
    bridge_log: str
    tunnel_log: str


REPO_ROOT = Path(__file__).resolve().parent.parent

NODES = {
    "local": Node(
        name="local",
        host=None,
        project_root=os.environ.get("POKE_BRIDGECTL_LOCAL_PROJECT_ROOT", str(REPO_ROOT)),
        workspace_root=os.environ.get("POKE_BRIDGECTL_LOCAL_WORKSPACE_ROOT", str(REPO_ROOT.parent)),
        state_dir=os.environ.get("POKE_BRIDGECTL_LOCAL_STATE_DIR", str(Path("~/.poke-shell-bridge").expanduser())),
        bridge_session="poke-shell-bridge-local",
        tunnel_session="poke-tunnel-local",
        tunnel_name=os.environ.get("POKE_BRIDGECTL_LOCAL_TUNNEL_NAME", "Computer (Local)"),
        bridge_log=os.environ.get(
            "POKE_BRIDGECTL_LOCAL_BRIDGE_LOG",
            str(Path("~/.poke-shell-bridge/server-local.log").expanduser()),
        ),
        tunnel_log=os.environ.get(
            "POKE_BRIDGECTL_LOCAL_TUNNEL_LOG",
            str(Path("~/.poke-shell-bridge/tunnel-local.log").expanduser()),
        ),
    ),
    "remote": Node(
        name="remote",
        host=os.environ.get("POKE_BRIDGECTL_REMOTE_HOST", "m1"),
        project_root=os.environ.get("POKE_BRIDGECTL_REMOTE_PROJECT_ROOT", "/Users/ccob/work/poke-shell-bridge"),
        workspace_root=os.environ.get("POKE_BRIDGECTL_REMOTE_WORKSPACE_ROOT", "/Users/ccob/workspace"),
        state_dir=os.environ.get("POKE_BRIDGECTL_REMOTE_STATE_DIR", "/Users/ccob/.poke-shell-bridge"),
        bridge_session="poke-shell-bridge-remote",
        tunnel_session="poke-tunnel-remote",
        tunnel_name=os.environ.get("POKE_BRIDGECTL_REMOTE_TUNNEL_NAME", "Computer (M1)"),
        bridge_log=os.environ.get("POKE_BRIDGECTL_REMOTE_BRIDGE_LOG", "/Users/ccob/.poke-shell-bridge/server.log"),
        tunnel_log=os.environ.get("POKE_BRIDGECTL_REMOTE_TUNNEL_LOG", "/Users/ccob/.poke-shell-bridge/tunnel.log"),
    ),
}


def run_shell(node: Node, script: str, *, check: bool = True) -> subprocess.CompletedProcess[str]:
    if node.host:
        cmd = ["ssh", node.host, f"zsh -lc {shlex.quote(script)}"]
    else:
        cmd = ["zsh", "-lc", script]
    return subprocess.run(cmd, text=True, check=check, capture_output=True)


def q(value: str) -> str:
    return shlex.quote(value)


def bridge_process_pattern(node: Node) -> str:
    return f"{node.project_root}/.venv/bin/poke-shell-bridge"


def tunnel_process_pattern(node: Node) -> str:
    return "npm exec poke tunnel http://127.0.0.1:8765/mcp"


def bridge_command(node: Node) -> str:
    inner = (
        f"cd {q(node.project_root)} && "
        "source .venv/bin/activate && "
        f"env POKE_BRIDGE_WORKSPACE_ROOT={q(node.workspace_root)} "
        "POKE_BRIDGE_SHELL=/bin/zsh "
        f"poke-shell-bridge > {q(node.bridge_log)} 2>&1"
    )
    return (
        f"mkdir -p {q(node.state_dir)} && "
        f"tmux kill-session -t {q(node.bridge_session)} >/dev/null 2>&1 || true && "
        f"pkill -f -- {q(bridge_process_pattern(node))} >/dev/null 2>&1 || true && "
        f"tmux new-session -d -s {q(node.bridge_session)} {q(inner)}"
    )


def tunnel_command(node: Node) -> str:
    inner = (
        f"cd {q(node.project_root)} && "
        f"npx poke tunnel http://127.0.0.1:8765/mcp -n {q(node.tunnel_name)} "
        f"> {q(node.tunnel_log)} 2>&1"
    )
    return (
        f"mkdir -p {q(node.state_dir)} && "
        f"tmux kill-session -t {q(node.tunnel_session)} >/dev/null 2>&1 || true && "
        f"pkill -f -- {q(tunnel_process_pattern(node))} >/dev/null 2>&1 || true && "
        f"tmux new-session -d -s {q(node.tunnel_session)} {q(inner)}"
    )


def stop_bridge_command(node: Node) -> str:
    return (
        f"tmux kill-session -t {q(node.bridge_session)} >/dev/null 2>&1 || true && "
        f"pkill -f -- {q(bridge_process_pattern(node))} >/dev/null 2>&1 || true"
    )


def stop_tunnel_command(node: Node) -> str:
    return (
        f"tmux kill-session -t {q(node.tunnel_session)} >/dev/null 2>&1 || true && "
        f"pkill -f -- {q(tunnel_process_pattern(node))} >/dev/null 2>&1 || true"
    )


def deploy_command(node: Node) -> str:
    parts = [f"cd {q(node.project_root)}"]
    if node.host:
        parts.append("git pull --ff-only origin main")
    parts.append("source .venv/bin/activate")
    parts.append(f"pip install -e . > /tmp/poke-shell-bridge-{node.name}-build.log 2>&1")
    return " && ".join(parts)


def status_command(node: Node) -> str:
    return f"""
echo "[{node.name}]"
echo "project_root={node.project_root}"
if tmux has-session -t {q(node.bridge_session)} 2>/dev/null; then
  echo "bridge=running"
elif pgrep -f -- {q(bridge_process_pattern(node))} >/dev/null 2>&1; then
  echo "bridge=running (legacy-process)"
else
  echo "bridge=stopped"
fi
if tmux has-session -t {q(node.tunnel_session)} 2>/dev/null; then
  echo "tunnel=running"
elif pgrep -f -- {q(tunnel_process_pattern(node))} >/dev/null 2>&1; then
  echo "tunnel=running (legacy-process)"
else
  echo "tunnel=stopped"
fi
echo "--- bridge log ---"
tail -n 4 {q(node.bridge_log)} 2>/dev/null | tr -d '\\000' || true
echo "--- tunnel log ---"
tail -n 4 {q(node.tunnel_log)} 2>/dev/null | tr -d '\\000' || true
""".strip()


def logs_command(node: Node, service: str, lines: int) -> str:
    path = node.bridge_log if service == "bridge" else node.tunnel_log
    return f"tail -n {int(lines)} {q(path)} | tr -d '\\000'"


def running_check_command(node: Node, service: str) -> str:
    if service == "bridge":
        session = node.bridge_session
        pattern = bridge_process_pattern(node)
    else:
        session = node.tunnel_session
        pattern = tunnel_process_pattern(node)
    return f"""
if tmux has-session -t {q(session)} 2>/dev/null; then
  echo "running"
elif pgrep -f -- {q(pattern)} >/dev/null 2>&1; then
  echo "running"
else
  echo "stopped"
fi
""".strip()


def service_is_running(node: Node, service: str) -> bool:
    result = run_shell(node, running_check_command(node, service))
    return result.stdout.strip() == "running"


def nodes_for(target: str) -> list[Node]:
    if target == "m1":
        target = "remote"
    if target == "all":
        return [NODES["local"], NODES["remote"]]
    return [NODES[target]]


def print_block(title: str, content: str) -> None:
    print(f"\n=== {title} ===")
    print(content.rstrip() or "(no output)")


def exec_and_print(node: Node, title: str, script: str) -> None:
    result = run_shell(node, script)
    print_block(title, result.stdout)
    if result.stderr.strip():
        print_block(f"{title} stderr", result.stderr)


def do_status(target: str) -> None:
    for node in nodes_for(target):
        exec_and_print(node, f"{node.name} status", status_command(node))


def do_logs(target: str, service: str, lines: int) -> None:
    if service == "all":
        raise SystemExit("logs 只支持 bridge 或 tunnel")
    for node in nodes_for(target):
        exec_and_print(node, f"{node.name} {service} logs", logs_command(node, service, lines))


def do_action(action: str, target: str, service: str) -> None:
    if action == "deploy":
        for node in nodes_for(target):
            exec_and_print(node, f"{node.name} deploy", deploy_command(node))
            if service in {"bridge", "all"}:
                exec_and_print(node, f"{node.name} restart bridge", bridge_command(node))
            if service in {"tunnel", "all"}:
                if service_is_running(node, "tunnel"):
                    print_block(
                        f"{node.name} ensure tunnel",
                        "tunnel already running; keep existing Poke connection",
                    )
                else:
                    exec_and_print(node, f"{node.name} start tunnel", tunnel_command(node))
        return

    for node in nodes_for(target):
        if service in {"bridge", "all"}:
            if action == "start":
                exec_and_print(node, f"{node.name} start bridge", bridge_command(node))
            elif action == "stop":
                exec_and_print(node, f"{node.name} stop bridge", stop_bridge_command(node))
            elif action == "restart":
                exec_and_print(node, f"{node.name} restart bridge", bridge_command(node))
        if service in {"tunnel", "all"}:
            if action == "start":
                exec_and_print(node, f"{node.name} start tunnel", tunnel_command(node))
            elif action == "stop":
                exec_and_print(node, f"{node.name} stop tunnel", stop_tunnel_command(node))
            elif action == "restart":
                exec_and_print(node, f"{node.name} restart tunnel", tunnel_command(node))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Manage local and m1 poke-shell-bridge bridge/tunnel processes.")
    parser.add_argument("action", choices=["status", "start", "stop", "restart", "deploy", "logs"])
    parser.add_argument("target", nargs="?", default="all", choices=["local", "remote", "m1", "all"])
    parser.add_argument("service", nargs="?", default="all", choices=["bridge", "tunnel", "all"])
    parser.add_argument("-n", "--lines", type=int, default=20, help="Lines to show for logs")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.action == "status":
        do_status(args.target)
    elif args.action == "logs":
        do_logs(args.target, args.service, args.lines)
    else:
        do_action(args.action, args.target, args.service)


if __name__ == "__main__":
    main()
