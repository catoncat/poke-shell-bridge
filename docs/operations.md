# 运维脚本

仓库里带了一个维护脚本：

```bash
python3 scripts/bridgectl.py status
```

它默认支持：

- `local`：当前电脑
- `remote`：远端电脑
- `all`：两边一起

兼容别名：

- `m1` 会被当作 `remote`

## 常用命令

```bash
# 查看状态
python3 scripts/bridgectl.py status
python3 scripts/bridgectl.py status local
python3 scripts/bridgectl.py status remote

# 启动 / 停止 / 重启
python3 scripts/bridgectl.py restart local bridge
python3 scripts/bridgectl.py restart local tunnel
python3 scripts/bridgectl.py restart all all

# 同步代码并刷新 bridge
python3 scripts/bridgectl.py deploy all all
python3 scripts/bridgectl.py deploy remote all

# 只有确实需要换一条新 tunnel 时，才显式重启 tunnel
python3 scripts/bridgectl.py restart local tunnel
python3 scripts/bridgectl.py restart remote tunnel

# 查看日志
python3 scripts/bridgectl.py logs local bridge -n 50
python3 scripts/bridgectl.py logs remote tunnel -n 50
```

## 行为说明

- `start` / `restart`：用 `tmux` 拉起 bridge / tunnel
- `stop`：杀掉对应 `tmux session`
- `deploy`：重新安装当前仓库；远端会先 `git pull --ff-only origin main`
  - `bridge`：会重启，确保最新代码立即生效
  - `tunnel`：**默认不重建**；如果 tunnel 已经在线，就继续复用当前 Poke 连接；只有 tunnel 没跑时才补起
- `logs`：只支持 `bridge` 或 `tunnel`

这套策略的目的，是尽量避免每次 `deploy` 都在 Poke 里生成一条新的连接记录。

如果你**就是要**强制换一条新连接，再手动执行：

```bash
python3 scripts/bridgectl.py restart local tunnel
python3 scripts/bridgectl.py restart remote tunnel
```

如果 Poke 里已经积累了历史旧连接，需要去 Poke 的连接管理界面手动断开旧项；`deploy` 现在只负责尽量不再继续制造新项。

默认情况下，bridge 的 server log 里会带 `TRACE {...}` 行，可以直接配合：

```bash
python3 scripts/bridgectl.py logs local bridge -n 100
```

来看：

- `initialize / tools/list / tools/call`
- HTTP `200 / 202 / 409`
- `shell.started / shell.heartbeat / shell.completed`

从现在开始，如果同一个 session 又来了一条新的 `GET /mcp`，bridge 会自动输出：

```text
TRACE {"event":"sse.takeover", ...}
```

这表示它已经主动让**新的 SSE 回推通道接管旧通道**，避免旧连接脏住后把整个会话卡死。

## 可配置环境变量

如果你的机器名、远端路径或 tunnel 名不同，可以通过环境变量覆盖：

```bash
POKE_BRIDGECTL_REMOTE_HOST
POKE_BRIDGECTL_REMOTE_PROJECT_ROOT
POKE_BRIDGECTL_REMOTE_WORKSPACE_ROOT
POKE_BRIDGECTL_REMOTE_TUNNEL_NAME

POKE_BRIDGECTL_LOCAL_PROJECT_ROOT
POKE_BRIDGECTL_LOCAL_WORKSPACE_ROOT
POKE_BRIDGECTL_LOCAL_TUNNEL_NAME
```

路径类变量建议直接传**绝对路径**。

例如：

```bash
POKE_BRIDGECTL_REMOTE_HOST=lab-mac \
POKE_BRIDGECTL_REMOTE_PROJECT_ROOT=~/code/poke-shell-bridge \
POKE_BRIDGECTL_REMOTE_WORKSPACE_ROOT=~/workspace \
python3 scripts/bridgectl.py deploy remote all
```
