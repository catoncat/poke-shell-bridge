# poke-shell-bridge

一个面向 Poke 的 **Computer Control** MCP：把一台独立机器上的文件读写与 shell 执行能力，通过 MCP 暴露给 Poke。

适合把 **专门给 agent 用的开发机 / 沙盒机** 接到 Poke，而不是直接暴露你的主力电脑。

## 它能做什么

- 在指定工作区里 `read` / `write` / `edit` 文件
- 执行任意 shell 命令，并通过 Poke callback 回推进度
- 检查当前工作目录是否是 git repo、`codex` 是否可用、trusted path 是否命中
- 自动适配目标机器上的 shell 运行时，不让模型去猜该用 `bash` 还是 `zsh`

## 适合的场景

- 你想把一台远程 Mac / Linux 开发机接给 Poke
- 你想让 agent 能跑 `git`、`codex`、构建、测试，但不想直接暴露当前工作电脑
- 你需要一个比“只开放 run_command”更清晰的 MCP 产品边界

## 提供的工具

| 工具 | 用途 |
| --- | --- |
| `read` | 读取文本文件，支持分页 |
| `write` | 整文件覆盖写入 |
| `edit` | 基于唯一精确匹配做文本替换 |
| `shell` | 执行命令；快命令立即完成，长命令通过 callback 回推进度 |
| `workspace_profile` | 预检 git / codex / trusted path / shell 环境 |

## 快速开始

### 1) 安装

```bash
git clone https://github.com/catoncat/poke-shell-bridge.git
cd poke-shell-bridge

python3 -m venv .venv
source .venv/bin/activate

pip install -r requirements.txt
pip install -e .
```

### 2) 启动 bridge

```bash
export POKE_BRIDGE_WORKSPACE_ROOT=~/workspace
poke-shell-bridge
```

默认监听：

```text
http://127.0.0.1:8765/mcp
```

### 3) 接到 Poke

在 bridge 所在主机上执行：

```bash
npx poke login
npx poke tunnel http://127.0.0.1:8765/mcp -n poke-shell-bridge
```

## 配置

| 环境变量 | 默认值 | 说明 |
| --- | --- | --- |
| `POKE_BRIDGE_HOST` | `127.0.0.1` | HTTP 监听地址 |
| `POKE_BRIDGE_PORT` | `8765` | HTTP 监听端口 |
| `POKE_BRIDGE_WORKSPACE_ROOT` | `~/workspace` | 默认工作区根目录 |
| `POKE_BRIDGE_STATE_DIR` | `~/.poke-shell-bridge` | 运行状态、长输出落盘目录 |
| `POKE_BRIDGE_SHELL` | 自动解析 | 指定 shell 可执行文件 |
| `POKE_BRIDGE_SHELL_MODE` | `login` | `login` 或 `exec` |
| `POKE_BRIDGE_PATH_PREFIX` | 空 | 额外追加到 `PATH` 前面的目录列表 |
| `POKE_BRIDGE_SHELL_TIMEOUT` | `1800` | `shell` 的默认超时秒数 |
| `POKE_BRIDGE_BACKGROUND_TIMEOUT` | 兼容旧配置 | 旧版本长命令超时变量，未设置新变量时仍会回退读取 |
| `POKE_BRIDGE_COMMAND_TIMEOUT` | 兼容旧配置 | 更早期兼容变量，未设置新变量时会作为默认超时 |
| `POKE_BRIDGE_CALLBACK_HEARTBEAT_SECONDS` | `5` | 长命令 heartbeat 间隔 |
| `POKE_BRIDGE_TRACE` | `1` | 是否在 server log 输出方法级 trace |
| `POKE_BRIDGE_MAX_READ_LINES` | `200` | 单次读取最大行数 |
| `POKE_BRIDGE_MAX_READ_BYTES` | `32768` | 单次读取最大字节数 |
| `POKE_BRIDGE_MAX_OUTPUT_TAIL_LINES` | `200` | 命令输出返回的最大 tail 行数 |
| `POKE_BRIDGE_MAX_OUTPUT_TAIL_BYTES` | `32768` | 命令输出返回的最大 tail 字节数 |

## shell 运行模型

这个 bridge 不要求模型自己判断目标机器该用什么 shell。

启动时会按下面顺序解析运行时：

```text
POKE_BRIDGE_SHELL > $SHELL > 平台默认 shell
```

另外：

- `POKE_BRIDGE_SHELL_MODE=login` 时，使用 login shell 语义
- `POKE_BRIDGE_SHELL_MODE=exec` 时，直接 `-c` 执行
- bridge 会预置常见用户 bin 目录到 `PATH`
- 你也可以通过 `POKE_BRIDGE_PATH_PREFIX` 继续补充

这使得 `codex`、`bun`、`pnpm`、用户自定义脚本等命令更容易在目标机器上被正确找到。

## 命令执行语义

### `shell`

`shell` 是唯一的命令执行工具，统一走 Poke callback 生命周期。

适合：

- `git status`
- `command -v codex`
- `pytest tests/foo.py -q`
- `codex review .`
- 构建、长测试、批量脚本

行为是：

1. **快命令**：如果命令很快完成，会直接返回 `completed`
2. **长命令**：先返回 `started`
3. 运行过程中按 heartbeat 间隔回推 `heartbeat`
4. 结束后回推 `completed`

`completed` 事件里的结果包含：

- `success`
- `exit_code`
- `stdout`
- `stderr`
- `resolved_cwd`
- `shell` / `shell_args` / `shell_mode` / `shell_source`

如果输出过大，完整输出会保存到：

```text
$POKE_BRIDGE_STATE_DIR/runs/...
```

> 注意：`shell` 依赖 Poke callback headers。
> 如果 MCP 客户端没有带 `X-Poke-Callback-Token` / `X-Poke-Callback-Url`，它只能拿到第一条返回，后续 callback 不会继续送达。

### `workspace_profile`

在执行 repo-aware 工具前，建议先调用它做预检，尤其是：

- `git diff`
- `gh`
- `codex review .`

它会返回：

- 当前 `cwd` 是否存在
- 当前 shell 运行时信息
- `git` / `codex` 是否能找到
- 当前目录是否在 git repo 中
- 当前目录是否命中 codex trusted entries

## 观测与排查

默认会在 server log 输出 `TRACE {...}` 行，用来观察：

- HTTP 请求方法、路径、状态码
- JSON-RPC method / id
- `tools/call` 的工具名与关键参数摘要
- 是否带了 Poke callback headers
- `shell` 的 `run / started / heartbeat / completed`

如果想关闭这些 trace：

```bash
export POKE_BRIDGE_TRACE=0
```

## 推荐部署方式

推荐把它部署在一台**独立的 agent 机器**上：

- 一台远程 Mac mini / Linux 主机
- 一台专门给 agent 用的云机 / VPS
- 一台你愿意交给 Poke 的独立沙盒机

然后把这台机器通过 `poke tunnel` 接到 Poke，而不是直接暴露你的主力开发电脑。

## 设计原则

- 默认围绕一个固定 `workspace_root` 工作
- 相对路径按工作区解析，必要时也允许显式绝对路径
- 尽量保持原始 shell 语义，不额外包一层“智能 shell”
- 默认只监听 `127.0.0.1`
- 输出结构化，便于模型与人一起排查环境问题
