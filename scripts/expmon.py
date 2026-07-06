import argparse
import json
import os
import queue
import re
import secrets
import shutil
import socket
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any

try:
    import psutil
except ImportError:  # pragma: no cover
    psutil = None

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None


APP_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_LOGDIR = APP_ROOT / "expmon-runs"
METRIC_PREFIX = "EXPMON_METRIC"
EVENT_PREFIX = "EXPMON_EVENT"


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def slugify(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "-", value.strip()).strip("-")
    return cleaned or "run"


def write_yaml(path: Path, payload: dict[str, Any]) -> None:
    if yaml is None:
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return
    path.write_text(yaml.safe_dump(payload, allow_unicode=True, sort_keys=False), encoding="utf-8")


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False) + "\n")


def parse_key_values(items: list[str]) -> dict[str, Any]:
    parsed: dict[str, Any] = {}
    for item in items:
        if "=" not in item:
            continue
        key, raw = item.split("=", 1)
        parsed[key] = coerce_value(raw)
    return parsed


def coerce_value(value: str) -> str | int | float | bool:
    lowered = value.lower()
    if lowered == "true":
        return True
    if lowered == "false":
        return False
    try:
        if "." in value or "e" in lowered:
            return float(value)
        return int(value)
    except ValueError:
        return value


def parse_metric_line(line: str) -> dict[str, Any] | None:
    if METRIC_PREFIX not in line:
        return None
    payload = line.split(METRIC_PREFIX, 1)[1].strip()
    if not payload:
        return None
    if payload.startswith("{"):
        try:
            parsed = json.loads(payload)
            if isinstance(parsed, dict):
                return metric_payload(parsed)
        except json.JSONDecodeError:
            return None
    return metric_payload(parse_key_values(payload.split()))


def metric_payload(values: dict[str, Any]) -> dict[str, Any]:
    step = values.pop("step", None)
    ts = values.pop("ts", now_iso())
    record: dict[str, Any] = {"ts": ts, "metrics": values}
    if step is not None:
        record["step"] = step
    return record


def event_payload(values: dict[str, Any]) -> dict[str, Any]:
    ts = values.pop("ts", now_iso())
    event_type = str(values.pop("type", values.pop("event", "event")))
    severity = str(values.pop("severity", "info"))
    message = str(values.pop("message", event_type))
    return {"ts": ts, "type": event_type, "severity": severity, "message": message, "fields": values}


def parse_event_line(line: str) -> dict[str, Any] | None:
    if EVENT_PREFIX not in line:
        return None
    payload = line.split(EVENT_PREFIX, 1)[1].strip()
    if not payload:
        return None
    if payload.startswith("{"):
        try:
            parsed = json.loads(payload)
            if isinstance(parsed, dict):
                return event_payload(parsed)
        except json.JSONDecodeError:
            return None
    return event_payload(parse_key_values(payload.split()))


def command_after_separator(raw: list[str]) -> list[str]:
    if raw and raw[0] == "--":
        return raw[1:]
    return raw


def process_create_time(pid: int) -> float:
    if psutil is None:
        return time.time()
    try:
        return float(psutil.Process(pid).create_time())
    except Exception:
        return time.time()


def make_run_dir(logdir: Path, project: str, name: str) -> tuple[str, Path]:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    run_id = f"{slugify(project)}-{slugify(name)}-{stamp}-{secrets.token_hex(3)}"
    run_dir = logdir / slugify(project) / run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    return run_id, run_dir


def infer_entrypoint(command: list[str]) -> str:
    joined = " ".join(command).lower()
    if "python" in joined or any(part.endswith(".py") for part in command):
        return "python"
    if "powershell" in joined or "bash" in joined or "cmd" in joined:
        return "shell"
    if "rscript" in joined:
        return "r"
    if "julia" in joined:
        return "julia"
    return "other"


def copy_hparams(source: str | None, run_dir: Path) -> None:
    target = run_dir / "hparams.yaml"
    if not source:
        target.write_text("{}\n", encoding="utf-8")
        return
    src = Path(source)
    if src.exists():
        shutil.copyfile(src, target)
    else:
        target.write_text("{}\n", encoding="utf-8")


def stream_reader(
    stream: Any,
    log_path: Path,
    output: Any,
    metrics_path: Path,
    events_path: Path,
    events: "queue.Queue[dict[str, Any]]",
) -> None:
    with log_path.open("a", encoding="utf-8", errors="replace") as log:
        for line in iter(stream.readline, ""):
            log.write(line)
            log.flush()
            output.write(line)
            output.flush()
            metric = parse_metric_line(line)
            if metric:
                append_jsonl(metrics_path, metric)
                events.put(metric)
            event = parse_event_line(line)
            if event:
                append_jsonl(events_path, event)
                events.put(event)


