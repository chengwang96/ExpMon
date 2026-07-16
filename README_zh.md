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

## Windows 桌面客户端

Electron 客户端会打包生产版 React 界面和独立 Python collector sidecar。它会选择空闲的本机端口，用每次启动生成的 token 验证 renderer 请求，等待 collector 健康检查通过，并在窗口退出时清理整个 collector 进程树。安装后的客户端不需要用户另行安装 Python 或 Node.js。

从仓库启动桌面客户端：

```powershell
npm run desktop:start
```

构建 Python sidecar 和 NSIS 安装包：

```powershell
npm run desktop:dist
```

安装包输出到 `release-client/ExpMon-Setup-<version>-x64.exe`。桌面配置、SSH profile、运行元数据、受管理运行文件和 collector 日志存放在 Electron 的 ExpMon 用户数据目录。可以运行 `npm run test:desktop` 对桌面客户端做端到端检查。

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

JSONL、CSV 和 W&B summary 可以在页面内预览。ExpMon 会增量导入 TensorBoard 的 `train_loss`、`valid_loss`/`val_loss` 和 `test_loss` 到 `metrics.jsonl`，包括 adopt 时已经存在的历史指标。TensorBoard 已包含在 collector 依赖中；MLflow viewer 仍为可选功能。

```powershell
pip install mlflow
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

本地 collector 会优先通过 SSH tunnel 使用 remote agent，再回退到一次性 SSH 采样：

1. 通过 SSH 执行 `expmon discover --json`，或读取标准 discovery manifest。
2. Linux/macOS 首次连接且未发现 ExpMon 时，自动安装轻量 agent 到 `~/.local/share/expmon`；缺少 `psutil` 或 TensorBoard 支持时会优先安装到用户环境，并在需要时回退到隔离 venv。
3. agent 默认绑定远端 `127.0.0.1:5194`，本地 collector 自动创建 SSH tunnel 后采样。
4. 自动安装或 tunnel 不可用时，才尝试显式暴露的 agent 和一次性 SSH 采样。

添加 SSH 配置并通过连接测试后，bootstrap 会在后台启动；已有 SSH 配置也会在首次资源采样时补装。安装和自动启动默认开启，可分别用 `EXPMON_REMOTE_AGENT_AUTO_INSTALL=0` 和 `EXPMON_REMOTE_AGENT_AUTOSTART=0` 禁用。安装失败会进入冷却并自动降级，不会阻塞其他主机。agent 会把远端 managed、adopted 和自动发现运行合并到本地 **Runs** 与 **Projects** 页面。

如果远端训练已经启动，可以直接在该服务器执行 Level B 接管，无需重启训练：

```bash
python scripts/expmon.py adopt --pid 3637117 --project NeuroSTORM \
  --name hcp1200-h200-gpu0 --resource-type gpu --log-file nohup.out
```

`adopt` 会创建稳定的 run id、manifest 和后续资源历史，但无法补回接管前的输出、注入启动时环境变量或恢复未受 ExpMon 监督的退出码。

记录的根进程退出后，collector 会把 `finished` 和 `ended_at` 持久化到 manifest 与 `status.json`。由于 adopt 进程并非 ExpMon 的子进程，历史退出码会诚实记录为 `exit_code: null` 和 `exit_code_known: false`；`expmon launch` 仍会记录真实退出码。

因此推荐让 agent 绑定 `127.0.0.1`，远端机器不需要开放 HTTP 端口。如果确实要暴露其他直连端口，可以在本地 collector 设置 `EXPMON_REMOTE_AGENT_PORT`。共享环境中，可以在远端 agent 设置 `EXPMON_AGENT_TOKEN`，并在本地 collector 设置相同的 `EXPMON_REMOTE_AGENT_TOKEN`。

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
