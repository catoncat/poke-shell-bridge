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


## Poke 连接行为结论

这是前面排查本地 MCP 生命周期后得到的固定结论，后续不要再反复猜：

- **集成可以长期在线**：bridge / tunnel 活着，Poke 就能继续用这个 MCP
- **session 会周期性轮换**：不是一条 SSE 永远挂到底
- **从现网日志观察**：常见是约每 5 分钟一次新的 `initialize`，约 30 秒后看到新的 `sse.takeover`
- **单次调用有超时约束**：Poke 官方 MCP Client Specification 写了默认 network timeout 是 30 秒
- **所以长命令必须靠 callback 回结果**：不能指望同步请求一直挂着等

排查顺序建议固定为：

1. 先看 bridge / tunnel 是否在线
2. 再看有没有新的 `initialize` / `sse.takeover`
3. 最后看具体调用有没有 `shell.completed` + `callback.send` / `callback.result`

如果第 1 步正常，第 2 步也正常，那问题通常不在“连接断了”，而在具体命令或 callback 行为。

## Poke 使用建议（给远程 SSH 场景）

如果 Poke 要在 `m1` 上再 SSH 到另一台机器执行命令，建议遵循下面这套傻瓜顺序：

1. **先探测环境，不要直接 deploy**

```bash
ssh m4 'export PATH=/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:$PATH; uname -m; command -v node; command -v npx; command -v wrangler'
```

2. **确认路径后，再执行正式命令**

```bash
ssh m4 'export PATH=/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:$PATH; cd ~/work/doodle-jump-pixel && npx wrangler pages deploy . --project-name doodle-jump-pixel'
```

3. **不要在 SSH 里套复杂引号地狱**

少用这种：

```bash
ssh m4 "zsh -l -c "...""
```

优先用单层命令，必要时把脚本先写成文件再执行。

4. **不要默认上 `zsh -l`**

- 非交互远程命令容易把 zsh 插件链一起拉起来
- 遇到 `FUNCNEST` / 卡死时，第一反应不是“再试一次”，而是去掉 login shell

5. **把 heartbeat 当进度，不要把 heartbeat 当结果**

- heartbeat 被限流时，bridge 现在会直接丢弃中间 heartbeat
- 真正可靠的完成信号是 `shell.completed` 对应的 `completed` callback

如果要看连接是否正常，不要只盯着聊天界面，直接看 bridge log：

```bash
python3 scripts/bridgectl.py logs remote bridge -n 100
```

重点看：

- `shell.started`
- `shell.completed`
- `callback.send`
- `callback.result`
- `callback.drop`（表示中间 heartbeat 因限流被丢弃）