def launch(args: argparse.Namespace) -> int:
    command = command_after_separator(args.command)
    if not command:
        print("expmon launch needs a command after --", file=sys.stderr)
        return 2

    logdir = Path(args.logdir or os.environ.get("EXPMON_LOGDIR") or DEFAULT_LOGDIR)
    run_id, run_dir = make_run_dir(logdir, args.project, args.name)
    metrics_path = run_dir / "metrics.jsonl"
    events_path = run_dir / "events.jsonl"
    metrics_path.touch()
    events_path.touch()
    copy_hparams(args.hparams, run_dir)

    env = os.environ.copy()
    env.update(
        {
            "EXPMON_RUN_ID": run_id,
            "EXPMON_RUN_DIR": str(run_dir),
            "EXPMON_PROJECT": args.project,
            "EXPMON_NAME": args.name,
        }
    )

    cwd = str(Path(args.cwd).resolve()) if args.cwd else os.getcwd()
    started_at = now_iso()
    process = subprocess.Popen(
        command,
        cwd=cwd,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
    )

    root_create_time = process_create_time(process.pid)
    manifest = {
        "schema_version": "expmon.v1",
        "run": {
            "run_id": run_id,
            "project": args.project,
            "name": args.name,
            "status": "running",
            "resource_type": args.resource_type,
            "tags": args.tag,
        },
        "host": {
            "host_id": args.host_id or socket.gethostname(),
            "hostname": socket.gethostname(),
            "user": os.environ.get("USERNAME") or os.environ.get("USER") or "local",
        },
        "entrypoint": {
            "kind": infer_entrypoint(command),
            "command": " ".join(command),
            "cwd": cwd,
        },
        "process": {
            "root_pid": process.pid,
            "root_create_time": root_create_time,
        },
        "time": {"started_at": started_at},
    }
    write_yaml(run_dir / "manifest.yaml", manifest)
    write_json(
        run_dir / "status.json",
        {
            "status": "running",
            "launcher": "expmon",
            "pid": process.pid,
            "command": " ".join(command),
            "cwd": cwd,
            "started_at": started_at,
        },
    )

    print(f"expmon run_id={run_id}")
    print(f"expmon run_dir={run_dir}")

    events: "queue.Queue[dict[str, Any]]" = queue.Queue()
    stdout_thread = threading.Thread(
        target=stream_reader,
        args=(process.stdout, run_dir / "stdout.log", sys.stdout, metrics_path, events_path, events),
        daemon=True,
    )
    stderr_thread = threading.Thread(
        target=stream_reader,
        args=(process.stderr, run_dir / "stderr.log", sys.stderr, metrics_path, events_path, events),
        daemon=True,
    )
    stdout_thread.start()
    stderr_thread.start()
    exit_code = process.wait()
    stdout_thread.join(timeout=2)
    stderr_thread.join(timeout=2)

    ended_at = now_iso()
    final_status = "finished" if exit_code == 0 else "failed"
    manifest["run"]["status"] = final_status
    manifest["time"]["ended_at"] = ended_at
    write_yaml(run_dir / "manifest.yaml", manifest)
    write_json(
        run_dir / "status.json",
        {
            "status": final_status,
            "launcher": "expmon",
            "pid": process.pid,
            "exit_code": exit_code,
            "command": " ".join(command),
            "cwd": cwd,
            "started_at": started_at,
            "ended_at": ended_at,
        },
    )
    return int(exit_code)


def log_metric(args: argparse.Namespace) -> int:
    run_dir_text = args.run_dir or os.environ.get("EXPMON_RUN_DIR")
    if not run_dir_text:
        print("EXPMON_RUN_DIR is not set; pass --run-dir or use expmon launch", file=sys.stderr)
        return 2
    run_dir = Path(run_dir_text)
    run_dir.mkdir(parents=True, exist_ok=True)
    metrics = parse_key_values(args.metric)
    payload: dict[str, Any] = {"ts": now_iso(), "metrics": metrics}
    if args.step is not None:
        payload["step"] = args.step
    append_jsonl(run_dir / "metrics.jsonl", payload)
    return 0


def log_event(args: argparse.Namespace) -> int:
    run_dir_text = args.run_dir or os.environ.get("EXPMON_RUN_DIR")
    if not run_dir_text:
        print("EXPMON_RUN_DIR is not set; pass --run-dir or use expmon launch", file=sys.stderr)
        return 2
    run_dir = Path(run_dir_text)
    run_dir.mkdir(parents=True, exist_ok=True)
    fields = parse_key_values(args.field)
    payload = event_payload({
        **fields,
        "type": args.type,
        "severity": args.severity,
        "message": args.message or args.type,
    })
    append_jsonl(run_dir / "events.jsonl", payload)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="expmon", description="Experiment monitor launcher and metric logger")
    subparsers = parser.add_subparsers(dest="command_name", required=True)

    launch_parser = subparsers.add_parser("launch", help="launch a command as a managed experiment run")
    launch_parser.add_argument("--project", required=True)
    launch_parser.add_argument("--name", required=True)
    launch_parser.add_argument("--logdir")
    launch_parser.add_argument("--cwd")
    launch_parser.add_argument("--host-id")
    launch_parser.add_argument("--resource-type", default="unknown", choices=["cpu_only", "gpu", "hybrid", "unknown"])
    launch_parser.add_argument("--hparams")
    launch_parser.add_argument("--tag", action="append", default=[])
    launch_parser.add_argument("command", nargs=argparse.REMAINDER)
    launch_parser.set_defaults(func=launch)

    log_parser = subparsers.add_parser("log", help="append metrics to the current managed run")
    log_parser.add_argument("--run-dir")
    log_parser.add_argument("--step", type=int)
    log_parser.add_argument("metric", nargs="+")
    log_parser.set_defaults(func=log_metric)

    event_parser = subparsers.add_parser("event", help="append an event to the current managed run")
    event_parser.add_argument("--run-dir")
    event_parser.add_argument("--type", required=True)
    event_parser.add_argument("--severity", default="info", choices=["info", "warning", "error"])
    event_parser.add_argument("--message", default="")
    event_parser.add_argument("field", nargs="*")
    event_parser.set_defaults(func=log_event)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
