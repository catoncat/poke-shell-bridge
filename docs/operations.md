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

# 同步并重建
python3 scripts/bridgectl.py deploy all all
python3 scripts/bridgectl.py deploy remote all

# 查看日志
python3 scripts/bridgectl.py logs local bridge -n 50
python3 scripts/bridgectl.py logs remote tunnel -n 50
```

## 行为说明

- `start` / `restart`：用 `tmux` 拉起 bridge / tunnel
- `stop`：杀掉对应 `tmux session`
- `deploy`：重新安装当前仓库；远端会先 `git pull --ff-only origin main`，然后重启对应服务
- `logs`：只支持 `bridge` 或 `tunnel`

默认情况下，bridge 的 server log 里会带 `TRACE {...}` 行，可以直接配合：

```bash
python3 scripts/bridgectl.py logs local bridge -n 100
```

来看：

- `initialize / tools/list / tools/call`
- HTTP `200 / 202 / 409`
- `shell.started / shell.heartbeat / shell.completed`

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
