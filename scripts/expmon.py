import argparse
import getpass
import json
import os
import platform
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
DEFAULT_AGENT_PORT = 5194
DISCOVERY_CAPABILITIES = [
    "host",
    "gpu",
    "gpu_process",
    "process",
    "runs",
    "adopt",
    "memory_breakdown",
    "disk_network",
]


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


def package_version() -> str:
    try:
        package = json.loads((APP_ROOT / "package.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return "0.0.0"
    return str(package.get("version") or "0.0.0")


def discovery_path() -> Path:
    if os.name == "nt":
        root = os.environ.get("LOCALAPPDATA")
        base = Path(root) if root else Path.home() / "AppData" / "Local"
        return base / "ExpMon" / "discovery.json"
    root = os.environ.get("XDG_CONFIG_HOME")
    base = Path(root) if root else Path.home() / ".config"
    return base / "expmon" / "discovery.json"


def pid_alive(pid: Any) -> bool:
    try:
        value = int(pid)
    except (TypeError, ValueError):
        return False
    if value <= 0:
        return False
    if psutil is not None:
        return psutil.pid_exists(value)
    try:
        os.kill(value, 0)
        return True
    except OSError:
        return False


def read_discovery_manifest() -> dict[str, Any]:
    path = discovery_path()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def discover(args: argparse.Namespace) -> int:
    manifest = read_discovery_manifest()
    agent = manifest.get("agent") if isinstance(manifest.get("agent"), dict) else {}
    agent_running = bool(agent.get("running")) and pid_alive(agent.get("pid"))
    payload = {
        "ok": True,
        "name": "ExpMon",
        "version": package_version(),
        "platform": platform.system().lower(),
        "os": platform.platform(),
        "hostname": socket.gethostname(),
        "user": getpass.getuser(),
        "pythonPath": sys.executable,
        "installRoot": str(APP_ROOT),
        "discoveryPath": str(discovery_path()),
        "agent": {
            "installed": (APP_ROOT / "scripts" / "remote_agent.py").exists(),
            "running": agent_running,
            "bind": str(agent.get("bind") or "127.0.0.1"),
            "port": int(agent.get("port") or DEFAULT_AGENT_PORT),
            "pid": int(agent.get("pid") or 0) if str(agent.get("pid") or "").isdigit() else 0,
            "updatedAt": str(agent.get("updatedAt") or ""),
        },
        "capabilities": DISCOVERY_CAPABILITIES,
    }
    print(json.dumps(payload, ensure_ascii=False if getattr(args, "json", False) else True, indent=None if getattr(args, "json", False) else 2))
    return 0


def agent_start(args: argparse.Namespace) -> int:
    agent_path = APP_ROOT / "scripts" / "remote_agent.py"
    if not agent_path.exists():
        print(json.dumps({"ok": False, "error": "remote_agent.py not found", "installRoot": str(APP_ROOT)}))
        return 2
    command = [
        sys.executable,
        str(agent_path),
        "--host",
        args.bind,
        "--port",
        str(args.port),
    ]
    if args.background:
        kwargs: dict[str, Any] = {
            "cwd": str(APP_ROOT),
            "stdin": subprocess.DEVNULL,
            "stdout": subprocess.DEVNULL,
            "stderr": subprocess.DEVNULL,
            "start_new_session": os.name != "nt",
        }
        if os.name == "nt":
            kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(subprocess, "DETACHED_PROCESS", 0)
        process = subprocess.Popen(command, **kwargs)
        time.sleep(0.4)
        print(json.dumps({
            "ok": True,
            "agent": {
                "running": True,
                "pid": process.pid,
                "bind": args.bind,
                "port": args.port,
            },
        }))
        return 0
    return subprocess.call(command, cwd=str(APP_ROOT))


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


def adopt(args: argparse.Namespace) -> int:
    if psutil is None:
        print("expmon adopt requires psutil", file=sys.stderr)
        return 2

    try:
        process = psutil.Process(args.pid)
        if not process.is_running() or process.status() == psutil.STATUS_ZOMBIE:
            raise psutil.NoSuchProcess(args.pid)
    except (psutil.NoSuchProcess, psutil.ZombieProcess):
        print(f"process {args.pid} is not running", file=sys.stderr)
        return 2
    except psutil.AccessDenied:
        print(f"access denied while inspecting process {args.pid}", file=sys.stderr)
        return 2

    with process.oneshot():
        try:
            process_command = " ".join(process.cmdline())
        except (psutil.AccessDenied, psutil.NoSuchProcess):
            process_command = ""
        try:
            process_cwd = process.cwd()
        except (psutil.AccessDenied, psutil.NoSuchProcess):
            process_cwd = ""
        try:
            process_user = process.username()
        except (psutil.AccessDenied, psutil.NoSuchProcess):
            process_user = os.environ.get("USERNAME") or os.environ.get("USER") or "local"
        try:
            root_create_time = float(process.create_time())
        except (psutil.AccessDenied, psutil.NoSuchProcess):
            print(f"could not read the create time for process {args.pid}", file=sys.stderr)
            return 2

    command = str(args.command_text or process_command or f"pid {args.pid}")
    cwd = str(Path(args.cwd).resolve()) if args.cwd else (process_cwd or os.getcwd())
    logdir = Path(args.logdir or os.environ.get("EXPMON_LOGDIR") or DEFAULT_LOGDIR)
    run_id, run_dir = make_run_dir(logdir, args.project, args.name)
    (run_dir / "metrics.jsonl").touch()
    (run_dir / "events.jsonl").touch()
    copy_hparams(args.hparams, run_dir)

    started_at = datetime.fromtimestamp(root_create_time).isoformat(timespec="seconds")
    adopted_at = now_iso()
    tags = list(dict.fromkeys([*args.tag, "adopted"]))
    manifest: dict[str, Any] = {
        "schema_version": "expmon.v1",
        "run": {
            "run_id": run_id,
            "project": args.project,
            "name": args.name,
            "status": "running",
            "resource_type": args.resource_type,
            "tags": tags,
        },
        "host": {
            "host_id": args.host_id or socket.gethostname(),
            "hostname": socket.gethostname(),
            "user": process_user,
        },
        "entrypoint": {
            "kind": infer_entrypoint(command.split()),
            "command": command,
            "cwd": cwd,
        },
        "process": {
            "root_pid": args.pid,
            "root_create_time": root_create_time,
            "adopted": True,
        },
        "time": {"started_at": started_at, "adopted_at": adopted_at},
    }
    if args.log_file:
        manifest["logs"] = {"stdout": str(Path(args.log_file).expanduser().resolve())}

    write_yaml(run_dir / "manifest.yaml", manifest)
    write_json(
        run_dir / "status.json",
        {
            "status": "running",
            "launcher": "expmon-adopt",
            "pid": args.pid,
            "command": command,
            "cwd": cwd,
            "started_at": started_at,
            "adopted_at": adopted_at,
        },
    )
    append_jsonl(
        run_dir / "events.jsonl",
        {
            "ts": adopted_at,
            "type": "adopted",
            "severity": "info",
            "message": f"adopted existing process {args.pid}",
            "fields": {"pid": args.pid, "historicalCapture": False},
        },
    )
    try:
        import local_collector

        imported = local_collector.import_tensorboard_metrics(
            run_dir,
            command,
            cwd,
            manifest.get("logs") if isinstance(manifest.get("logs"), dict) else {},
        )
        if int(imported.get("imported") or 0) > 0:
            append_jsonl(
                run_dir / "events.jsonl",
                {
                    "ts": now_iso(),
                    "type": "tensorboard_metrics_imported",
                    "severity": "info",
                    "message": "imported existing TensorBoard scalar metrics",
                    "fields": {
                        "values": int(imported.get("imported") or 0),
                        "tags": list(imported.get("tags") or []),
                    },
                },
            )
    except Exception as exc:
        append_jsonl(
            run_dir / "events.jsonl",
            {
                "ts": now_iso(),
                "type": "tensorboard_import_warning",
                "severity": "warning",
                "message": f"TensorBoard metric import skipped: {exc}",
            },
        )
    print(f"expmon adopted pid={args.pid}")
    print(f"expmon run_id={run_id}")
    print(f"expmon run_dir={run_dir}")
    return 0


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

    adopt_parser = subparsers.add_parser("adopt", help="register an already-running process without restarting it")
    adopt_parser.add_argument("--pid", required=True, type=int)
    adopt_parser.add_argument("--project", required=True)
    adopt_parser.add_argument("--name", required=True)
    adopt_parser.add_argument("--logdir")
    adopt_parser.add_argument("--cwd")
    adopt_parser.add_argument("--host-id")
    adopt_parser.add_argument("--resource-type", default="unknown", choices=["cpu_only", "gpu", "hybrid", "unknown"])
    adopt_parser.add_argument("--hparams")
    adopt_parser.add_argument("--tag", action="append", default=[])
    adopt_parser.add_argument("--command", dest="command_text", help="override the command read from the process")
    adopt_parser.add_argument("--log-file", help="tail an existing nohup/stdout log from the run detail page")
    adopt_parser.set_defaults(func=adopt)

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

    discover_parser = subparsers.add_parser("discover", help="print ExpMon installation and agent discovery JSON")
    discover_parser.add_argument("--json", action="store_true", help="emit compact JSON for machine parsing")
    discover_parser.set_defaults(func=discover)

    agent_parser = subparsers.add_parser("agent", help="manage the lightweight remote agent")
    agent_subparsers = agent_parser.add_subparsers(dest="agent_command", required=True)
    agent_start_parser = agent_subparsers.add_parser("start", help="start the lightweight remote agent")
    agent_start_parser.add_argument("--bind", default="127.0.0.1")
    agent_start_parser.add_argument("--port", type=int, default=DEFAULT_AGENT_PORT)
    agent_start_parser.add_argument("--background", action="store_true")
    agent_start_parser.set_defaults(func=agent_start)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
