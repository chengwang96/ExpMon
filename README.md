# ExpMon - Local-First Experiment, GPU, and SSH Host Monitor

[中文文档](README_zh.md)

ExpMon is a local-first experiment task monitor. It tracks managed and discovered experiment processes, host resources, GPU usage, metrics, logs, and common experiment log formats from a browser UI.

## Quick Start

Install frontend dependencies:

```powershell
npm ci
```

Install Python collector dependencies:

```powershell
python -m pip install -r requirements.txt
```

For UI regression tests, install the development dependencies and Playwright browser runtime:

```powershell
python -m pip install -r requirements-dev.txt
python -m playwright install chromium
```

Start the local collector:

```powershell
npm run collector
```

Start the frontend:

```powershell
npm run dev
```

Open the Vite URL shown in the terminal, usually `http://127.0.0.1:5173`.

Or start both collector and frontend with one PowerShell script:

```powershell
npm run start:local
```

Custom ports or a local config file can be passed directly:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start-expmon.ps1 -CollectorPort 5185 -FrontendPort 5174 -Config .\expmon-local.yaml
```

Copy `.env.example` to a local `.env` file when you want to persist frontend or collector environment overrides. Local `.env` files are ignored by Git.

## Managed Runs

Launch an experiment through ExpMon:

```powershell
python .\scripts\expmon.py launch --project demo --name train-resnet --resource-type gpu -- `
  python train.py --epochs 10
```

Log metrics from a launched process:

```powershell
python .\scripts\expmon.py log --step 100 train/loss=0.83 val/auc=0.91 objective=0.91
```

Or print metric markers from the training script:

```python
print("EXPMON_METRIC step=100 train/loss=0.83 val/auc=0.91 objective=0.91")
```

Log events from a launched process:

```powershell
python .\scripts\expmon.py event --type checkpoint --severity info --message "saved epoch 3"
```

Or print event markers:

```python
print('EXPMON_EVENT {"type":"cuda_oom","severity":"error","message":"CUDA out of memory"}')
```

The collector writes resource samples to `resources.jsonl` and events to `events.jsonl`, so finished managed runs can still show historical resource curves and detected failures.

## Experiment Log Visualization

The run detail page scans managed run directories for:

- TensorBoard event files
- Weights & Biases offline run directories
- MLflow tracking directories
- metric JSONL files
- metric CSV files

JSONL, CSV, and W&B summaries can be previewed inline. TensorBoard and MLflow can be opened through local viewer processes if the corresponding packages are installed in the collector environment.

```powershell
pip install tensorboard mlflow
```

## Configuration

`expmon.yaml` is the generic sample configuration committed to the repository. Use the **Config** page to edit the active local collector configuration: host id, refresh interval, experiment roots, managed run scan roots, command keyword rules, and explicit parser rules.

When `EXPMON_CONFIG` is not set, UI edits are saved to `expmon-local.yaml`, which is ignored by Git. When `EXPMON_CONFIG` is set, edits are saved to that local path. The collector applies saved changes without a restart.

Useful environment variables:

- `VITE_COLLECTOR_URL`: frontend API endpoint for the collector.
- `EXPMON_COLLECTOR_PORT`: port used by `scripts/local_collector.py`.
- `EXPMON_CONFIG`: local collector config path.
- `EXPMON_SSH_SERVERS`: local SSH server profile storage path.
- `EXPMON_RUN_METADATA`: local run notes and marks storage path.

## Host / SSH

The **Host / SSH** page shows local host resources and stores remote SSH server profiles in a gitignored local file. Key-based SSH profiles can be tested from the UI with the local `ssh` command.

For stable remote monitoring on Windows, macOS, or Ubuntu, run the lightweight remote agent on the target machine:

```powershell
python scripts/remote_agent.py --host 127.0.0.1 --port 5194
```

When ExpMon is installed on the remote machine, the local collector uses a discovery handshake before falling back to one-shot SSH sampling:

1. Try a direct remote agent at `http://<ssh-host>:5194/api/host` for explicitly exposed agents.
2. Run `expmon discover --json` over SSH.
3. Read the standard discovery manifest (`%LOCALAPPDATA%\ExpMon\discovery.json` on Windows or `~/.config/expmon/discovery.json` on Linux/macOS).
4. If the remote agent is running on remote `127.0.0.1`, open an SSH tunnel from a local random port to the remote agent and sample through that tunnel.

This means the recommended agent bind address is `127.0.0.1`; the remote host does not need to expose an HTTP port. Use `EXPMON_REMOTE_AGENT_PORT` on the local collector if you intentionally expose a different direct-agent port. For shared environments, set `EXPMON_AGENT_TOKEN` on the remote agent and the same value as `EXPMON_REMOTE_AGENT_TOKEN` on the local collector. Setting `EXPMON_REMOTE_AGENT_AUTOSTART=1` lets the local collector try `expmon agent start --background` when discovery finds ExpMon installed but the agent is not running.

Password SSH profiles are saved locally as requested, but non-interactive connection testing and one-shot SSH snapshots require `sshpass` or switching the profile to key-based authentication.

## Project Workspace

The **Projects** page groups runs by their Git root or working directory. For Git repositories, it can show recent log entries, changed files, diff statistics, inline diffs, select files, generate or edit a commit message, create a commit, and run `git pull --ff-only` or `git push` through the local collector.

## Testing

Run a production build check:

```powershell
npm run build
```

Run the server-independent release checks:

```powershell
npm run check:release
```

`npm test` runs the same release checks. The GitHub Actions workflow uses this release-check path on pushes and pull requests.

With the frontend running, run the lightweight smoke test:

```powershell
npm run test:smoke
```

Run the broader UI regression checks for language switching, run detail navigation, resource subcharts, log filtering, and confirmation dialogs:

```powershell
npm run test:ui
```

Run collector-side checks for project root detection:

```powershell
npm run test:collector
```

Run the privacy scan before publishing or committing generated fixtures:

```powershell
npm run test:privacy
```

Set `EXPMON_FRONTEND_URL` when the frontend is served on a custom port.

## Run Notes And Diagnostics

The run detail page supports local notes, marks, and pinned runs. These are stored in `expmon-run-metadata.json`, which is ignored by Git.

The collector also reports diagnostic insights for common problems such as error events, idle GPU allocations, CPU-side bottlenecks, and Jupyter/ipykernel processes holding GPU memory outside an ExpMon run.
