# poke-m1-bridge

给专用的 `m1` Mac 沙盒机使用的本地 MCP bridge。

## 提供的工具

- `read`
- `write`
- `edit`
- `bash_exec`

## 设计目标

- 运行在 `m1` 本机
- 默认围绕一个固定 `workspace_root` 工作
- 同时允许显式传绝对路径
- `bash_exec` 保持原始 shell 语义，不引入额外包装
- 服务默认只监听 `127.0.0.1`

## 环境变量

```bash
POKE_BRIDGE_HOST=127.0.0.1
POKE_BRIDGE_PORT=8765
POKE_BRIDGE_WORKSPACE_ROOT=~/work/agent-sandbox
POKE_BRIDGE_STATE_DIR=~/.poke-m1-bridge
POKE_BRIDGE_SHELL=/bin/zsh
POKE_BRIDGE_COMMAND_TIMEOUT=30
POKE_BRIDGE_MAX_READ_LINES=200
POKE_BRIDGE_MAX_READ_BYTES=32768
POKE_BRIDGE_MAX_OUTPUT_TAIL_LINES=200
POKE_BRIDGE_MAX_OUTPUT_TAIL_BYTES=32768
```

## 在 m1 上安装

```bash
cd ~/work
python3 -m venv poke-m1-bridge/.venv
cd poke-m1-bridge
source .venv/bin/activate
pip install -r requirements.txt
pip install -e .
```

## 启动

```bash
export POKE_BRIDGE_WORKSPACE_ROOT=~/work/agent-sandbox
poke-m1-bridge
```

或者：

```bash
python3 -m poke_m1_bridge.server
```

服务地址：

```text
http://127.0.0.1:8765/mcp
```

## 接入 Poke

在 `m1` 上：

```bash
npx poke login
npx poke tunnel http://127.0.0.1:8765/mcp -n m1-agent
```

## 说明

- `read` 默认按行读取并在大文件时返回 `next_offset`
- `write` 是整文件覆盖写
- `edit` 是基于唯一精确匹配的文本替换
- `bash_exec` 会返回结构化结果；当输出过大时，会把完整输出保存到 `POKE_BRIDGE_STATE_DIR/runs/...`
