# poke-shell-bridge

给 Poke 使用的通用本地 MCP shell bridge。

## 提供的工具

- `read`
- `write`
- `edit`
- `shell`
- `shell_background`
- `workspace_profile`

## 设计目标

- 运行在本地机器
- 默认围绕一个固定 `workspace_root` 工作
- 同时允许显式传绝对路径
- `shell` 保持原始 shell 语义，不引入额外包装
- shell 由 bridge 在启动时解析，不让 LLM 猜当前机器该用 bash 还是 zsh
- 服务默认只监听 `127.0.0.1`

## 环境变量

```bash
POKE_BRIDGE_HOST=127.0.0.1
POKE_BRIDGE_PORT=8765
POKE_BRIDGE_WORKSPACE_ROOT=~/work/agent-sandbox
POKE_BRIDGE_STATE_DIR=~/.poke-shell-bridge
POKE_BRIDGE_SHELL=/bin/zsh
POKE_BRIDGE_SHELL_MODE=login
POKE_BRIDGE_PATH_PREFIX=~/.bun/bin:~/.codex/scripts
POKE_BRIDGE_COMMAND_TIMEOUT=30
POKE_BRIDGE_CALLBACK_HEARTBEAT_SECONDS=5
POKE_BRIDGE_MAX_READ_LINES=200
POKE_BRIDGE_MAX_READ_BYTES=32768
POKE_BRIDGE_MAX_OUTPUT_TAIL_LINES=200
POKE_BRIDGE_MAX_OUTPUT_TAIL_BYTES=32768
```

## 在 m1 上安装

```bash
cd ~/work
python3 -m venv poke-shell-bridge/.venv
cd poke-shell-bridge
source .venv/bin/activate
pip install -r requirements.txt
pip install -e .
```

## 启动

```bash
export POKE_BRIDGE_WORKSPACE_ROOT=~/work/agent-sandbox
poke-shell-bridge
```

或者：

```bash
python3 -m poke_shell_bridge.server
```

服务地址：

```text
http://127.0.0.1:8765/mcp
```

## 接入 Poke

在 `m1` 上：

```bash
npx poke login
npx poke tunnel http://127.0.0.1:8765/mcp -n poke-shell-bridge
```

## 说明

- `read` 默认按行读取并在大文件时返回 `next_offset`
- `write` 是整文件覆盖写
- `edit` 是基于唯一精确匹配的文本替换
- `shell` 会返回结构化结果；当输出过大时，会把完整输出保存到 `POKE_BRIDGE_STATE_DIR/runs/...`
- `shell_background` 适合 `codex` / `build` / `test` 这类长命令：首条结果立即返回，后续进度通过 Poke callback 回推
- `shell_background` 当前是 **Poke callback-first** 语义：如果 MCP 客户端没有带 `X-Poke-Callback-Token` / `X-Poke-Callback-Url`，它只会返回 `started`，不会继续把后续结果回传
- `workspace_profile` 用来预检 cwd 是否是 git repo、codex 是否可用、以及当前路径是否命中 trusted entries
- 实际执行 shell 由 bridge 启动时解析：`POKE_BRIDGE_SHELL` > `$SHELL` > 平台默认 shell
- `POKE_BRIDGE_SHELL_MODE` 默认是 `login`；需要完全跳过 login profile 时可改成 `exec`
- bridge 会在执行前把常见用户 bin 目录预置到 `PATH`，可再通过 `POKE_BRIDGE_PATH_PREFIX` 追加
- `shell` 返回里会附带 `shell` / `shell_args` / `shell_mode` / `shell_source`，方便模型和人一起排查环境问题

## 实现说明

- 当前实现仍然基于 `FastMCP`
- `poke` Python SDK 这里主要用于 callback hooks：`with_callbacks` + `PokeCallbackMiddleware`
- 也就是说这里是 **FastMCP + Poke callback integration**，不是把整个 MCP server framework 换成 `poke`
