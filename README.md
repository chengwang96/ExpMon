# ExpMon

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

The **Host / SSH** page shows local host resources and stores remote SSH server profiles in a gitignored local file. Key-based SSH profiles can be tested from the UI with the local `ssh` command and can fetch an on-demand remote resource snapshot. Password profiles are saved locally as requested, but non-interactive connection testing and remote snapshots require `sshpass` or switching the profile to key-based authentication.

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
