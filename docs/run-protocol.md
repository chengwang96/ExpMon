# ExpMon Run Protocol

ExpMon supports two monitoring levels.

## Level C: automatic process discovery

No training code changes are required.

The local collector reads `expmon.yaml`, checks running processes, and promotes matching process roots into runs when their command or working directory matches the configured discovery rules.

Example discovery configuration:

```yaml
experiment_roots:
  - ./

run_discovery:
  include_command_keywords:
    - train
    - fit
    - torchrun
  include_cwd_under:
    - ./
  explicit_rules: []
```

Level C can show:

- root process and process tree
- CPU and memory
- GPU usage when the process owns a visible NVIDIA GPU context
- runtime, command, cwd, and user

Level C cannot reliably show:

- hyperparameters
- scalar metrics
- stdout/stderr history after collector restarts
- stable run identity after process exit

## Level B: adopt an existing process

Use `adopt` when a training process was started outside ExpMon and must keep running:

```bash
python scripts/expmon.py adopt \
  --pid 3637117 \
  --project NeuroSTORM \
  --name hcp1200-h200-gpu0 \
  --resource-type gpu \
  --log-file nohup.out
```

Adoption creates a stable run id, manifest, process identity, and resource history without restarting the process. The collector infers the original start time, command, working directory, user, and process tree. `--log-file` is optional and lets the run page tail an existing `nohup` log.

An adopted run is Level B rather than Level A: ExpMon cannot reconstruct output emitted before adoption, inject `EXPMON_*` environment variables into an existing process, or recover an exit code it does not supervise. The collector still persists process exit detection with `ended_at`, `exit_code: null`, and `exit_code_known: false`. Existing and growing TensorBoard loss scalars are imported into `metrics.jsonl`; new metrics can also be appended with `expmon log --run-dir <printed-run-dir> ...`.

## Level A: managed run

Use `scripts/expmon.py launch` to start the task.

```powershell
python .\scripts\expmon.py launch --project demo --name train-resnet --resource-type gpu -- `
  python train.py --epochs 10 --batch-size 8
```

The launcher creates:

```text
expmon-runs/<project>/<run_id>/
  manifest.yaml
  status.json
  hparams.yaml
  metrics.jsonl
  resources.jsonl
  events.jsonl
  stdout.log
  stderr.log
```

The collector scans this directory through:

```yaml
protocol:
  scan_roots:
    - ./expmon-runs
```

When launched through `expmon.py launch`, the child process receives:

- `EXPMON_RUN_ID`
- `EXPMON_RUN_DIR`
- `EXPMON_PROJECT`
- `EXPMON_NAME`

## Logging metrics

Option 1: print metric markers from the training script.

```python
print("EXPMON_METRIC step=100 train/loss=0.83 val/auc=0.91 objective=0.91")
```

Option 2: call the logger from inside the launched process.

```powershell
python .\scripts\expmon.py log --step 100 train/loss=0.83 val/auc=0.91 objective=0.91
```

## Logging events

Option 1: print event markers from the training script.

```python
print('EXPMON_EVENT {"type":"checkpoint","severity":"info","message":"saved epoch 3"}')
print("EXPMON_EVENT type=eval_started severity=info message=validation")
```

Option 2: call the event logger from inside the launched process.

```powershell
python .\scripts\expmon.py event --type checkpoint --severity info --message "saved epoch 3"
```

The collector also scans stdout/stderr for common failures such as CUDA OOM, NCCL warnings, disk full errors, segmentation faults, DataLoader crashes, and NaN/Inf warnings.

## Experiment log visualization

The collector scans each managed run directory, explicit output/log directories from the command, and common `lightning_logs`/`runs` children for experiment log formats:

- TensorBoard event files named `events.out.tfevents*`
- Weights & Biases offline directories under `wandb/run-*` or `wandb/offline-run-*`
- MLflow tracking directories named `mlruns`
- metric JSONL files such as `metrics.jsonl`, `history.jsonl`, or `wandb-history.jsonl`
- metric CSV files with names containing `metric`, `history`, `progress`, or `result`

JSONL, CSV, and W&B summaries are previewed inline. TensorBoard loss scalars are also imported incrementally into the unified metric history. TensorBoard is a core collector dependency; install MLflow separately to open its standard local viewer:

```powershell
pip install mlflow
```

Keep `protocol.scan_roots` narrow. Scanning a dedicated run directory every 3 seconds is cheap; scanning an entire data drive is not.
