# ExpMon - 本地优先的实验任务、GPU 与 SSH 主机监控

[English README](README.md)

ExpMon 是一个本地优先的实验任务监控工具。它通过浏览器界面跟踪受管理和自动发现的实验进程、主机资源、GPU 使用情况、指标、日志，以及常见的实验日志格式。

## 快速开始

安装前端依赖：

```powershell
npm ci
```

安装 Python collector 依赖：

```powershell
python -m pip install -r requirements.txt
```

如果要运行 UI 回归测试，请安装开发依赖和 Playwright 浏览器运行时：

```powershell
python -m pip install -r requirements-dev.txt
python -m playwright install chromium
```

启动本地 collector：

```powershell
npm run collector
```

启动前端：

```powershell
npm run dev
```

打开终端里显示的 Vite 地址，通常是 `http://127.0.0.1:5173`。

也可以用一个 PowerShell 脚本同时启动 collector 和前端：

```powershell
npm run start:local
```

自定义端口或本地配置文件可以直接传给脚本：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start-expmon.ps1 -CollectorPort 5185 -FrontendPort 5174 -Config .\expmon-local.yaml
```

如果需要持久化前端或 collector 的环境变量覆盖项，可以把 `.env.example` 复制为本地 `.env` 文件。本地 `.env` 文件会被 Git 忽略。

## 受管理的运行

通过 ExpMon 启动实验：

```powershell
python .\scripts\expmon.py launch --project demo --name train-resnet --resource-type gpu -- `
  python train.py --epochs 10
```

从已启动进程记录指标：

```powershell
python .\scripts\expmon.py log --step 100 train/loss=0.83 val/auc=0.91 objective=0.91
```

也可以在训练脚本中打印指标标记：

```python
print("EXPMON_METRIC step=100 train/loss=0.83 val/auc=0.91 objective=0.91")
```

从已启动进程记录事件：

```powershell
python .\scripts\expmon.py event --type checkpoint --severity info --message "saved epoch 3"
```

也可以打印事件标记：

```python
print('EXPMON_EVENT {"type":"cuda_oom","severity":"error","message":"CUDA out of memory"}')
```

collector 会把资源采样写入 `resources.jsonl`，把事件写入 `events.jsonl`，因此已经结束的受管理运行仍然可以显示历史资源曲线和检测到的失败信息。

## 实验日志可视化

运行详情页会扫描受管理运行目录中的：

- TensorBoard event 文件
- Weights & Biases 离线运行目录
- MLflow tracking 目录
- metric JSONL 文件
- metric CSV 文件

JSONL、CSV 和 W&B summary 可以在页面内预览。如果 collector 环境中安装了对应包，TensorBoard 和 MLflow 可以通过本地 viewer 进程打开。

```powershell
pip install tensorboard mlflow
```

## 配置

`expmon.yaml` 是提交到仓库里的通用示例配置。可以在 **Config** 页面编辑当前本地 collector 配置，包括 host id、刷新间隔、实验根目录、受管理运行扫描根目录、命令关键词规则，以及显式 parser 规则。

未设置 `EXPMON_CONFIG` 时，UI 编辑会保存到 `expmon-local.yaml`，该文件会被 Git 忽略。设置 `EXPMON_CONFIG` 后，编辑会保存到指定的本地路径。collector 会在不重启的情况下应用已保存的变更。

常用环境变量：

- `VITE_COLLECTOR_URL`：前端访问 collector 的 API 端点。
- `EXPMON_COLLECTOR_PORT`：`scripts/local_collector.py` 使用的端口。
- `EXPMON_CONFIG`：本地 collector 配置路径。
- `EXPMON_SSH_SERVERS`：本地 SSH 服务器配置存储路径。
- `EXPMON_RUN_METADATA`：本地运行笔记和标记存储路径。

## Host / SSH

**Host / SSH** 页面会显示本地主机资源，并把远程 SSH 服务器配置存储在一个被 Git 忽略的本地文件中。基于密钥的 SSH 配置可以在 UI 中通过本地 `ssh` 命令测试。

如果希望稳定监控 Windows、macOS 或 Ubuntu 远端机器，建议在目标机器上运行轻量 remote agent：

```powershell
python scripts/remote_agent.py --host 127.0.0.1 --port 5194
```

当远端机器也安装了 ExpMon，本地 collector 会先做 discovery handshake，再回退到一次性 SSH 采样：

1. 先尝试直连显式暴露的 remote agent：`http://<ssh-host>:5194/api/host`。
2. 通过 SSH 执行 `expmon discover --json`。
3. 读取标准 discovery manifest：Windows 为 `%LOCALAPPDATA%\ExpMon\discovery.json`，Linux/macOS 为 `~/.config/expmon/discovery.json`。
4. 如果发现远端 agent 正在远端 `127.0.0.1` 运行，本地 collector 会自动创建 SSH tunnel，从本地随机端口转发到远端 agent，再通过 tunnel 采样。

因此推荐让 agent 绑定 `127.0.0.1`，远端机器不需要开放 HTTP 端口。如果确实要暴露其他直连端口，可以在本地 collector 设置 `EXPMON_REMOTE_AGENT_PORT`。共享环境中，可以在远端 agent 设置 `EXPMON_AGENT_TOKEN`，并在本地 collector 设置相同的 `EXPMON_REMOTE_AGENT_TOKEN`。设置 `EXPMON_REMOTE_AGENT_AUTOSTART=1` 后，如果 discovery 发现远端安装了 ExpMon 但 agent 未运行，本地 collector 会尝试执行 `expmon agent start --background`。

密码配置会按要求保存在本地，但非交互式连接测试和一次性 SSH 快照需要 `sshpass`，或者把配置切换为基于密钥的认证。

## 项目工作区

**Projects** 页面会按 Git 根目录或工作目录对运行进行分组。对于 Git 仓库，它可以显示最近日志、变更文件、diff 统计、内联 diff，选择文件，生成或编辑 commit message，创建 commit，并通过本地 collector 执行 `git pull --ff-only` 或 `git push`。

## 测试

运行生产构建检查：

```powershell
npm run build
```

运行与服务无关的发布检查：

```powershell
npm run check:release
```

`npm test` 会运行同样的发布检查。GitHub Actions workflow 会在 push 和 pull request 上使用这条发布检查路径。

前端运行时，可以执行轻量 smoke test：

```powershell
npm run test:smoke
```

运行更完整的 UI 回归检查，覆盖语言切换、运行详情导航、资源子图、日志过滤和确认对话框：

```powershell
npm run test:ui
```

运行 collector 侧的项目根目录检测检查：

```powershell
npm run test:collector
```

发布或提交生成 fixture 前，运行隐私扫描：

```powershell
npm run test:privacy
```

当前端服务使用自定义端口时，请设置 `EXPMON_FRONTEND_URL`。

## 运行笔记和诊断

运行详情页支持本地笔记、标记和 pinned runs。这些内容存储在 `expmon-run-metadata.json`，该文件会被 Git 忽略。

collector 还会报告常见问题的诊断洞察，例如错误事件、空闲 GPU 分配、CPU 侧瓶颈，以及在 ExpMon 运行之外占用 GPU 内存的 Jupyter/ipykernel 进程。
