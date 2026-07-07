import base64
import hashlib
import json
import os
import re
import shlex
import shutil
import socket
import subprocess
import sys
import threading
import time
import uuid
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

import psutil

try:
    import yaml
except ImportError:  # pragma: no cover - PyYAML is listed in the project docs, but keep collector resilient.
    yaml = None


APP_ROOT = Path(__file__).resolve().parents[1]
PORT = int(os.environ.get("EXPMON_COLLECTOR_PORT", "5184"))
SAMPLE_CONFIG_PATH = APP_ROOT / "expmon.yaml"
CONFIG_FILE = Path(os.environ.get("EXPMON_CONFIG", APP_ROOT / "expmon-local.yaml"))
LATEST_SNAPSHOT: dict[str, Any] | None = None
SNAPSHOT_LOCK = threading.Lock()
MANIFEST_CACHE: tuple[float, list[Path]] = (0, [])
RUN_RESOURCE_HISTORY: dict[str, list[dict[str, Any]]] = {}
PROCESS_CPU_HISTORY: dict[int, tuple[float, float]] = {}
RUN_IO_HISTORY: dict[str, tuple[float, float, float]] = {}
HOST_IO_HISTORY: tuple[float, float, float, float, float] | None = None
HOST_RESOURCE_HISTORY: dict[str, list[dict[str, Any]]] = {}
DELETABLE_RUN_STATUSES = {"finished", "failed", "killed"}
SSH_SERVERS_PATH = Path(os.environ.get("EXPMON_SSH_SERVERS", APP_ROOT / "expmon-ssh-servers.json"))
RUN_METADATA_PATH = Path(os.environ.get("EXPMON_RUN_METADATA", APP_ROOT / "expmon-run-metadata.json"))
VISUALIZATION_PROCESSES: dict[str, dict[str, Any]] = {}


DEFAULT_CONFIG: dict[str, Any] = {
    "host_id": "local",
    "sampling": {"interval_seconds": 3, "unmanaged_top_n": 80},
    "experiment_roots": [str(APP_ROOT)],
    "run_discovery": {
        "include_command_keywords": [
            "train",
            "retrain",
            "fit",
            "finetune",
            "fold",
            "torchrun",
            "deepspeed",
        ],
        "exclude_command_keywords": [
            "expmon-frontend",
            "codegraph",
            "local_collector.py",
            "local_collector",
            "Get-CimInstance Win32_Process",
            "collect_snapshot",
            "playwright",
            "vite",
            "node_modules",
        ],
        "include_cwd_under": [str(APP_ROOT)],
        "explicit_rules": [],
    },
    "protocol": {
        "scan_roots": [str(APP_ROOT / "expmon-runs")],
        "manifest_cache_seconds": 3,
        "max_scan_depth": 5,
        "max_metric_points": 120,
    },
}

RUNNER_NAME_HINTS = (
    "python",
    "torchrun",
    "deepspeed",
    "accelerate",
    "rscript",
    "julia",
    "powershell",
    "pwsh",
    "bash",
    "cmd",
)


def deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def config_path(value: Any) -> Path:
    path = Path(os.path.expandvars(os.path.expanduser(str(value))))
    return path if path.is_absolute() else APP_ROOT / path


def read_yaml_file(path: Path) -> dict[str, Any]:
    if not path.exists() or yaml is None:
        return {}
    try:
        loaded = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}
    return loaded if isinstance(loaded, dict) else {}


def load_config() -> dict[str, Any]:
    loaded = deep_merge(json.loads(json.dumps(DEFAULT_CONFIG)), read_yaml_file(SAMPLE_CONFIG_PATH))
    active_path = config_path(CONFIG_FILE)
    if active_path.resolve() != SAMPLE_CONFIG_PATH.resolve():
        loaded = deep_merge(loaded, read_yaml_file(active_path))
    return loaded


CONFIG = load_config()
SAMPLE_INTERVAL_SECONDS = max(1, int(CONFIG.get("sampling", {}).get("interval_seconds", 3)))


def read_json_body(handler: BaseHTTPRequestHandler) -> dict[str, Any]:
    length = int(handler.headers.get("Content-Length") or 0)
    if length <= 0:
        return {}
    raw = handler.rfile.read(length)
    try:
        parsed = json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def read_json_file(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def write_json_file(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def int_setting(value: Any, default: int, minimum: int = 1, maximum: int = 100000) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(maximum, parsed))


def config_metadata() -> dict[str, Any]:
    active_path = config_path(CONFIG_FILE)
    return {
        "path": str(active_path),
        "samplePath": str(SAMPLE_CONFIG_PATH),
        "usingEnvConfig": bool(os.environ.get("EXPMON_CONFIG")),
        "writable": yaml is not None,
    }


def normalize_collector_config(raw: dict[str, Any]) -> dict[str, Any]:
    sampling = raw.get("sampling") if isinstance(raw.get("sampling"), dict) else {}
    discovery = raw.get("run_discovery") if isinstance(raw.get("run_discovery"), dict) else {}
    protocol = raw.get("protocol") if isinstance(raw.get("protocol"), dict) else {}
    explicit_rules: list[dict[str, str]] = []
    for rule in discovery.get("explicit_rules") or []:
        if not isinstance(rule, dict):
            continue
        next_rule = {
            "name": str(rule.get("name") or "").strip(),
            "project": str(rule.get("project") or "").strip(),
            "command_regex": str(rule.get("command_regex") or "").strip(),
        }
        if any(next_rule.values()):
            explicit_rules.append(next_rule)
    return {
        "host_id": str(raw.get("host_id") or "local").strip() or "local",
        "sampling": {
            "interval_seconds": int_setting(sampling.get("interval_seconds"), 3, 1, 3600),
            "unmanaged_top_n": int_setting(sampling.get("unmanaged_top_n"), 80, 1, 1000),
        },
        "experiment_roots": string_list(raw.get("experiment_roots")),
        "run_discovery": {
            "include_command_keywords": string_list(discovery.get("include_command_keywords")),
            "exclude_command_keywords": string_list(discovery.get("exclude_command_keywords")),
            "include_cwd_under": string_list(discovery.get("include_cwd_under")),
            "explicit_rules": explicit_rules,
        },
        "protocol": {
            "scan_roots": string_list(protocol.get("scan_roots")),
            "manifest_cache_seconds": int_setting(protocol.get("manifest_cache_seconds"), 3, 1, 3600),
            "max_scan_depth": int_setting(protocol.get("max_scan_depth"), 5, 1, 25),
            "max_metric_points": int_setting(protocol.get("max_metric_points"), 120, 10, 10000),
        },
    }


def write_yaml_config(path: Path, payload: dict[str, Any]) -> None:
    if yaml is None:
        raise RuntimeError("PyYAML is required to save collector config")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(payload, allow_unicode=True, sort_keys=False), encoding="utf-8")


def save_collector_config(payload: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    global CONFIG, SAMPLE_INTERVAL_SECONDS, LATEST_SNAPSHOT, MANIFEST_CACHE
    incoming = payload.get("config") if isinstance(payload.get("config"), dict) else payload
    if not isinstance(incoming, dict):
        return 400, {"ok": False, "error": "config payload must be an object"}
    next_config = normalize_collector_config(deep_merge(CONFIG, incoming))
    try:
        write_yaml_config(config_path(CONFIG_FILE), next_config)
    except Exception as exc:
        return 500, {"ok": False, "error": str(exc), "metadata": config_metadata()}

    CONFIG = next_config
    SAMPLE_INTERVAL_SECONDS = max(1, int(CONFIG.get("sampling", {}).get("interval_seconds", 3)))
    MANIFEST_CACHE = (0, [])
    with SNAPSHOT_LOCK:
        LATEST_SNAPSHOT = None
    return 200, {"ok": True, "config": CONFIG, "metadata": config_metadata()}


def read_run_metadata_raw() -> dict[str, Any]:
    payload = read_json_file(RUN_METADATA_PATH, {})
    return payload if isinstance(payload, dict) else {}


def run_metadata_for(run_id: str) -> dict[str, Any]:
    all_metadata = read_run_metadata_raw()
    item = all_metadata.get(run_id)
    if not isinstance(item, dict):
        return {"note": "", "mark": "", "pinned": False, "updatedAt": ""}
    return {
        "note": str(item.get("note") or ""),
        "mark": str(item.get("mark") or ""),
        "pinned": bool(item.get("pinned")),
        "updatedAt": str(item.get("updatedAt") or ""),
    }


def save_run_metadata(run_id: str, payload: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    global LATEST_SNAPSHOT
    allowed_marks = {"", "baseline", "bad", "debug", "candidate", "important"}
    current = run_metadata_for(run_id)
    if "note" in payload:
        current["note"] = str(payload.get("note") or "")[:5000]
    if "mark" in payload:
        mark = str(payload.get("mark") or "")
        if mark not in allowed_marks:
            return 400, {"ok": False, "error": "invalid mark"}
        current["mark"] = mark
    if "pinned" in payload:
        current["pinned"] = bool(payload.get("pinned"))
    current["updatedAt"] = datetime.now().isoformat(timespec="seconds")

    all_metadata = read_run_metadata_raw()
    if current["note"] or current["mark"] or current["pinned"]:
        all_metadata[run_id] = current
    else:
        all_metadata.pop(run_id, None)
    write_json_file(RUN_METADATA_PATH, all_metadata)
    with SNAPSHOT_LOCK:
        LATEST_SNAPSHOT = None
    return 200, {"ok": True, "runId": run_id, "metadata": current}


def read_ssh_servers_raw() -> list[dict[str, Any]]:
    if not SSH_SERVERS_PATH.exists():
        return []
    try:
        payload = json.loads(SSH_SERVERS_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    servers = payload.get("servers") if isinstance(payload, dict) else payload
    return servers if isinstance(servers, list) else []


def write_ssh_servers_raw(servers: list[dict[str, Any]]) -> None:
    SSH_SERVERS_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "updatedAt": datetime.now().isoformat(timespec="seconds"),
        "warning": "Passwords are stored locally because password auth was explicitly enabled in the UI.",
        "servers": servers,
    }
    SSH_SERVERS_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        os.chmod(SSH_SERVERS_PATH, 0o600)
    except OSError:
        pass


def public_ssh_server(server: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(server.get("id") or ""),
        "name": str(server.get("name") or server.get("host") or "ssh-host"),
        "host": str(server.get("host") or ""),
        "port": int(server.get("port") or 22),
        "username": str(server.get("username") or ""),
        "authType": str(server.get("authType") or "key"),
        "keyPath": str(server.get("keyPath") or ""),
        "hasPassword": bool(server.get("password")),
        "createdAt": str(server.get("createdAt") or ""),
        "updatedAt": str(server.get("updatedAt") or ""),
    }


def ssh_key_candidates() -> list[str]:
    ssh_dir = Path.home() / ".ssh"
    names = ["id_ed25519", "id_rsa", "id_ecdsa", "id_dsa"]
    excluded_names = {"authorized_keys", "known_hosts", "known_hosts.old", "config"}
    candidates: list[str] = []
    for name in names:
        path = ssh_dir / name
        if path.exists():
            candidates.append(str(path))
    try:
        for path in ssh_dir.glob("*"):
            if path.is_file() and not path.name.endswith(".pub") and path.name not in excluded_names and str(path) not in candidates:
                candidates.append(str(path))
    except OSError:
        pass
    return candidates


def ssh_servers_payload() -> dict[str, Any]:
    servers = dedupe_ssh_servers(read_ssh_servers_raw())
    return {
        "servers": [public_ssh_server(server) for server in servers],
        "keyCandidates": ssh_key_candidates(),
        "storagePath": str(SSH_SERVERS_PATH),
    }


def save_ssh_server(payload: dict[str, Any], persist: bool = True) -> tuple[int, dict[str, Any]]:
    host = str(payload.get("host") or "").strip()
    username = str(payload.get("username") or "").strip()
    auth_type = str(payload.get("authType") or "key").strip().lower()
    name = str(payload.get("name") or host).strip()
    key_path = str(payload.get("keyPath") or "").strip()
    password = str(payload.get("password") or "")
    try:
        port = int(payload.get("port") or 22)
    except (TypeError, ValueError):
        port = 22

    if not host:
        return 400, {"ok": False, "error": "host is required"}
    if not username:
        return 400, {"ok": False, "error": "username is required"}
    if port <= 0 or port > 65535:
        return 400, {"ok": False, "error": "port must be 1-65535"}
    if auth_type not in {"key", "password"}:
        return 400, {"ok": False, "error": "authType must be key or password"}
    if auth_type == "key" and not key_path:
        return 400, {"ok": False, "error": "keyPath is required for key auth"}
    if auth_type == "password" and not password:
        return 400, {"ok": False, "error": "password is required for password auth"}

    now = datetime.now().isoformat(timespec="seconds")
    servers = dedupe_ssh_servers(read_ssh_servers_raw())
    server_id = str(payload.get("id") or uuid.uuid4().hex[:12])
    existing = next((server for server in servers if str(server.get("id")) == server_id), None)
    duplicate = next((
        server for server in servers
        if str(server.get("id")) != server_id
        and ssh_server_key(server) == (host.lower(), username.lower(), port)
    ), None)
    if duplicate:
        return 409, {
            "ok": False,
            "error": "ssh server already exists",
            "server": public_ssh_server(duplicate),
        }
    next_doc = {
        "id": server_id,
        "name": name or host,
        "host": host,
        "port": port,
        "username": username,
        "authType": auth_type,
        "keyPath": key_path if auth_type == "key" else "",
        "password": password if auth_type == "password" else "",
        "createdAt": str(existing.get("createdAt")) if existing else now,
        "updatedAt": now,
    }
    if existing:
        servers = [next_doc if str(server.get("id")) == server_id else server for server in servers]
    else:
        servers.append(next_doc)
    if persist:
        write_ssh_servers_raw(servers)
        return 200, {"ok": True, "server": public_ssh_server(next_doc), "storagePath": str(SSH_SERVERS_PATH)}
    return 200, {
        "ok": True,
        "server": public_ssh_server(next_doc),
        "serverDoc": next_doc,
        "servers": servers,
        "storagePath": str(SSH_SERVERS_PATH),
    }


def validate_and_save_ssh_server(payload: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    status, saved = save_ssh_server(payload, persist=False)
    if status != 200:
        return status, saved
    server = saved.get("serverDoc")
    if not isinstance(server, dict):
        return 500, {"ok": False, "error": "failed to prepare ssh server"}
    test_payload = test_ssh_server_doc(server)
    write_ssh_servers_raw(saved.get("servers", []))
    return 200, {
        "ok": True,
        "server": public_ssh_server(server),
        "test": test_payload,
        "warning": "" if test_payload.get("ok") else (test_payload.get("message") or "ssh connection test failed"),
        "storagePath": str(SSH_SERVERS_PATH),
    }


def delete_ssh_server(server_id: str) -> tuple[int, dict[str, Any]]:
    servers = dedupe_ssh_servers(read_ssh_servers_raw())
    next_servers = [server for server in servers if str(server.get("id")) != server_id]
    if len(next_servers) == len(servers):
        return 404, {"ok": False, "error": "ssh server not found"}
    write_ssh_servers_raw(next_servers)
    return 200, {"ok": True, "serverId": server_id}


def clear_ssh_servers() -> tuple[int, dict[str, Any]]:
    write_ssh_servers_raw([])
    return 200, {"ok": True, "deleted": True}


def ssh_server_key(server: dict[str, Any]) -> tuple[str, str, int]:
    return (
        str(server.get("host") or "").strip().lower(),
        str(server.get("username") or "").strip().lower(),
        int(server.get("port") or 22),
    )


def dedupe_ssh_servers(servers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[str, str, int]] = set()
    deduped = []
    for server in servers:
        key = ssh_server_key(server)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(server)
    return deduped


def ssh_server_by_id(server_id: str) -> dict[str, Any] | None:
    return next((server for server in read_ssh_servers_raw() if str(server.get("id")) == server_id), None)


def resolve_ssh_key_path(key_path: str) -> Path:
    path = config_path(key_path) if not Path(key_path).expanduser().is_absolute() else Path(key_path).expanduser()
    if path.is_dir():
        for name in ("id_ed25519", "id_rsa", "id_ecdsa", "id_dsa"):
            candidate = path / name
            if candidate.exists():
                return candidate
    return path


def ssh_command_for_server(server: dict[str, Any], remote_command: str) -> tuple[list[str] | None, dict[str, Any] | None]:
    auth_type = str(server.get("authType") or "key")
    if auth_type == "password" and not shutil.which("sshpass"):
        return None, {
            "ok": False,
            "supported": False,
            "server": public_ssh_server(server),
            "testedAt": datetime.now().isoformat(timespec="seconds"),
            "message": "password auth is saved locally, but non-interactive testing requires sshpass or a key",
        }

    ssh_binary = shutil.which("ssh")
    if not ssh_binary:
        return None, {
            "ok": False,
            "supported": False,
            "server": public_ssh_server(server),
            "testedAt": datetime.now().isoformat(timespec="seconds"),
            "message": "ssh command is not available on this machine",
        }

    host = str(server.get("host") or "")
    username = str(server.get("username") or "")
    port = str(int(server.get("port") or 22))
    target = f"{username}@{host}"
    command = [
        ssh_binary,
        "-p",
        port,
        "-o",
        "ConnectTimeout=6",
        "-o",
        "StrictHostKeyChecking=accept-new",
    ]
    if auth_type == "key":
        key_path = str(server.get("keyPath") or "").strip()
        if not key_path:
            return None, {"ok": False, "error": "keyPath is missing", "server": public_ssh_server(server)}
        command.extend(["-o", "BatchMode=yes"])
        command.extend(["-i", str(resolve_ssh_key_path(key_path))])
    else:
        command = ["sshpass", "-p", str(server.get("password") or ""), *command]
    command.extend([target, remote_command])
    return command, None


def test_ssh_server_doc(server: dict[str, Any]) -> dict[str, Any]:
    command, error_payload = ssh_command_for_server(server, "echo EXPMON_SSH_OK && hostname")
    if error_payload:
        return error_payload
    if not command:
        return {"ok": False, "error": "failed to build ssh command", "server": public_ssh_server(server)}

    started = time.time()
    try:
        completed = subprocess.run(
            command,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            timeout=12,
        )
    except subprocess.TimeoutExpired:
        return {
            "ok": False,
            "supported": True,
            "server": public_ssh_server(server),
            "testedAt": datetime.now().isoformat(timespec="seconds"),
            "latencyMs": int((time.time() - started) * 1000),
            "message": "ssh test timed out",
        }

    stdout = completed.stdout.strip()
    stderr = completed.stderr.strip()
    lines = [line.strip() for line in stdout.splitlines() if line.strip()]
    ok = completed.returncode == 0 and "EXPMON_SSH_OK" in lines
    hostname = next((line for line in lines if line != "EXPMON_SSH_OK"), "")
    return {
        "ok": ok,
        "supported": True,
        "server": public_ssh_server(server),
        "testedAt": datetime.now().isoformat(timespec="seconds"),
        "latencyMs": int((time.time() - started) * 1000),
        "hostname": hostname,
        "stdout": stdout[:2000],
        "stderr": stderr[:2000],
        "message": "ssh connection ok" if ok else (stderr or stdout or f"ssh exited with {completed.returncode}"),
    }


def test_ssh_server(server_id: str) -> tuple[int, dict[str, Any]]:
    server = ssh_server_by_id(server_id)
    if not server:
        return 404, {"ok": False, "error": "ssh server not found"}

    return 200, test_ssh_server_doc(server)


REMOTE_RESOURCE_SCRIPT = r"""
import json
import os
import platform
import subprocess
import time


def cpu_snapshot():
    try:
        with open("/proc/stat", "r", encoding="utf-8") as handle:
            parts = handle.readline().split()[1:]
        values = [int(value) for value in parts[:8]]
        idle = values[3] + values[4]
        total = sum(values)
        return idle, total
    except Exception:
        return 0, 0


def cpu_usage():
    idle1, total1 = cpu_snapshot()
    time.sleep(0.2)
    idle2, total2 = cpu_snapshot()
    total_delta = total2 - total1
    idle_delta = idle2 - idle1
    if total_delta <= 0:
        return 0
    return round(max(0, min(100, (1 - idle_delta / total_delta) * 100)), 1)


def memory():
    values = {}
    try:
        with open("/proc/meminfo", "r", encoding="utf-8") as handle:
            for line in handle:
                key, raw = line.split(":", 1)
                values[key] = int(raw.strip().split()[0])
    except Exception:
        return 0, 0
    total = values.get("MemTotal", 0) / 1024 / 1024
    available = values.get("MemAvailable", 0) / 1024 / 1024
    return round(total - available, 2), round(total, 2)


def cpu_cores():
    try:
        count = os.cpu_count() or 0
        return [0 for _ in range(count)]
    except Exception:
        return []


def gpus():
    query = "index,uuid,name,memory.total,memory.used,utilization.gpu,power.draw,power.limit,temperature.gpu"
    try:
        result = subprocess.run(
            ["nvidia-smi", f"--query-gpu={query}", "--format=csv,noheader,nounits"],
            capture_output=True,
            text=True,
            timeout=3,
        )
    except Exception:
        return []
    if result.returncode != 0:
        return []
    rows = []
    for line in result.stdout.splitlines():
        parts = [part.strip() for part in line.split(",")]
        if len(parts) < 9:
            continue
        try:
            total = float(parts[3])
            used = float(parts[4])
            util = float(parts[5])
            rows.append({
                "index": int(float(parts[0])),
                "uuid": parts[1],
                "name": parts[2],
                "memoryTotalMiB": total,
                "memoryUsedMiB": used,
                "memoryPercent": round((used / total) * 100, 1) if total else 0,
                "utilization": util,
                "powerDrawW": float(parts[6] or 0),
                "powerLimitW": float(parts[7] or 0),
                "temperatureC": float(parts[8] or 0),
                "busy": util > 0 or used > 0,
                "processes": [],
            })
        except Exception:
            continue
    return rows


memory_used, memory_total = memory()
gpu_rows = gpus()
print(json.dumps({
    "hostname": platform.node(),
    "os": platform.platform(),
    "user": os.environ.get("USER") or os.environ.get("LOGNAME") or "",
    "cpuUsage": cpu_usage(),
    "cores": cpu_cores(),
    "memoryUsedGb": memory_used,
    "memoryTotalGb": memory_total,
    "gpus": gpu_rows,
    "gpusTotal": len(gpu_rows),
    "gpusBusy": sum(1 for gpu in gpu_rows if gpu.get("busy")),
}))
"""


def run_ssh_remote_command(server: dict[str, Any], remote_command: str, timeout: int = 15) -> tuple[subprocess.CompletedProcess[str] | None, dict[str, Any] | None, int]:
    command, error_payload = ssh_command_for_server(server, remote_command)
    if error_payload:
        return None, error_payload, 400 if error_payload.get("error") else 200
    if not command:
        return None, {"ok": False, "error": "failed to build ssh command", "server": public_ssh_server(server)}, 500
    try:
        completed = subprocess.run(
            command,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return None, {"ok": False, "supported": True, "message": "remote command timed out"}, 200
    return completed, None, 200


def detect_remote_os(server: dict[str, Any]) -> str:
    completed, _, _ = run_ssh_remote_command(server, "uname -s", timeout=6)
    if completed and completed.returncode == 0:
        value = completed.stdout.strip().lower()
        if "darwin" in value:
            return "macos"
        if "linux" in value:
            return "linux"
    completed, _, _ = run_ssh_remote_command(server, "ver", timeout=6)
    if completed and completed.returncode == 0 and "windows" in (completed.stdout + completed.stderr).lower():
        return "windows"
    return "unknown"


WINDOWS_RESOURCE_SCRIPT = r'''
$ErrorActionPreference = 'SilentlyContinue'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8
$os = Get-CimInstance Win32_OperatingSystem
$processors = @(Get-CimInstance Win32_Processor)
$logical = 0
$loadValues = @()
foreach ($processor in $processors) {
  $logical += [int]($processor.NumberOfLogicalProcessors)
  if ($null -ne $processor.LoadPercentage) { $loadValues += [double]$processor.LoadPercentage }
}
if ($logical -le 0) { $logical = [Environment]::ProcessorCount }
$cpuUsage = 0
if ($loadValues.Count -gt 0) { $cpuUsage = [Math]::Round(($loadValues | Measure-Object -Average).Average, 1) }
$memoryTotal = 0
$memoryUsed = 0
if ($os) {
  $memoryTotal = [Math]::Round([double]$os.TotalVisibleMemorySize / 1048576, 2)
  $memoryUsed = [Math]::Round(([double]$os.TotalVisibleMemorySize - [double]$os.FreePhysicalMemory) / 1048576, 2)
}
$gpuRows = @()
$nvidia = Get-Command nvidia-smi -ErrorAction SilentlyContinue
if ($nvidia) {
  $query = 'index,uuid,name,memory.total,memory.used,utilization.gpu,power.draw,power.limit,temperature.gpu'
  $lines = & $nvidia.Source "--query-gpu=$query" "--format=csv,noheader,nounits" 2>$null
  foreach ($line in $lines) {
    $parts = @($line -split ',' | ForEach-Object { $_.Trim() })
    if ($parts.Count -ge 9) {
      $total = [double]($parts[3] -replace '[^0-9\.]','')
      $used = [double]($parts[4] -replace '[^0-9\.]','')
      $util = [double]($parts[5] -replace '[^0-9\.]','')
      $gpuRows += [pscustomobject]@{
        index = [int]$parts[0]
        uuid = $parts[1]
        name = $parts[2]
        memoryTotalMiB = $total
        memoryUsedMiB = $used
        memoryPercent = $(if ($total -gt 0) { [Math]::Round(($used / $total) * 100, 1) } else { 0 })
        utilization = $util
        powerDrawW = [double]($parts[6] -replace '[^0-9\.]','')
        powerLimitW = [double]($parts[7] -replace '[^0-9\.]','')
        temperatureC = [double]($parts[8] -replace '[^0-9\.]','')
        busy = ($util -gt 0 -or $used -gt 0)
        processes = @()
      }
    }
  }
}
[pscustomobject]@{
  hostname = $env:COMPUTERNAME
  os = "windows / $($os.Caption)"
  user = $env:USERNAME
  cpuUsage = $cpuUsage
  cores = @(0..([Math]::Max($logical - 1, 0)) | ForEach-Object { 0 })
  memoryUsedGb = $memoryUsed
  memoryTotalGb = $memoryTotal
  gpus = $gpuRows
  gpusTotal = $gpuRows.Count
  gpusBusy = @($gpuRows | Where-Object { $_.busy }).Count
} | ConvertTo-Json -Compress -Depth 6
'''


def windows_resource_command() -> str:
    encoded = base64.b64encode(WINDOWS_RESOURCE_SCRIPT.encode("utf-16le")).decode("ascii")
    return f"powershell -NoProfile -EncodedCommand {encoded}"


def posix_resource_command() -> str:
    quoted_script = shlex.quote(REMOTE_RESOURCE_SCRIPT)
    candidates = [
        "$HOME/miniconda3/bin/python",
        "$HOME/anaconda3/bin/python",
        "$HOME/mambaforge/bin/python",
        "$HOME/miniforge3/bin/python",
        "$HOME/miniconda/bin/python",
        "$HOME/anaconda/bin/python",
        "/opt/conda/bin/python",
        "/opt/mamba/bin/python",
        "/usr/local/bin/python3",
        "/usr/bin/python3",
        "python3",
        "python",
    ]
    candidate_text = " ".join(f'"{candidate}"' if candidate.startswith("$HOME/") else shlex.quote(candidate) for candidate in candidates)
    return (
        "for py in "
        f"{candidate_text}; do "
        "if [ -x \"$py\" ]; then "
        "echo EXPMON_PYTHON=$py 1>&2; exec \"$py\" -c "
        f"{quoted_script}; "
        "elif command -v \"$py\" >/dev/null 2>&1; then "
        "resolved=$(command -v \"$py\"); echo EXPMON_PYTHON=$resolved 1>&2; exec \"$resolved\" -c "
        f"{quoted_script}; "
        "fi; "
        "done; echo EXPMON_PYTHON_NOT_FOUND 1>&2; exit 127"
    )


def ssh_remote_resource_snapshot(server_id: str) -> tuple[int, dict[str, Any]]:
    server = ssh_server_by_id(server_id)
    if not server:
        return 404, {"ok": False, "error": "ssh server not found"}

    remote_os = detect_remote_os(server)
    if remote_os == "windows":
        remote_command = windows_resource_command()
    else:
        remote_command = posix_resource_command()
    command, error_payload = ssh_command_for_server(server, remote_command)
    if error_payload:
        return 400 if error_payload.get("error") else 200, error_payload
    if not command:
        return 500, {"ok": False, "error": "failed to build ssh command", "server": public_ssh_server(server)}

    started = time.time()
    try:
        completed = subprocess.run(
            command,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            timeout=15,
        )
    except subprocess.TimeoutExpired:
        return 200, {
            "ok": False,
            "supported": True,
            "server": public_ssh_server(server),
            "sampledAt": datetime.now().isoformat(timespec="seconds"),
            "latencyMs": int((time.time() - started) * 1000),
            "message": f"remote {remote_os} resource snapshot timed out",
        }

    stdout = completed.stdout.strip()
    stderr = completed.stderr.strip()
    python_path = ""
    for line in stderr.splitlines():
        if line.startswith("EXPMON_PYTHON="):
            python_path = line.split("=", 1)[1].strip()
            break
    try:
        parsed = json.loads(stdout.splitlines()[-1]) if stdout else {}
    except json.JSONDecodeError:
        parsed = {}
    if completed.returncode != 0 or not isinstance(parsed, dict) or not parsed:
        return 200, {
            "ok": False,
            "supported": True,
            "server": public_ssh_server(server),
            "sampledAt": datetime.now().isoformat(timespec="seconds"),
            "latencyMs": int((time.time() - started) * 1000),
            "stdout": stdout[:2000],
            "stderr": stderr[:2000],
            "remoteOs": remote_os,
            "pythonPath": python_path,
            "message": stderr or stdout or f"ssh exited with {completed.returncode}",
        }

    host = {
        "id": f"ssh:{server_id}",
        "name": str(server.get("name") or parsed.get("hostname") or server.get("host") or "remote"),
        "os": str(parsed.get("os") or "remote"),
        "address": str(server.get("host") or ""),
        "user": str(parsed.get("user") or server.get("username") or ""),
        "cpuUsage": float(parsed.get("cpuUsage") or 0),
        "memoryUsedGb": float(parsed.get("memoryUsedGb") or 0),
        "memoryTotalGb": float(parsed.get("memoryTotalGb") or 0),
        "gpusTotal": int(parsed.get("gpusTotal") or 0),
        "gpusBusy": int(parsed.get("gpusBusy") or 0),
        "gpus": parsed.get("gpus") if isinstance(parsed.get("gpus"), list) else [],
        "diskRead": 0,
        "diskWrite": 0,
        "netRx": 0,
        "netTx": 0,
        "runningRuns": 0,
        "warnings": [],
        "cores": parsed.get("cores") if isinstance(parsed.get("cores"), list) else [],
    }
    return 200, {
        "ok": True,
        "supported": True,
        "server": public_ssh_server(server),
        "sampledAt": datetime.now().isoformat(timespec="seconds"),
        "latencyMs": int((time.time() - started) * 1000),
        "remoteOs": remote_os,
        "pythonPath": python_path,
        "host": host,
        "message": "remote resource snapshot ok",
    }


def mib(value: float) -> float:
    return round(value / 1024 / 1024, 2)


def gb(value: float) -> float:
    return round(value / 1024 / 1024 / 1024, 2)


def to_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def norm_text_path(value: str | Path | None) -> str:
    if not value:
        return ""
    return str(value).replace("\\", "/").lower()


def path_is_under(path: str | Path | None, root: str | Path | None) -> bool:
    if not path or not root:
        return False
    try:
        return Path(path).resolve().is_relative_to(Path(root).resolve())
    except Exception:
        path_text = norm_text_path(path)
        root_text = norm_text_path(root).rstrip("/")
        return path_text == root_text or path_text.startswith(f"{root_text}/")


def configured_roots() -> list[Path]:
    roots = []
    for item in CONFIG.get("experiment_roots", []):
        try:
            root = config_path(item)
            if root.exists():
                roots.append(root)
        except OSError:
            continue
    return roots


def protocol_scan_roots() -> list[Path]:
    protocol = CONFIG.get("protocol", {})
    roots = protocol.get("scan_roots") or CONFIG.get("experiment_roots", [])
    resolved = []
    for item in roots:
        try:
            root = config_path(item)
            if root.exists():
                resolved.append(root)
        except OSError:
            continue
    return resolved


def canonical_host_id(value: Any = None) -> str:
    configured = str(CONFIG.get("host_id") or "local")
    candidate = str(value or "").strip()
    local_aliases = {
        configured.lower(),
        socket.gethostname().lower(),
        os.environ.get("COMPUTERNAME", "").lower(),
    }
    if not candidate or candidate.lower() in local_aliases:
        return configured
    return candidate


def discovery_config() -> dict[str, Any]:
    return CONFIG.get("run_discovery", {})


def explicit_rule_for(command: str, cwd: str = "") -> dict[str, Any] | None:
    hay = f"{command}\n{cwd}"
    for rule in discovery_config().get("explicit_rules", []) or []:
        pattern = rule.get("command_regex")
        if not pattern:
            continue
        try:
            if re.search(str(pattern), hay, flags=re.IGNORECASE):
                return rule
        except re.error:
            continue
    return None


def safe_process_info(process: psutil.Process) -> dict[str, Any] | None:
    try:
        info = process.as_dict(
            attrs=[
                "pid",
                "ppid",
                "name",
                "cmdline",
                "cwd",
                "username",
                "create_time",
                "status",
                "memory_info",
                "num_threads",
                "cpu_percent",
                "io_counters",
            ]
        )
        info["cmd"] = " ".join(info.get("cmdline") or [])
        return info
    except (psutil.AccessDenied, psutil.NoSuchProcess, psutil.ZombieProcess):
        return None


def safe_resource_process_info(process: psutil.Process) -> dict[str, Any] | None:
    try:
        return process.as_dict(attrs=["pid", "name", "memory_info"])
    except (psutil.AccessDenied, psutil.NoSuchProcess, psutil.ZombieProcess):
        return None


def safe_basic_process_info(process: psutil.Process) -> dict[str, Any] | None:
    try:
        info = process.as_dict(
            attrs=[
                "pid",
                "ppid",
                "name",
                "cmdline",
                "username",
                "create_time",
                "status",
            ]
        )
        info["cmd"] = " ".join(info.get("cmdline") or [])
        return info
    except (psutil.AccessDenied, psutil.NoSuchProcess, psutil.ZombieProcess):
        return None


def safe_min_process_info(process: psutil.Process) -> dict[str, Any] | None:
    try:
        return process.as_dict(attrs=["pid", "ppid", "name", "username", "create_time", "status"])
    except (psutil.AccessDenied, psutil.NoSuchProcess, psutil.ZombieProcess):
        return None


def candidate_process_infos() -> list[dict[str, Any]]:
    if os.name == "nt":
        cim_infos = windows_cim_process_infos()
        if cim_infos:
            return cim_infos

    candidates = []
    for process in psutil.process_iter():
        info = safe_min_process_info(process)
        if not info:
            continue
        name = str(info.get("name") or "").lower()
        if not any(hint in name for hint in RUNNER_NAME_HINTS):
            continue
        try:
            cmdline = process.cmdline()
        except (psutil.AccessDenied, psutil.NoSuchProcess, psutil.ZombieProcess, OSError):
            cmdline = []
        info["cmdline"] = cmdline
        info["cmd"] = " ".join(cmdline)
        candidates.append(info)
    return candidates


def windows_cim_process_infos() -> list[dict[str, Any]]:
    command = (
        "[Console]::OutputEncoding=[System.Text.Encoding]::UTF8; "
        "Get-CimInstance Win32_Process | "
        "Select-Object ProcessId,ParentProcessId,Name,CommandLine,CreationDate | "
        "ConvertTo-Json -Compress"
    )
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", command],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=5,
        )
    except Exception:
        return []
    if result.returncode != 0 or not result.stdout.strip():
        return []
    try:
        parsed = json.loads(result.stdout)
    except json.JSONDecodeError:
        return []
    rows = parsed if isinstance(parsed, list) else [parsed]
    keywords = [str(keyword).lower() for keyword in discovery_config().get("include_command_keywords", []) or []]
    candidates = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        name = str(row.get("Name") or "")
        cmd = str(row.get("CommandLine") or "")
        hay = f"{name} {cmd}".lower()
        if not any(hint in name.lower() for hint in RUNNER_NAME_HINTS) and not any(keyword in hay for keyword in keywords):
            continue
        candidates.append(
            {
                "pid": int(row.get("ProcessId") or 0),
                "ppid": int(row.get("ParentProcessId") or 0),
                "name": name,
                "cmdline": cmd.split(),
                "cmd": cmd,
                "username": "",
                "create_time": 0,
                "status": "running",
            }
        )
    return candidates


def process_cwd(pid: int) -> str:
    try:
        return psutil.Process(pid).cwd()
    except (psutil.AccessDenied, psutil.NoSuchProcess, psutil.ZombieProcess, OSError):
        return ""


def is_shell_process_name(name: str) -> bool:
    lower = name.lower()
    return any(shell in lower for shell in ("powershell", "pwsh", "cmd.exe", "bash", "zsh", "fish"))


def is_observer_shell_command(text: str) -> bool:
    lower = text.lower()
    if "start-sleep" not in lower:
        return False
    observer_tokens = (
        "get-content",
        "get-childitem",
        "import-csv",
        "convertfrom-json",
        "convertto-json",
        "invoke-restmethod",
        "test-path",
        "select-string",
    )
    return any(token in lower for token in observer_tokens)


def is_workspace_process(info: dict[str, Any]) -> bool:
    cmd = str(info.get("cmd") or "")
    name = str(info.get("name") or "")
    cwd = process_cwd(int(info.get("pid") or 0))
    hay = f"{name} {cmd} {cwd}".lower()

    if is_observer_shell_command(hay):
        return False

    for keyword in discovery_config().get("exclude_command_keywords", []) or []:
        if str(keyword).lower() in hay:
            return False

    if "spawn_main" in hay or "--multiprocessing-fork" in hay:
        return False

    if explicit_rule_for(cmd, cwd):
        return True

    for root in configured_roots():
        root_text = norm_text_path(root)
        if root_text and (root_text in norm_text_path(cmd) or path_is_under(cwd, root)):
            return True

    for root in discovery_config().get("include_cwd_under", []) or []:
        if path_is_under(cwd, root):
            return True

    for keyword in discovery_config().get("include_command_keywords", []) or []:
        if str(keyword).lower() in hay:
            return True

    return False


def is_run_root(info: dict[str, Any], workspace_pids: set[int]) -> bool:
    cmd = str(info.get("cmd") or "").lower()
    name = str(info.get("name") or "").lower()
    cwd = process_cwd(int(info.get("pid") or 0))
    if "spawn_main" in cmd or "--multiprocessing-fork" in cmd:
        return False
    if is_observer_shell_command(f"{name} {cmd} {cwd}"):
        return False
    if explicit_rule_for(cmd, cwd):
        return True
    if info.get("ppid") in workspace_pids:
        return False
    keywords = [str(keyword).lower() for keyword in discovery_config().get("include_command_keywords", []) or []]
    if not any(keyword in cmd for keyword in keywords):
        return False
    if is_shell_process_name(name) and not explicit_rule_for(cmd, cwd):
        shell_launch_tokens = (".ps1", "torchrun", "deepspeed", "python", "conda run", "mamba run")
        if not any(token in cmd for token in shell_launch_tokens):
            return False
    runner_names = ("python", "python.exe", "torchrun", "deepspeed", "rscript", "julia", "powershell", "bash")
    return any(item in name for item in runner_names) or any(keyword in name for keyword in keywords)


def process_node(process: psutil.Process, role: str = "root", label: str | None = None) -> dict[str, Any] | None:
    info = safe_resource_process_info(process)
    if not info:
        return None
    memory = info.get("memory_info")
    children = []
    try:
        for child in process.children(recursive=False):
            node = process_node(child, "child")
            if node:
                children.append(node)
    except (psutil.AccessDenied, psutil.NoSuchProcess):
        pass
    cmd = label or info.get("name") or f"pid {info['pid']}"
    return {
        "pid": info["pid"],
        "name": shorten_command(cmd),
        "cpu": process_cpu_percent(process),
        "memoryGb": gb(memory.rss if memory else 0),
        "role": role,
        "children": children,
    }


def empty_process_node(pid: int, label: str) -> dict[str, Any]:
    return {"pid": pid, "name": label, "cpu": 0, "memoryGb": 0, "role": "root", "children": []}


def flatten_tree(node: dict[str, Any]) -> list[dict[str, Any]]:
    rows = [node]
    for child in node.get("children") or []:
        rows.extend(flatten_tree(child))
    return rows


def shorten_command(command: str) -> str:
    shortened = command
    for root in configured_roots():
        shortened = shortened.replace(str(root), str(root.name))
    return shortened if len(shortened) <= 180 else f"{shortened[:177]}..."


def detect_entrypoint(command: str) -> str:
    lower = command.lower()
    if "python" in lower or ".py" in lower:
        return "python"
    if "rscript" in lower:
        return "r"
    if "julia" in lower:
        return "julia"
    if lower.endswith(".ps1") or "powershell" in lower or "cmd.exe" in lower or "bash" in lower:
        return "shell"
    return "other"


def detect_project(command: str, cwd: str) -> str:
    rule = explicit_rule_for(command, cwd)
    if rule and rule.get("project"):
        return str(rule["project"])
    for root in configured_roots():
        if path_is_under(cwd, root):
            return root.name or str(root)
    return Path(cwd).name or "local"


def detect_name(command: str) -> str:
    parts = command.split()
    for part in parts:
        if part.endswith(".py"):
            return Path(part).stem
    return Path(parts[0]).name if parts else "local-process"


def coerce_hparam_value(value: str) -> str | int | float | bool:
    lowered = value.strip().lower()
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


def parse_command_hparams(command: str) -> dict[str, str | int | float | bool]:
    try:
        tokens = shlex.split(command, posix=False)
    except ValueError:
        tokens = command.split()
    hparams: dict[str, str | int | float | bool] = {}
    index = 0
    while index < len(tokens):
        token = tokens[index]
        if not token.startswith("--") or token == "--":
            index += 1
            continue
        key_value = token[2:]
        if "=" in key_value:
            key, value = key_value.split("=", 1)
            hparams[key] = coerce_hparam_value(value.strip("\"'"))
            index += 1
            continue
        key = key_value
        next_token = tokens[index + 1] if index + 1 < len(tokens) else ""
        if next_token and not next_token.startswith("-"):
            hparams[key] = coerce_hparam_value(next_token.strip("\"'"))
            index += 2
        else:
            hparams[key] = True
            index += 1
    return hparams


def discover_hparams_files(cwd: str) -> dict[str, str | int | float | bool]:
    if not cwd:
        return {}
    names = [
        "hparams.yaml",
        "hparams.yml",
        "hyperparameters.yaml",
        "hyperparameters.yml",
        "args.yaml",
        "args.yml",
        "config.yaml",
        "config.yml",
    ]
    current = Path(cwd)
    candidates = []
    for directory in [current, current / "configs", current / "config"]:
        for name in names:
            candidates.append(directory / name)
    for path in candidates:
        data = read_yaml(path)
        if data:
            return flatten_hparams(data)
    return {}


def hparams_for_process(command: str, cwd: str) -> dict[str, str | int | float | bool]:
    hparams = discover_hparams_files(cwd)
    hparams.update(parse_command_hparams(command))
    return hparams


def tree_resource_summary(tree: dict[str, Any]) -> tuple[float, float, int, int, float, float]:
    rows = flatten_tree(tree)
    cpu = round(sum(float(row.get("cpu") or 0) for row in rows), 1)
    memory_total = round(sum(float(row.get("memoryGb") or 0) for row in rows), 2)
    io_read = 0
    io_write = 0
    thread_total = 0
    for row in rows:
        try:
            process = psutil.Process(int(row["pid"]))
            io = process.io_counters()
            io_read += getattr(io, "read_bytes", 0)
            io_write += getattr(io, "write_bytes", 0)
            thread_total += process.num_threads()
        except (psutil.AccessDenied, psutil.NoSuchProcess):
            pass
    return cpu, memory_total, len(rows), thread_total, mib(io_read), mib(io_write)


def process_cpu_percent(process: psutil.Process) -> float:
    try:
        times = process.cpu_times()
        cpu_time = float(times.user + times.system)
        now = time.time()
        pid = int(process.pid)
    except (psutil.AccessDenied, psutil.NoSuchProcess, psutil.ZombieProcess):
        return 0

    previous = PROCESS_CPU_HISTORY.get(pid)
    PROCESS_CPU_HISTORY[pid] = (now, cpu_time)
    if not previous:
        return 0
    previous_wall, previous_cpu = previous
    wall_delta = now - previous_wall
    cpu_delta = cpu_time - previous_cpu
    if wall_delta <= 0 or cpu_delta < 0:
        return 0
    return round((cpu_delta / wall_delta) * 100, 1)


def update_resource_history(run_id: str, sample: dict[str, Any]) -> list[dict[str, Any]]:
    max_points = int(CONFIG.get("protocol", {}).get("max_metric_points", 120))
    history = RUN_RESOURCE_HISTORY.setdefault(run_id, [])
    if not history or history[-1].get("time") != sample.get("time"):
        history.append(sample)
    if len(history) > max_points:
        del history[:-max_points]
    return list(history)


def io_rates(run_id: str, read_mib_total: float, write_mib_total: float) -> tuple[float, float]:
    now = time.time()
    previous = RUN_IO_HISTORY.get(run_id)
    RUN_IO_HISTORY[run_id] = (now, read_mib_total, write_mib_total)
    if not previous:
        return 0, 0
    previous_time, previous_read, previous_write = previous
    seconds = now - previous_time
    if seconds <= 0:
        return 0, 0
    read_rate = max(0, read_mib_total - previous_read) / seconds
    write_rate = max(0, write_mib_total - previous_write) / seconds
    return round(read_rate, 2), round(write_rate, 2)


def host_io_rates(
    read_mib_total: float,
    write_mib_total: float,
    rx_mib_total: float,
    tx_mib_total: float,
) -> tuple[float, float, float, float]:
    global HOST_IO_HISTORY
    now = time.time()
    previous = HOST_IO_HISTORY
    HOST_IO_HISTORY = (now, read_mib_total, write_mib_total, rx_mib_total, tx_mib_total)
    if not previous:
        return 0, 0, 0, 0
    previous_time, previous_read, previous_write, previous_rx, previous_tx = previous
    seconds = now - previous_time
    if seconds <= 0:
        return 0, 0, 0, 0
    return (
        round(max(0, read_mib_total - previous_read) / seconds, 2),
        round(max(0, write_mib_total - previous_write) / seconds, 2),
        round(max(0, rx_mib_total - previous_rx) / seconds, 2),
        round(max(0, tx_mib_total - previous_tx) / seconds, 2),
    )


def update_host_history(host_id: str, sample: dict[str, Any]) -> list[dict[str, Any]]:
    max_points = int(CONFIG.get("protocol", {}).get("max_metric_points", 120))
    history = HOST_RESOURCE_HISTORY.setdefault(host_id, [])
    if not history or history[-1].get("time") != sample.get("time"):
        history.append(sample)
    if len(history) > max_points:
        del history[:-max_points]
    return list(history)


def run_from_process(
    process: psutil.Process,
    access_level: str = "C",
    tags: list[str] | None = None,
    gpus: list[dict[str, Any]] | None = None,
    gpu_pids: set[int] | None = None,
    run_id_override: str | None = None,
) -> dict[str, Any] | None:
    info = safe_process_info(process)
    if not info:
        return None
    command = info.get("cmd") or info.get("name") or ""
    tree = process_node(process, label=shorten_command(command))
    if not tree:
        return None
    cwd = info.get("cwd") or ""
    started = datetime.fromtimestamp(float(info.get("create_time") or time.time()))
    runtime_seconds = max(0, int(time.time() - started.timestamp()))
    cpu, memory_total, process_count, thread_total, read_mib, write_mib = tree_resource_summary(tree)
    rows = flatten_tree(tree)
    run_pids = {int(row.get("pid") or 0) for row in rows}
    uses_gpu = bool(gpu_pids and any(pid in gpu_pids for pid in run_pids))
    active_gpus = [
        gpu for gpu in gpus or []
        if any(int(process.get("pid") or 0) in run_pids for process in gpu.get("processes") or [])
    ] if uses_gpu else []
    gpu_label = ", ".join(f"GPU {gpu['index']}" for gpu in active_gpus) if active_gpus else "-"
    gpu_memory_gb = round(sum(float(gpu.get("memoryUsedMiB") or 0) for gpu in active_gpus) / 1024, 2)
    gpu_util_percent = max((float(gpu.get("utilization") or 0) for gpu in active_gpus), default=0)
    gpu_power_w = round(sum(float(gpu.get("powerDrawW") or 0) for gpu in active_gpus), 1)
    gpu_temperature_c = max((float(gpu.get("temperatureC") or 0) for gpu in active_gpus), default=0)
    run_id = run_id_override or f"local-{info['pid']}-{int(started.timestamp())}"
    read_rate, write_rate = io_rates(run_id, read_mib, write_mib)
    sample_time = datetime.now()
    resource_sample = {
        "time": sample_time.strftime("%H:%M:%S"),
        "ts": sample_time.isoformat(timespec="seconds"),
        "cpu": cpu,
        "memory": memory_total,
        "read": read_rate,
        "write": write_rate,
        "readTotal": read_mib,
        "writeTotal": write_mib,
        "processes": process_count,
        "threads": thread_total,
    }
    if active_gpus:
        resource_sample["gpuMemory"] = gpu_memory_gb
        resource_sample["gpuUtil"] = gpu_util_percent
        resource_sample["gpuPower"] = gpu_power_w
        resource_sample["gpuTemp"] = gpu_temperature_c
    resources = update_resource_history(run_id, resource_sample)
    summary = build_run_summary("running", {}, runtime_seconds, resources, [], [], gpu_label)
    return {
        "id": run_id,
        "project": detect_project(command, cwd),
        "name": detect_name(command),
        "status": "running",
        "resourceType": "gpu" if uses_gpu else infer_resource_type(command, gpus),
        "hostId": canonical_host_id(),
        "user": info.get("username") or "local",
        "rootPid": info["pid"],
        "rootCreateTime": started.strftime("%Y-%m-%d %H:%M:%S"),
        "command": shorten_command(command),
        "cwd": cwd,
        "runtime": format_runtime(runtime_seconds),
        "rootCpuPercent": float(tree.get("cpu") or 0),
        "processTreeCpuPercent": cpu,
        "cpuPercent": cpu,
        "memoryGb": memory_total,
        "gpuLabel": gpu_label,
        "gpuMemoryGb": gpu_memory_gb,
        "gpuUtilPercent": gpu_util_percent,
        "gpuPowerW": gpu_power_w,
        "gpuTemperatureC": gpu_temperature_c,
        "diskIo": round(read_rate + write_rate, 2),
        "latestMetric": "not connected",
        "bestMetric": "-",
        "entrypointKind": detect_entrypoint(command),
        "tags": tags or ["local", "unmanaged"],
        "accessLevel": access_level,
        "processTree": tree,
        "hparams": hparams_for_process(command, cwd),
        "logs": [
            "local collector discovered this process",
            "no manifest.yaml linked yet",
            "use scripts/expmon.py launch for metrics, hparams and log capture",
        ],
        "metrics": [],
        "resources": resources,
        "events": [],
        "summary": summary,
        "metadata": run_metadata_for(run_id),
        "gpuProcesses": [
            dict(process)
            for gpu in active_gpus
            for process in gpu.get("processes") or []
            if int(process.get("pid") or 0) in run_pids
        ],
    }


def infer_resource_type(command: str, gpus: list[dict[str, Any]] | None = None) -> str:
    lower = command.lower()
    gpu_hint = any(token in lower for token in ("cuda", "gpu", "torchrun", "deepspeed", "--device"))
    if gpus and any(gpu.get("busy") for gpu in gpus):
        return "gpu"
    return "gpu" if gpu_hint else "unknown"


def format_runtime(seconds: int) -> str:
    hours, rem = divmod(seconds, 3600)
    minutes, _ = divmod(rem, 60)
    if hours:
        return f"{hours}h{minutes:02d}m"
    return f"{minutes}m"


def format_clock() -> str:
    return datetime.now().strftime("%H:%M:%S")


def gpu_samples() -> list[dict[str, Any]]:
    try:
        result = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=index,uuid,name,memory.total,memory.used,utilization.gpu,power.draw,power.limit,temperature.gpu",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=2,
        )
        if result.returncode != 0:
            return []
        gpus = []
        for line in result.stdout.splitlines():
            if not line.strip():
                continue
            parts = [part.strip() for part in line.split(",")]
            if len(parts) < 9:
                continue
            used = to_float(parts[4])
            total = to_float(parts[3])
            util = to_float(parts[5])
            gpus.append(
                {
                    "index": int(to_float(parts[0])),
                    "uuid": parts[1],
                    "name": parts[2],
                    "memoryTotalMiB": total,
                    "memoryUsedMiB": used,
                    "memoryPercent": round((used / total) * 100, 1) if total else 0,
                    "utilization": util,
                    "powerDrawW": to_float(parts[6]),
                    "powerLimitW": to_float(parts[7]),
                    "temperatureC": to_float(parts[8]),
                    "busy": util > 0 or used > 0,
                    "processes": [],
                }
            )
        attach_gpu_processes(gpus)
        return gpus
    except Exception:
        return []


def gpu_process_samples() -> list[dict[str, Any]]:
    def classify_process(pid: int, name: str) -> tuple[str, str]:
        try:
            proc = psutil.Process(pid)
            command = " ".join(proc.cmdline())
        except (psutil.Error, OSError):
            command = ""
        lower = f"{name} {command}".lower()
        if any(token in lower for token in ["jupyter", "notebook", "jupyter-lab", "jupyter lab", "ipykernel", "kernel-"]):
            return "notebook", command
        return "unattributed", command

    try:
        result = subprocess.run(
            [
                "nvidia-smi",
                "--query-compute-apps=pid,process_name,used_memory,gpu_uuid",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=2,
        )
        if result.returncode != 0:
            return []
        processes = []
        for line in result.stdout.splitlines():
            parts = [part.strip() for part in line.split(",")]
            if len(parts) < 4:
                continue
            try:
                pid = int(parts[0])
            except ValueError:
                continue
            used_memory = to_float(parts[2])
            if used_memory <= 0:
                continue
            role, command = classify_process(pid, parts[1])
            processes.append(
                {
                    "pid": pid,
                    "name": parts[1],
                    "command": command,
                    "usedMemoryMiB": used_memory,
                    "gpuUuid": parts[3],
                    "gpuIndex": -1,
                    "runId": "",
                    "project": "",
                    "runName": "",
                    "role": role,
                }
            )
        return processes
    except Exception:
        return []


def attach_gpu_processes(gpus: list[dict[str, Any]]) -> None:
    by_uuid = {str(gpu.get("uuid") or ""): gpu for gpu in gpus}
    for process in gpu_process_samples():
        gpu = by_uuid.get(str(process.get("gpuUuid") or ""))
        if not gpu:
            continue
        process["gpuIndex"] = gpu.get("index", -1)
        gpu.setdefault("processes", []).append(process)


def gpu_process_pids(gpus: list[dict[str, Any]] | None = None) -> set[int]:
    if gpus is not None:
        return {int(process.get("pid") or 0) for gpu in gpus for process in gpu.get("processes") or [] if int(process.get("pid") or 0) > 0}
    try:
        return {int(process.get("pid") or 0) for process in gpu_process_samples() if int(process.get("pid") or 0) > 0}
    except Exception:
        return set()


def attribute_gpu_processes_to_runs(runs: list[dict[str, Any]], gpus: list[dict[str, Any]]) -> None:
    run_by_pid: dict[int, dict[str, Any]] = {}
    for run in runs:
        tree = run.get("processTree") if isinstance(run.get("processTree"), dict) else {}
        for row in flatten_tree(tree):
            pid = int(row.get("pid") or 0)
            if pid > 0:
                run_by_pid[pid] = run
        run["gpuProcesses"] = []

    for gpu in gpus:
        for process in gpu.get("processes") or []:
            pid = int(process.get("pid") or 0)
            run = run_by_pid.get(pid)
            if not run:
                continue
            process["runId"] = str(run.get("id") or "")
            process["project"] = str(run.get("project") or "")
            process["runName"] = str(run.get("name") or "")
            process["role"] = "run"
            run.setdefault("gpuProcesses", []).append(dict(process))


def read_yaml(path: Path) -> dict[str, Any]:
    if not path.exists() or yaml is None:
        return {}
    try:
        value = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        return value if isinstance(value, dict) else {}
    except Exception:
        return {}


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except Exception:
        return {}


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def write_yaml(path: Path, payload: dict[str, Any]) -> None:
    if yaml is None:
        write_json(path, payload)
        return
    path.write_text(yaml.safe_dump(payload, allow_unicode=True, sort_keys=False), encoding="utf-8")


def append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False) + "\n")


def tail_lines(path: Path, limit: int = 80) -> list[str]:
    if not path.exists():
        return []
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        return lines[-limit:]
    except OSError:
        return []


def metric_record_from_json(row: dict[str, Any]) -> dict[str, Any]:
    record: dict[str, Any] = {"time": str(row.get("time") or row.get("ts") or row.get("step") or format_clock())}
    if isinstance(row.get("metrics"), dict):
        for key, value in row["metrics"].items():
            if isinstance(value, (int, float)):
                record[str(key)] = value
    for key, value in row.items():
        if key in {"time", "ts", "step", "metrics"}:
            continue
        if isinstance(value, (int, float)):
            record[str(key)] = value
    return record


def read_metrics(run_dir: Path) -> list[dict[str, Any]]:
    metrics_path = run_dir / "metrics.jsonl"
    if not metrics_path.exists():
        return []
    max_points = int(CONFIG.get("protocol", {}).get("max_metric_points", 120))
    records: list[dict[str, Any]] = []
    for line in tail_lines(metrics_path, max_points):
        try:
            parsed = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            records.append(metric_record_from_json(parsed))
    return records


def resource_record_from_json(row: dict[str, Any]) -> dict[str, Any]:
    record: dict[str, Any] = {"time": str(row.get("time") or row.get("ts") or format_clock())}
    for key, value in row.items():
        if key in {"time", "ts"}:
            continue
        if isinstance(value, (int, float)):
            record[str(key)] = value
    return record


def read_resources(run_dir: Path) -> list[dict[str, Any]]:
    resources_path = run_dir / "resources.jsonl"
    if not resources_path.exists():
        return []
    max_points = int(CONFIG.get("protocol", {}).get("max_metric_points", 120))
    records: list[dict[str, Any]] = []
    for line in tail_lines(resources_path, max_points):
        try:
            parsed = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            records.append(resource_record_from_json(parsed))
    return records


LOG_EVENT_PATTERNS: list[tuple[str, str, str, re.Pattern[str]]] = [
    ("cuda_oom", "error", "CUDA out of memory", re.compile(r"CUDA out of memory|CUDNN_STATUS_ALLOC_FAILED", re.I)),
    ("killed", "error", "Process was killed", re.compile(r"(^|\s)Killed($|\s)|exit code 137", re.I)),
    ("segfault", "error", "Segmentation fault", re.compile(r"segmentation fault|exit code 139", re.I)),
    ("nccl", "warning", "NCCL warning or timeout", re.compile(r"NCCL (WARN|ERROR)|NCCL.*timeout", re.I)),
    ("disk_full", "error", "No space left on device", re.compile(r"No space left on device", re.I)),
    ("bus_error", "error", "Bus error", re.compile(r"Bus error", re.I)),
    ("dataloader", "error", "DataLoader worker exited unexpectedly", re.compile(r"DataLoader worker.*exited unexpectedly|worker.*killed", re.I)),
    ("nan_inf", "warning", "NaN or Inf detected", re.compile(r"(^|[^a-z])(nan|inf)([^a-z]|$)", re.I)),
]


def parse_event_marker(line: str, source: str) -> dict[str, Any] | None:
    if "EXPMON_EVENT" not in line:
        return None
    payload = line.split("EXPMON_EVENT", 1)[1].strip()
    if not payload:
        return None
    parsed: dict[str, Any] = {}
    if payload.startswith("{"):
        try:
            value = json.loads(payload)
            if isinstance(value, dict):
                parsed = value
        except json.JSONDecodeError:
            return None
    else:
        for item in payload.split():
            if "=" not in item:
                continue
            key, raw = item.split("=", 1)
            parsed[key] = raw.strip("\"'")
    event_type = str(parsed.get("type") or parsed.get("event") or "event")
    return {
        "time": str(parsed.get("time") or parsed.get("ts") or format_clock()),
        "type": event_type,
        "severity": str(parsed.get("severity") or "info"),
        "message": str(parsed.get("message") or event_type),
        "source": source,
        "line": line.strip(),
    }


def event_from_log_line(line: str, source: str) -> dict[str, Any] | None:
    marker = parse_event_marker(line, source)
    if marker:
        return marker
    for event_type, severity, message, pattern in LOG_EVENT_PATTERNS:
        if pattern.search(line):
            return {
                "time": format_clock(),
                "type": event_type,
                "severity": severity,
                "message": message,
                "source": source,
                "line": line.strip(),
            }
    return None


def event_record_from_json(row: dict[str, Any]) -> dict[str, Any]:
    event_type = str(row.get("type") or row.get("event") or "event")
    return {
        "time": str(row.get("time") or row.get("ts") or format_clock()),
        "type": event_type,
        "severity": str(row.get("severity") or "info"),
        "message": str(row.get("message") or event_type),
        "source": str(row.get("source") or "events.jsonl"),
        "line": str(row.get("line") or row.get("message") or event_type),
    }


def read_events(run_dir: Path) -> list[dict[str, Any]]:
    max_points = int(CONFIG.get("protocol", {}).get("max_metric_points", 120))
    events: list[dict[str, Any]] = []
    events_path = run_dir / "events.jsonl"
    for line in tail_lines(events_path, max_points):
        try:
            parsed = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            events.append(event_record_from_json(parsed))

    seen = {(event["type"], event["source"], event["line"]) for event in events}
    for source, path in (("stdout", run_dir / "stdout.log"), ("stderr", run_dir / "stderr.log")):
        for line in tail_lines(path, max_points):
            event = event_from_log_line(line, source)
            if not event:
                continue
            key = (event["type"], event["source"], event["line"])
            if key in seen:
                continue
            seen.add(key)
            events.append(event)
    return events[-max_points:]


def append_resource_sample(run_dir: Path, sample: dict[str, Any]) -> None:
    resources_path = run_dir / "resources.jsonl"
    if "ts" not in sample:
        sample = {**sample, "ts": datetime.now().isoformat(timespec="seconds")}
    last_lines = tail_lines(resources_path, 1)
    if last_lines:
        try:
            previous = json.loads(last_lines[-1])
            if isinstance(previous, dict) and previous.get("ts") == sample.get("ts"):
                return
        except json.JSONDecodeError:
            pass
    append_jsonl(resources_path, sample)


def flatten_hparams(value: Any, prefix: str = "") -> dict[str, str | int | float]:
    flattened: dict[str, str | int | float] = {}
    if isinstance(value, dict):
        for key, item in value.items():
            next_prefix = f"{prefix}.{key}" if prefix else str(key)
            flattened.update(flatten_hparams(item, next_prefix))
    elif isinstance(value, (str, int, float, bool)):
        flattened[prefix] = value
    return flattened


def process_is_alive(pid: int, create_time: float | None = None) -> bool:
    if pid <= 0:
        return False
    try:
        process = psutil.Process(pid)
        if create_time:
            return abs(float(process.create_time()) - float(create_time)) < 2
        return process.is_running()
    except (psutil.AccessDenied, psutil.NoSuchProcess, psutil.ZombieProcess):
        return False


def parse_create_timestamp(value: Any) -> float | None:
    if not value or value == "-":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        pass
    for candidate in [str(value), str(value).replace(" ", "T")]:
        try:
            return datetime.fromisoformat(candidate).timestamp()
        except ValueError:
            continue
    return None


def format_create_time(value: Any, fallback: str = "-") -> str:
    timestamp = parse_create_timestamp(value)
    if timestamp is not None:
        return datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M:%S")
    if fallback and fallback != "-":
        timestamp = parse_create_timestamp(fallback)
        if timestamp is not None:
            return datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M:%S")
        return fallback.replace("T", " ")
    return "-"


def root_create_time_matches(process: psutil.Process, value: Any) -> bool:
    expected = parse_create_timestamp(value)
    if expected is None:
        return True
    try:
        return abs(float(process.create_time()) - expected) < 2
    except (psutil.AccessDenied, psutil.NoSuchProcess, psutil.ZombieProcess):
        return False


def find_manifest_dir_for_run(run_id: str) -> Path | None:
    for run_dir in find_manifest_dirs():
        manifest = read_yaml(run_dir / "manifest.yaml")
        run_doc = manifest.get("run", {}) if isinstance(manifest.get("run"), dict) else {}
        if str(run_doc.get("run_id") or run_dir.name) == run_id:
            return run_dir
    return None


def mark_manifest_killed(run_id: str, pid: int) -> None:
    run_dir = find_manifest_dir_for_run(run_id)
    if not run_dir:
        return
    status_path = run_dir / "status.json"
    status_doc = read_json(status_path)
    status_doc.update(
        {
            "status": "killed",
            "killed_at": datetime.now().isoformat(timespec="seconds"),
            "ended_at": datetime.now().isoformat(timespec="seconds"),
            "pid": pid,
        }
    )
    write_json(status_path, status_doc)

    manifest_path = run_dir / "manifest.yaml"
    manifest = read_yaml(manifest_path)
    if manifest:
        run_doc = manifest.setdefault("run", {})
        time_doc = manifest.setdefault("time", {})
        if isinstance(run_doc, dict):
            run_doc["status"] = "killed"
        if isinstance(time_doc, dict):
            time_doc["ended_at"] = datetime.now().isoformat(timespec="seconds")
        write_yaml(manifest_path, manifest)


def kill_process_tree(pid: int) -> dict[str, Any]:
    process = psutil.Process(pid)
    children = process.children(recursive=True)
    targets = children + [process]
    terminated: list[int] = []
    killed: list[int] = []
    errors: list[str] = []

    for target in targets:
        try:
            target.terminate()
            terminated.append(int(target.pid))
        except (psutil.AccessDenied, psutil.NoSuchProcess) as exc:
            errors.append(f"{target.pid}: {exc}")

    gone, alive = psutil.wait_procs(targets, timeout=5)
    for target in alive:
        try:
            target.kill()
            killed.append(int(target.pid))
        except (psutil.AccessDenied, psutil.NoSuchProcess) as exc:
            errors.append(f"{target.pid}: {exc}")

    if alive:
        psutil.wait_procs(alive, timeout=3)

    return {
        "terminated": sorted(set(terminated + [int(item.pid) for item in gone])),
        "killed": sorted(set(killed)),
        "errors": errors,
    }


def kill_run(run_id: str) -> tuple[int, dict[str, Any]]:
    global LATEST_SNAPSHOT
    current = snapshot()
    runs = current.get("runs") or []
    run = next((item for item in runs if str(item.get("id")) == run_id), None)
    if not run:
        fresh = collect_snapshot()
        run = next((item for item in fresh.get("runs") or [] if str(item.get("id")) == run_id), None)
    if not run:
        return 404, {"ok": False, "error": "run not found"}
    if run.get("status") != "running":
        return 409, {"ok": False, "error": f"run is {run.get('status')}"}

    pid = int(run.get("rootPid") or 0)
    if pid <= 0:
        return 400, {"ok": False, "error": "run has no root pid"}

    try:
        process = psutil.Process(pid)
    except (psutil.NoSuchProcess, psutil.ZombieProcess):
        return 410, {"ok": False, "error": "process already exited"}
    except psutil.AccessDenied:
        return 403, {"ok": False, "error": "access denied"}

    if not root_create_time_matches(process, run.get("rootCreateTime")):
        return 409, {"ok": False, "error": "root pid was reused; refusing to kill"}

    result = kill_process_tree(pid)
    mark_manifest_killed(run_id, pid)
    with SNAPSHOT_LOCK:
        LATEST_SNAPSHOT = None
    return 200, {"ok": True, "runId": run_id, "pid": pid, **result}


def delete_run_record(run_id: str) -> tuple[int, dict[str, Any]]:
    global LATEST_SNAPSHOT, MANIFEST_CACHE
    fresh = collect_snapshot()
    run = next((item for item in fresh.get("runs") or [] if str(item.get("id")) == run_id), None)
    if not run:
        return 404, {"ok": False, "error": "run not found"}

    status = str(run.get("status") or "")
    if status not in DELETABLE_RUN_STATUSES:
        return 409, {"ok": False, "error": f"run is {status}; only finished, failed or killed records can be deleted"}

    run_dir = find_manifest_dir_for_run(run_id)
    if not run_dir:
        return 404, {"ok": False, "error": "managed run directory not found"}
    if not (run_dir / "manifest.yaml").exists():
        return 409, {"ok": False, "error": "refusing to delete a directory without manifest.yaml"}
    if not any(path_is_under(run_dir, root) for root in protocol_scan_roots()):
        return 409, {"ok": False, "error": "run directory is outside configured scan roots"}

    pid = int(run.get("rootPid") or 0)
    if pid > 0:
        try:
            process = psutil.Process(pid)
            if root_create_time_matches(process, run.get("rootCreateTime")):
                return 409, {"ok": False, "error": "root process is still alive; kill or wait before deleting"}
        except (psutil.NoSuchProcess, psutil.ZombieProcess):
            pass
        except psutil.AccessDenied:
            return 403, {"ok": False, "error": "access denied while checking root process"}

    deleted_path = str(run_dir)
    try:
        shutil.rmtree(run_dir)
    except OSError as exc:
        return 500, {"ok": False, "error": str(exc)}

    with SNAPSHOT_LOCK:
        LATEST_SNAPSHOT = None
    MANIFEST_CACHE = (0, [])
    RUN_RESOURCE_HISTORY.pop(run_id, None)
    RUN_IO_HISTORY.pop(run_id, None)
    all_metadata = read_run_metadata_raw()
    if run_id in all_metadata:
        all_metadata.pop(run_id, None)
        write_json_file(RUN_METADATA_PATH, all_metadata)
    return 200, {"ok": True, "runId": run_id, "deletedPath": deleted_path}


def run_git(cwd: Path, args: list[str], timeout: int = 30) -> tuple[int, str, str]:
    try:
        completed = subprocess.run(
            ["git", *args],
            cwd=str(cwd),
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            timeout=timeout,
        )
        return completed.returncode, completed.stdout.strip(), completed.stderr.strip()
    except (OSError, subprocess.TimeoutExpired) as exc:
        return 1, "", str(exc)


def git_root_for_path(path_value: Any) -> Path | None:
    if not path_value:
        return None
    try:
        path = Path(str(path_value)).expanduser()
        if path.is_file():
            path = path.parent
        if not path.exists():
            return None
        code, stdout, _stderr = run_git(path, ["rev-parse", "--show-toplevel"], timeout=5)
        if code == 0 and stdout:
            return Path(stdout).resolve()
    except OSError:
        return None
    return None


def project_id_for_path(path: Path) -> str:
    return hashlib.sha1(str(path.resolve()).encode("utf-8", errors="ignore")).hexdigest()[:16]


def project_path_for_cwd(cwd: str) -> Path | None:
    if not cwd:
        return None
    try:
        cwd_path = Path(cwd).resolve()
    except OSError:
        return None

    for root in configured_roots():
        try:
            root_path = root.resolve()
            if not path_is_under(cwd_path, root_path):
                continue
            return root_path
        except (OSError, ValueError):
            continue
    return cwd_path


def project_path_for_run(run: dict[str, Any]) -> Path | None:
    cwd = str(run.get("cwd") or "")
    if not cwd:
        return None
    project_name = str(run.get("project") or "").strip()
    try:
        cwd_path = Path(cwd).resolve()
    except OSError:
        return None

    if project_name and project_name not in {".", ".."} and not Path(project_name).is_absolute():
        for root in configured_roots():
            try:
                root_path = root.resolve()
                if not path_is_under(cwd_path, root_path):
                    continue
                if root_path.name == project_name:
                    return root_path
                candidate = (root_path / project_name).resolve()
                if candidate.exists() and path_is_under(cwd_path, candidate):
                    return candidate
            except (OSError, ValueError):
                continue

    return project_path_for_cwd(cwd)


def projects_from_runs(runs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    projects: dict[str, dict[str, Any]] = {}
    for run in runs:
        project_path = project_path_for_run(run)
        if not project_path:
            continue
        root = git_root_for_path(project_path)
        project_id = project_id_for_path(project_path)
        item = projects.setdefault(
            project_id,
            {
                "id": project_id,
                "name": project_path.name or str(project_path),
                "path": str(project_path),
                "isGit": root is not None and root.resolve() == project_path.resolve(),
                "runs": [],
                "runningRuns": 0,
                "finishedRuns": 0,
                "failedRuns": 0,
                "totalGpuHours": 0,
                "avgGpuUtil": 0,
                "lastActivity": "",
                "_gpuUtilValues": [],
            },
        )
        item["runs"].append(str(run.get("id") or ""))
        if run.get("status") == "running":
            item["runningRuns"] += 1
        else:
            item["finishedRuns"] += 1
        if run.get("status") in {"failed", "killed"}:
            item["failedRuns"] += 1
        summary = run.get("summary") if isinstance(run.get("summary"), dict) else {}
        item["totalGpuHours"] = round(float(item.get("totalGpuHours") or 0) + float(summary.get("gpuHours") or 0), 3)
        if isinstance(summary.get("avgGpuUtil"), (int, float)) and float(summary.get("avgGpuUtil") or 0) > 0:
            item.setdefault("_gpuUtilValues", []).append(float(summary.get("avgGpuUtil") or 0))
        root_time = str(run.get("rootCreateTime") or "")
        if root_time > str(item.get("lastActivity") or ""):
            item["lastActivity"] = root_time

    for item in projects.values():
        values = item.pop("_gpuUtilValues", [])
        item["avgGpuUtil"] = round(sum(values) / len(values), 2) if values else 0
    return sorted(projects.values(), key=lambda item: (item.get("runningRuns", 0), item.get("lastActivity", "")), reverse=True)


def project_by_id(project_id: str) -> dict[str, Any] | None:
    fresh = collect_snapshot()
    for project in fresh.get("projects") or []:
        if str(project.get("id")) == project_id:
            return project
    return None


def changed_files_from_status(status_text: str) -> list[dict[str, str]]:
    files: list[dict[str, str]] = []
    for line in status_text.splitlines():
        if not line:
            continue
        parts = line.split(maxsplit=1)
        status = parts[0] if parts else "?"
        path = parts[1] if len(parts) > 1 else ""
        if " -> " in path:
            path = path.split(" -> ", 1)[1]
        files.append({"status": status, "path": path})
    return files


def safe_git_relative_path(path_value: str) -> bool:
    path = str(path_value or "").strip()
    if not path or "\x00" in path:
        return False
    if path.startswith(("/", "\\")) or re.match(r"^[A-Za-z]:[\\/]", path):
        return False
    normalized = path.replace("\\", "/")
    parts = normalized.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        return False
    return True


def git_payload(project_id: str) -> tuple[int, dict[str, Any]]:
    project = project_by_id(project_id)
    if not project:
        return 404, {"ok": False, "error": "project not found"}
    if not project.get("isGit"):
        return 409, {"ok": False, "error": "project directory is not a git repository", "project": project}

    cwd = Path(str(project["path"]))
    status_code, status_text, status_err = run_git(cwd, ["status", "--short"])
    log_code, log_text, log_err = run_git(cwd, ["log", "--oneline", "--decorate", "--graph", "-n", "30"])
    branch_code, branch_text, _branch_err = run_git(cwd, ["branch", "--show-current"])
    remote_code, remote_text, _remote_err = run_git(cwd, ["remote", "-v"])
    diff_code, diff_text, diff_err = run_git(cwd, ["diff", "--stat"])
    patch_code, patch_text, patch_err = run_git(cwd, ["diff", "--", "."], timeout=20)
    staged_code, staged_text, staged_err = run_git(cwd, ["diff", "--cached", "--stat"])

    return 200, {
        "ok": True,
        "project": project,
        "branch": branch_text if branch_code == 0 else "",
        "remotes": remote_text.splitlines() if remote_code == 0 and remote_text else [],
        "status": status_text.splitlines() if status_code == 0 else [],
        "changedFiles": changed_files_from_status(status_text if status_code == 0 else ""),
        "log": log_text.splitlines() if log_code == 0 else [],
        "diffStat": diff_text if diff_code == 0 else "",
        "stagedDiffStat": staged_text if staged_code == 0 else "",
        "diff": (patch_text if patch_code == 0 else "")[:60000],
        "errors": [item for item in [status_err, log_err, diff_err, patch_err, staged_err] if item],
    }


def generate_commit_message(project_id: str) -> tuple[int, dict[str, Any]]:
    status, payload = git_payload(project_id)
    if status != 200:
        return status, payload
    files = payload.get("changedFiles") or []
    paths = [str(item.get("path") or "") for item in files]
    lowered = " ".join(paths).lower()
    prefix = "chore"
    if any(path.startswith("src/") for path in paths):
        prefix = "feat"
    if "fix" in lowered or "bug" in lowered:
        prefix = "fix"
    if any(path.endswith((".md", ".rst", ".txt")) for path in paths):
        prefix = "docs" if prefix == "chore" else prefix
    if any("test" in path.lower() or path.lower().endswith("_test.py") for path in paths):
        prefix = "test" if prefix == "chore" else prefix

    noun = "project workspace"
    if any("app.tsx" in path.lower() for path in paths):
        noun = "project management UI"
    elif any("local_collector" in path.lower() for path in paths):
        noun = "collector git project support"
    elif paths:
        top_dirs = sorted({path.split("/", 1)[0] for path in paths if path})
        noun = ", ".join(top_dirs[:2])

    message = f"{prefix}: update {noun}"
    body = "\n".join(f"- {item.get('status', '?')} {item.get('path', '')}" for item in files[:12])
    return 200, {"ok": True, "message": message, "body": body, "files": files}


def git_action(project_id: str, action: str) -> tuple[int, dict[str, Any]]:
    project = project_by_id(project_id)
    if not project:
        return 404, {"ok": False, "error": "project not found"}
    if not project.get("isGit"):
        return 409, {"ok": False, "error": "project directory is not a git repository"}
    cwd = Path(str(project["path"]))
    if action == "pull":
        code, stdout, stderr = run_git(cwd, ["pull", "--ff-only"], timeout=120)
    elif action == "push":
        code, stdout, stderr = run_git(cwd, ["push"], timeout=120)
    else:
        return 400, {"ok": False, "error": "unknown git action"}
    return (200 if code == 0 else 409), {"ok": code == 0, "action": action, "project": project, "stdout": stdout, "stderr": stderr}


def commit_project(project_id: str, payload: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    project = project_by_id(project_id)
    if not project:
        return 404, {"ok": False, "error": "project not found"}
    if not project.get("isGit"):
        return 409, {"ok": False, "error": "project directory is not a git repository"}

    message = str(payload.get("message") or "").strip()
    body = str(payload.get("body") or "").strip()
    selected_paths = string_list(payload.get("paths"))
    if not message:
        return 400, {"ok": False, "error": "commit message is required"}
    if not selected_paths:
        return 400, {"ok": False, "error": "select at least one changed file"}
    unsafe_paths = [path for path in selected_paths if not safe_git_relative_path(path)]
    if unsafe_paths:
        return 400, {"ok": False, "error": "selected file path is not a safe relative git path", "invalid": unsafe_paths}

    status, git_info = git_payload(project_id)
    if status != 200:
        return status, git_info
    allowed_paths = {str(item.get("path") or "") for item in git_info.get("changedFiles") or []}
    unsafe_allowed_paths = [path for path in allowed_paths if path and not safe_git_relative_path(path)]
    if unsafe_allowed_paths:
        return 409, {"ok": False, "error": "git status returned unsafe paths", "invalid": unsafe_allowed_paths}
    invalid = [path for path in selected_paths if path not in allowed_paths]
    if invalid:
        return 400, {"ok": False, "error": "selected file is not in git status", "invalid": invalid}

    cwd = Path(str(project["path"]))
    add_code, add_stdout, add_stderr = run_git(cwd, ["add", "--", *selected_paths], timeout=60)
    if add_code != 0:
        return 409, {"ok": False, "error": add_stderr or add_stdout or "git add failed", "stdout": add_stdout, "stderr": add_stderr}

    commit_args = ["commit", "-m", message]
    if body:
        commit_args.extend(["-m", body])
    commit_code, commit_stdout, commit_stderr = run_git(cwd, commit_args, timeout=120)
    if commit_code != 0:
        return 409, {
            "ok": False,
            "error": commit_stderr or commit_stdout or "git commit failed",
            "stdout": commit_stdout,
            "stderr": commit_stderr,
        }

    status_after, payload_after = git_payload(project_id)
    return 200, {
        "ok": True,
        "action": "commit",
        "project": project,
        "stdout": commit_stdout,
        "stderr": commit_stderr,
        "git": payload_after if status_after == 200 else None,
    }


def find_manifest_dirs() -> list[Path]:
    global MANIFEST_CACHE
    now = time.time()
    cached_at, cached_dirs = MANIFEST_CACHE
    cache_seconds = int(CONFIG.get("protocol", {}).get("manifest_cache_seconds", 3))
    if now - cached_at < cache_seconds:
        return cached_dirs

    max_depth = int(CONFIG.get("protocol", {}).get("max_scan_depth", 5))
    skip_names = {".git", ".codegraph", "node_modules", "__pycache__", ".venv", "venv"}
    found: list[Path] = []
    for root in protocol_scan_roots():
        stack: list[tuple[Path, int]] = [(root, 0)]
        while stack:
            current, depth = stack.pop()
            if (current / "manifest.yaml").exists():
                found.append(current)
                continue
            if depth >= max_depth:
                continue
            try:
                children = list(current.iterdir())
            except OSError:
                continue
            for child in children:
                if child.is_dir() and child.name not in skip_names:
                    stack.append((child, depth + 1))
    MANIFEST_CACHE = (now, found)
    return found


def summarize_metric(metrics: list[dict[str, Any]]) -> tuple[str, str]:
    if not metrics:
        return "-", "-"
    latest = metrics[-1]
    numeric_items = [(key, value) for key, value in latest.items() if key != "time" and isinstance(value, (int, float))]
    if not numeric_items:
        return "-", "-"
    key, value = numeric_items[0]
    series_values = [float(row[key]) for row in metrics if isinstance(row.get(key), (int, float))]
    best = min(series_values) if any(token in key.lower() for token in ("loss", "error", "mae", "mse")) else max(series_values)
    return f"{key}={value:.4g}", f"{key}={best:.4g}"


def avg_numeric(rows: list[dict[str, Any]], key: str) -> float:
    values = [float(row[key]) for row in rows if isinstance(row.get(key), (int, float))]
    return round(sum(values) / len(values), 2) if values else 0


def max_numeric(rows: list[dict[str, Any]], key: str) -> float:
    values = [float(row[key]) for row in rows if isinstance(row.get(key), (int, float))]
    return round(max(values), 2) if values else 0


def final_metric(metrics: list[dict[str, Any]]) -> str:
    if not metrics:
        return "-"
    numeric_items = [(key, value) for key, value in metrics[-1].items() if key != "time" and isinstance(value, (int, float))]
    if not numeric_items:
        return "-"
    key, value = numeric_items[0]
    return f"{key}={value:.4g}"


def fail_reason(status_doc: dict[str, Any], events: list[dict[str, Any]], status: str) -> str:
    error_event = next((event for event in reversed(events) if event.get("severity") == "error"), None)
    if error_event:
        return str(error_event.get("message") or error_event.get("type") or "error")
    exit_code = status_doc.get("exit_code")
    if exit_code not in (None, 0, "0"):
        return f"exit code {exit_code}"
    if status in {"failed", "killed"}:
        return status
    return "-"


def build_run_summary(
    status: str,
    status_doc: dict[str, Any],
    runtime_seconds: int,
    resources: list[dict[str, Any]],
    metrics: list[dict[str, Any]],
    events: list[dict[str, Any]],
    gpu_label: str,
) -> dict[str, Any]:
    gpu_count = len(re.findall(r"GPU \d+", gpu_label))
    gpu_hours = round((runtime_seconds / 3600) * gpu_count, 3) if gpu_count else 0
    return {
        "durationSeconds": runtime_seconds,
        "duration": format_runtime(runtime_seconds),
        "gpuHours": gpu_hours,
        "avgGpuUtil": avg_numeric(resources, "gpuUtil"),
        "maxGpuUtil": max_numeric(resources, "gpuUtil"),
        "maxGpuMemoryGb": max_numeric(resources, "gpuMemory"),
        "avgCpu": avg_numeric(resources, "cpu"),
        "maxMemoryGb": max_numeric(resources, "memory"),
        "totalReadMiB": max_numeric(resources, "readTotal"),
        "totalWriteMiB": max_numeric(resources, "writeTotal"),
        "bestMetric": summarize_metric(metrics)[1],
        "finalMetric": final_metric(metrics),
        "failReason": fail_reason(status_doc, events, status),
        "eventCount": len(events),
        "errorCount": len([event for event in events if event.get("severity") == "error"]),
    }


def latest_resource(run: dict[str, Any]) -> dict[str, Any]:
    resources = run.get("resources") if isinstance(run.get("resources"), list) else []
    return resources[-1] if resources and isinstance(resources[-1], dict) else {}


def build_diagnostics(runs: list[dict[str, Any]], gpus: list[dict[str, Any]]) -> list[dict[str, Any]]:
    diagnostics: list[dict[str, Any]] = []
    for run in runs:
        run_id = str(run.get("id") or "")
        project = str(run.get("project") or "")
        name = str(run.get("name") or "")
        events = run.get("events") if isinstance(run.get("events"), list) else []
        error_event = next((event for event in reversed(events) if event.get("severity") == "error"), None)
        if error_event:
            diagnostics.append(
                {
                    "id": f"{run_id}:event:{error_event.get('type')}",
                    "severity": "error",
                    "type": str(error_event.get("type") or "error"),
                    "title": str(error_event.get("message") or "Run error detected"),
                    "message": f"{project}/{name}: {error_event.get('line') or error_event.get('message')}",
                    "runId": run_id,
                    "project": project,
                    "evidence": str(error_event.get("source") or "logs"),
                }
            )

        sample = latest_resource(run)
        gpu_memory = float(sample.get("gpuMemory") or run.get("gpuMemoryGb") or 0)
        gpu_util = float(sample.get("gpuUtil") or run.get("gpuUtilPercent") or 0)
        cpu = float(sample.get("cpu") or run.get("cpuPercent") or 0)
        if run.get("status") == "running" and gpu_memory > 2 and gpu_util < 5:
            diagnostics.append(
                {
                    "id": f"{run_id}:idle-gpu",
                    "severity": "warning",
                    "type": "idle_gpu",
                    "title": "Possible idle GPU allocation",
                    "message": f"{project}/{name}: {gpu_memory:.2f} GB allocated but GPU util is {gpu_util:.1f}%",
                    "runId": run_id,
                    "project": project,
                    "evidence": "gpuMemory > 2GB and gpuUtil < 5%",
                }
            )
        if run.get("status") == "running" and gpu_util < 20 and cpu > 90:
            diagnostics.append(
                {
                    "id": f"{run_id}:cpu-bottleneck",
                    "severity": "info",
                    "type": "cpu_bottleneck",
                    "title": "Possible CPU-side bottleneck",
                    "message": f"{project}/{name}: CPU {cpu:.1f}% while GPU util is {gpu_util:.1f}%",
                    "runId": run_id,
                    "project": project,
                    "evidence": "high process tree CPU with low GPU util",
                }
            )

    for gpu in gpus:
        memory_gb = float(gpu.get("memoryUsedMiB") or 0) / 1024
        util = float(gpu.get("utilization") or 0)
        for process in gpu.get("processes") or []:
            if process.get("role") == "notebook" and not process.get("runId"):
                diagnostics.append(
                    {
                        "id": f"gpu-{gpu.get('index')}:notebook:{process.get('pid')}",
                        "severity": "info",
                        "type": "notebook_gpu",
                        "title": "Notebook holding GPU memory",
                        "message": f"GPU {gpu.get('index')} PID {process.get('pid')} is a Jupyter/ipykernel process using {float(process.get('usedMemoryMiB') or 0) / 1024:.2f} GB",
                        "runId": "",
                        "project": "",
                        "evidence": str(process.get("command") or process.get("name") or "gpu process"),
                    }
                )
        if memory_gb > 2 and util < 5 and gpu.get("processes"):
            diagnostics.append(
                {
                    "id": f"gpu-{gpu.get('index')}:idle",
                    "severity": "warning",
                    "type": "idle_gpu",
                    "title": f"GPU {gpu.get('index')} may be idle",
                    "message": f"{memory_gb:.2f} GB allocated, GPU util {util:.1f}%",
                    "runId": "",
                    "project": "",
                    "evidence": "host GPU process table",
                }
            )
    return diagnostics[:20]


def stable_visualization_id(kind: str, path: Path) -> str:
    digest = hashlib.sha1(f"{kind}:{path.resolve()}".encode("utf-8", errors="ignore")).hexdigest()[:16]
    return digest


def path_depth(path: Path, root: Path) -> int:
    try:
        return len(path.relative_to(root).parts)
    except ValueError:
        return 999


def safe_relative(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def file_size_mb(path: Path) -> float:
    try:
        return round(path.stat().st_size / 1024 / 1024, 2)
    except OSError:
        return 0.0


def file_mtime(path: Path) -> str:
    try:
        return datetime.fromtimestamp(path.stat().st_mtime).isoformat(timespec="seconds")
    except OSError:
        return ""


def visualization_record(kind: str, path: Path, run_dir: Path, label: str, viewer: str, file_count: int = 1) -> dict[str, Any]:
    return {
        "id": stable_visualization_id(kind, path),
        "kind": kind,
        "label": label,
        "path": str(path),
        "relativePath": safe_relative(path, run_dir),
        "viewer": viewer,
        "fileCount": file_count,
        "sizeMb": file_size_mb(path) if path.is_file() else 0,
        "updatedAt": file_mtime(path),
    }


def discover_visualizations(run_dir: Path) -> list[dict[str, Any]]:
    if not run_dir.exists():
        return []
    max_depth = 8
    records: list[dict[str, Any]] = []
    tensorboard_dirs: dict[Path, int] = {}

    for path in run_dir.rglob("*"):
        if path_depth(path, run_dir) > max_depth:
            continue
        name = path.name
        lower = name.lower()
        if path.is_file() and (name.startswith("events.out.tfevents") or ".tfevents." in name):
            tensorboard_dirs[path.parent] = tensorboard_dirs.get(path.parent, 0) + 1
        elif path.is_dir() and path.parent.name == "wandb" and (name.startswith("run-") or name.startswith("offline-run-")):
            records.append(visualization_record("wandb", path, run_dir, f"W&B {name}", "inline"))
        elif path.is_dir() and name == "mlruns":
            records.append(visualization_record("mlflow", path, run_dir, "MLflow tracking directory", "external"))
        elif path.is_file() and lower in {"wandb-summary.json", "wandb-history.jsonl", "history.jsonl", "metrics.jsonl"}:
            records.append(visualization_record("metrics-jsonl", path, run_dir, name, "inline"))
        elif path.is_file() and lower.endswith(".csv") and any(token in lower for token in ("metric", "history", "progress", "result")):
            records.append(visualization_record("metrics-csv", path, run_dir, name, "inline"))

    for log_dir, count in tensorboard_dirs.items():
        records.append(visualization_record("tensorboard", log_dir, run_dir, f"TensorBoard: {safe_relative(log_dir, run_dir)}", "external", count))

    records.sort(key=lambda item: (str(item.get("kind")), str(item.get("relativePath"))))
    return records[:200]


def visualization_for_run(run_id: str, viz_id: str) -> tuple[Path | None, dict[str, Any] | None]:
    run_dir = find_manifest_dir_for_run(run_id)
    if not run_dir:
        return None, None
    for item in discover_visualizations(run_dir):
        if str(item.get("id")) == viz_id:
            return run_dir, item
    return run_dir, None


def read_numeric_jsonl(path: Path, max_rows: int = 500) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in tail_lines(path, max_rows):
        if not line.strip():
            continue
        try:
            parsed = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(parsed, dict):
            continue
        metrics = parsed.get("metrics") if isinstance(parsed.get("metrics"), dict) else parsed
        row: dict[str, Any] = {"time": str(parsed.get("time") or parsed.get("ts") or parsed.get("step") or len(rows))}
        for key, value in metrics.items():
            if isinstance(value, (int, float)) and key not in {"time", "ts", "step"}:
                row[str(key)] = value
        if len(row) > 1:
            rows.append(row)
    return rows


def read_numeric_csv(path: Path, max_rows: int = 500) -> list[dict[str, Any]]:
    import csv

    rows: list[dict[str, Any]] = []
    try:
        with path.open("r", encoding="utf-8", errors="replace", newline="") as handle:
            for index, row in enumerate(csv.DictReader(handle)):
                out: dict[str, Any] = {"time": row.get("time") or row.get("timestamp") or row.get("step") or str(index)}
                for key, value in row.items():
                    if key in {"time", "timestamp", "step"}:
                        continue
                    try:
                        out[key] = float(value)
                    except (TypeError, ValueError):
                        pass
                if len(out) > 1:
                    rows.append(out)
                if len(rows) >= max_rows:
                    break
    except OSError:
        return []
    return rows


def read_wandb_preview(path: Path) -> dict[str, Any]:
    files_dir = path / "files"
    summary_path = files_dir / "wandb-summary.json"
    history_path = files_dir / "wandb-history.jsonl"
    summary: dict[str, Any] = {}
    if summary_path.exists():
        try:
            parsed = json.loads(summary_path.read_text(encoding="utf-8", errors="replace"))
            if isinstance(parsed, dict):
                summary = {key: value for key, value in parsed.items() if isinstance(value, (int, float, str, bool))}
        except json.JSONDecodeError:
            summary = {}
    rows = read_numeric_jsonl(history_path) if history_path.exists() else []
    return {"summary": summary, "rows": rows}


def visualization_preview(run_id: str, viz_id: str) -> tuple[int, dict[str, Any]]:
    _run_dir, item = visualization_for_run(run_id, viz_id)
    if not item:
        return 404, {"ok": False, "error": "visualization not found"}
    path = Path(str(item.get("path") or ""))
    kind = str(item.get("kind") or "")
    if kind == "wandb":
        preview = read_wandb_preview(path)
    elif kind == "metrics-csv":
        preview = {"summary": {}, "rows": read_numeric_csv(path)}
    elif kind == "metrics-jsonl":
        if path.suffix.lower() == ".json":
            parsed = read_json(path)
            summary = {key: value for key, value in parsed.items() if isinstance(value, (int, float, str, bool))}
            preview = {"summary": summary, "rows": []}
        else:
            preview = {"summary": {}, "rows": read_numeric_jsonl(path)}
    else:
        preview = {"summary": {}, "rows": [], "message": "Use the external viewer for this log type."}
    return 200, {"ok": True, "visualization": item, **preview}


def find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def open_visualization(run_id: str, viz_id: str) -> tuple[int, dict[str, Any]]:
    _run_dir, item = visualization_for_run(run_id, viz_id)
    if not item:
        return 404, {"ok": False, "error": "visualization not found"}
    key = f"{run_id}:{viz_id}"
    existing = VISUALIZATION_PROCESSES.get(key)
    if existing:
        process = existing.get("process")
        if process and process.poll() is None:
            return 200, {"ok": True, "url": existing.get("url"), "alreadyRunning": True}

    kind = str(item.get("kind") or "")
    path = Path(str(item.get("path") or ""))
    port = find_free_port()
    if kind == "tensorboard":
        command = [sys.executable, "-m", "tensorboard.main", "--logdir", str(path), "--host", "127.0.0.1", "--port", str(port)]
        url = f"http://127.0.0.1:{port}"
    elif kind == "mlflow":
        command = [sys.executable, "-m", "mlflow", "ui", "--backend-store-uri", str(path), "--host", "127.0.0.1", "--port", str(port)]
        url = f"http://127.0.0.1:{port}"
    else:
        return 400, {"ok": False, "error": "this visualization is rendered inline and does not need an external viewer"}

    try:
        process = subprocess.Popen(command, cwd=str(path), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError as exc:
        return 500, {"ok": False, "error": str(exc), "command": command}
    VISUALIZATION_PROCESSES[key] = {"process": process, "url": url, "command": command}
    return 200, {"ok": True, "url": url, "command": command}


def run_from_manifest(run_dir: Path, gpus: list[dict[str, Any]]) -> dict[str, Any] | None:
    manifest = read_yaml(run_dir / "manifest.yaml")
    if not manifest:
        return None
    status_doc = read_json(run_dir / "status.json")
    hparams = read_yaml(run_dir / "hparams.yaml")
    metrics = read_metrics(run_dir)
    events = read_events(run_dir)

    run_doc = manifest.get("run", {}) if isinstance(manifest.get("run"), dict) else {}
    host_doc = manifest.get("host", {}) if isinstance(manifest.get("host"), dict) else {}
    entry_doc = manifest.get("entrypoint", {}) if isinstance(manifest.get("entrypoint"), dict) else {}
    process_doc = manifest.get("process", {}) if isinstance(manifest.get("process"), dict) else {}
    time_doc = manifest.get("time", {}) if isinstance(manifest.get("time"), dict) else {}
    manifest_run_id = str(run_doc.get("run_id") or run_dir.name)

    command = str(entry_doc.get("command") or status_doc.get("command") or "")
    cwd = str(entry_doc.get("cwd") or status_doc.get("cwd") or run_dir)
    root_pid = int(process_doc.get("root_pid") or status_doc.get("pid") or 0)
    root_create_time = process_doc.get("root_create_time")
    status = str(status_doc.get("status") or run_doc.get("status") or "unknown")
    alive = process_is_alive(root_pid, root_create_time)
    stale_running_record = status == "running" and not alive
    if alive:
        status = "running"
        try:
            live_run = run_from_process(
                psutil.Process(root_pid),
                access_level="A",
                tags=list(run_doc.get("tags") or []),
                gpus=gpus,
                gpu_pids=gpu_process_pids(gpus),
                run_id_override=manifest_run_id,
            )
        except (psutil.AccessDenied, psutil.NoSuchProcess):
            live_run = None
    else:
        if stale_running_record:
            status = "finished"
        live_run = None

    started_at = str(time_doc.get("started_at") or status_doc.get("started_at") or "")
    runtime_seconds = runtime_from_status(status_doc, started_at)
    latest_metric, best_metric = summarize_metric(metrics)
    logs = tail_lines(run_dir / "stdout.log", 60) + tail_lines(run_dir / "stderr.log", 30)
    if not logs:
        logs = [f"manifest discovered at {run_dir}", f"status={status}"]
    merged_hparams = hparams_for_process(command, cwd)
    merged_hparams.update(flatten_hparams(hparams))

    if live_run:
        tree = live_run["processTree"]
        cpu = live_run["cpuPercent"]
        memory = live_run["memoryGb"]
        if live_run.get("resources"):
            append_resource_sample(run_dir, dict(live_run["resources"][-1]))
        resources = read_resources(run_dir) or live_run["resources"]
        disk_io = live_run["diskIo"]
        gpu_label = live_run.get("gpuLabel", "-")
        gpu_memory_gb = live_run.get("gpuMemoryGb", 0)
        gpu_util_percent = live_run.get("gpuUtilPercent", 0)
        gpu_power_w = live_run.get("gpuPowerW", 0)
        gpu_temperature_c = live_run.get("gpuTemperatureC", 0)
    else:
        tree = empty_process_node(root_pid, detect_name(command) if command else run_dir.name)
        cpu = 0
        memory = 0
        disk_io = 0
        resources = read_resources(run_dir)
        gpu_label = "-"
        gpu_memory_gb = 0
        gpu_util_percent = 0
        gpu_power_w = 0
        gpu_temperature_c = 0
    summary = build_run_summary(status, status_doc, runtime_seconds, resources, metrics, events, gpu_label)

    return {
        "id": manifest_run_id,
        "project": str(run_doc.get("project") or detect_project(command, cwd)),
        "name": str(run_doc.get("name") or detect_name(command) or run_dir.name),
        "status": status if status in {"running", "finished", "failed", "killed", "unmanaged"} else ("running" if alive else "finished"),
        "resourceType": str(run_doc.get("resource_type") or infer_resource_type(command, gpus)),
        "hostId": canonical_host_id(host_doc.get("host_id")),
        "user": str(host_doc.get("user") or os.environ.get("USERNAME") or "local"),
        "rootPid": root_pid,
        "rootCreateTime": format_create_time(root_create_time, started_at),
        "command": shorten_command(command),
        "cwd": cwd,
        "runtime": format_runtime(runtime_seconds),
        "rootCpuPercent": float(tree.get("cpu") or 0),
        "processTreeCpuPercent": cpu,
        "cpuPercent": cpu,
        "memoryGb": memory,
        "gpuLabel": gpu_label,
        "gpuMemoryGb": gpu_memory_gb,
        "gpuUtilPercent": gpu_util_percent,
        "gpuPowerW": gpu_power_w,
        "gpuTemperatureC": gpu_temperature_c,
        "diskIo": disk_io,
        "latestMetric": latest_metric,
        "bestMetric": best_metric,
        "entrypointKind": str(entry_doc.get("kind") or detect_entrypoint(command)),
        "tags": list(run_doc.get("tags") or ["managed"]),
        "accessLevel": "A" if status_doc.get("launcher") == "expmon" else "B",
        "processTree": tree,
        "hparams": merged_hparams,
        "logs": logs,
        "metrics": metrics,
        "resources": resources,
        "events": events,
        "summary": summary,
        "metadata": run_metadata_for(manifest_run_id),
        "visualizations": discover_visualizations(run_dir),
        "gpuProcesses": [],
    }


def runtime_from_status(status_doc: dict[str, Any], started_at: str) -> int:
    start_value = status_doc.get("started_at") or started_at
    end_value = status_doc.get("ended_at")
    try:
        start = datetime.fromisoformat(str(start_value))
        end = datetime.fromisoformat(str(end_value)) if end_value else datetime.now()
        return max(0, int((end - start).total_seconds()))
    except Exception:
        return 0


def discover_protocol_runs(gpus: list[dict[str, Any]]) -> list[dict[str, Any]]:
    runs = []
    for run_dir in find_manifest_dirs():
        run = run_from_manifest(run_dir, gpus)
        if run:
            runs.append(run)
    runs.sort(key=lambda item: str(item.get("rootCreateTime", "")), reverse=True)
    return runs


def collect_snapshot() -> dict[str, Any]:
    psutil.cpu_percent(interval=None)
    gpus = gpu_samples()
    gpu_pids = gpu_process_pids(gpus)
    protocol_runs = discover_protocol_runs(gpus)
    protocol_pids = {int(run.get("rootPid") or 0) for run in protocol_runs}

    processes = candidate_process_infos()
    workspace = [info for info in processes if is_workspace_process(info)]
    workspace_pids = {int(info["pid"]) for info in workspace}
    roots = [
        info
        for info in workspace
        if int(info.get("pid") or 0) not in protocol_pids and is_run_root(info, workspace_pids)
    ]

    unmanaged_top_n = int(CONFIG.get("sampling", {}).get("unmanaged_top_n", 80))
    unmanaged_runs = []
    for info in roots[:unmanaged_top_n]:
        try:
            run = run_from_process(psutil.Process(int(info["pid"])), gpus=gpus, gpu_pids=gpu_pids)
            if run:
                unmanaged_runs.append(run)
        except (psutil.AccessDenied, psutil.NoSuchProcess):
            pass

    runs = protocol_runs + unmanaged_runs
    attribute_gpu_processes_to_runs(runs, gpus)
    runs.sort(key=lambda item: (bool((item.get("metadata") or {}).get("pinned")), str(item.get("rootCreateTime", ""))), reverse=True)
    projects = projects_from_runs(runs)
    diagnostics = build_diagnostics(runs, gpus)
    memory = psutil.virtual_memory()
    disk = psutil.disk_io_counters()
    net = psutil.net_io_counters()
    disk_read_total = mib(getattr(disk, "read_bytes", 0)) if disk else 0
    disk_write_total = mib(getattr(disk, "write_bytes", 0)) if disk else 0
    net_rx_total = mib(getattr(net, "bytes_recv", 0)) if net else 0
    net_tx_total = mib(getattr(net, "bytes_sent", 0)) if net else 0
    disk_read_rate, disk_write_rate, net_rx_rate, net_tx_rate = host_io_rates(
        disk_read_total,
        disk_write_total,
        net_rx_total,
        net_tx_total,
    )
    gpu_total = len(gpus)
    gpu_busy = sum(1 for gpu in gpus if gpu["busy"])
    cpu_cores = [round(value, 1) for value in psutil.cpu_percent(interval=None, percpu=True)]
    host_id = canonical_host_id()
    host_history = update_host_history(
        host_id,
        {
            "time": format_clock(),
            "ts": datetime.now().isoformat(timespec="seconds"),
            "read": disk_read_rate,
            "write": disk_write_rate,
            "rx": net_rx_rate,
            "tx": net_tx_rate,
            "readTotal": disk_read_total,
            "writeTotal": disk_write_total,
            "rxTotal": net_rx_total,
            "txTotal": net_tx_total,
        },
    )
    return {
        "hosts": [
            {
                "id": host_id,
                "name": "Local Host",
                "os": f"{os.name} / {socket.gethostname()}",
                "address": "127.0.0.1",
                "user": os.environ.get("USERNAME") or "local",
                "cpuUsage": round(psutil.cpu_percent(interval=None), 1),
                "memoryUsedGb": gb(memory.used),
                "memoryTotalGb": gb(memory.total),
                "gpusTotal": gpu_total,
                "gpusBusy": gpu_busy,
                "gpus": gpus,
                "diskRead": disk_read_rate,
                "diskWrite": disk_write_rate,
                "netRx": net_rx_rate,
                "netTx": net_tx_rate,
                "runningRuns": len([run for run in runs if run.get("status") == "running"]),
                "warnings": [] if runs else ["No experiment runs"],
                "cores": cpu_cores,
                "history": host_history,
            }
        ],
        "runs": runs,
        "projects": projects,
        "diagnostics": diagnostics,
        "sshServers": ssh_servers_payload()["servers"],
        "sshKeyCandidates": ssh_key_candidates(),
        "updatedAt": datetime.now().isoformat(),
        "config": CONFIG,
        "configMetadata": config_metadata(),
    }


def snapshot() -> dict[str, Any]:
    with SNAPSHOT_LOCK:
        cached = LATEST_SNAPSHOT
    if cached is not None:
        return cached
    return collect_snapshot()


def sample_loop() -> None:
    global LATEST_SNAPSHOT
    while True:
        try:
            next_snapshot = collect_snapshot()
            with SNAPSHOT_LOCK:
                LATEST_SNAPSHOT = next_snapshot
        except Exception as exc:
            with SNAPSHOT_LOCK:
                LATEST_SNAPSHOT = {
                    "hosts": [],
                    "runs": [],
                    "updatedAt": datetime.now().isoformat(),
                    "error": str(exc),
                }
        time.sleep(SAMPLE_INTERVAL_SECONDS)


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/api/snapshot":
            self.send_json(snapshot())
            return
        if path == "/api/ssh/servers":
            self.send_json(ssh_servers_payload())
            return
        if path == "/api/config":
            self.send_json({"ok": True, "config": CONFIG, "metadata": config_metadata()})
            return
        match = re.fullmatch(r"/api/projects/([^/]+)/git", path)
        if match:
            project_id = unquote(match.group(1))
            status, payload = git_payload(project_id)
            self.send_json(payload, status=status)
            return
        match = re.fullmatch(r"/api/runs/([^/]+)/visualizations/([^/]+)/preview", path)
        if match:
            run_id = unquote(match.group(1))
            viz_id = unquote(match.group(2))
            status, payload = visualization_preview(run_id, viz_id)
            self.send_json(payload, status=status)
            return
        if path == "/health":
            self.send_json({"ok": True, "intervalSeconds": SAMPLE_INTERVAL_SECONDS, "config": CONFIG, "metadata": config_metadata()})
            return
        self.send_error(404)

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self.send_cors_headers()
        self.send_header("Access-Control-Max-Age", "600")
        self.end_headers()

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        if path == "/api/ssh/servers":
            status, payload = validate_and_save_ssh_server(read_json_body(self))
            self.send_json(payload, status=status)
            return
        if path == "/api/config":
            status, payload = save_collector_config(read_json_body(self))
            self.send_json(payload, status=status)
            return
        match = re.fullmatch(r"/api/runs/([^/]+)/kill", path)
        if match:
            run_id = unquote(match.group(1))
            status, payload = kill_run(run_id)
            self.send_json(payload, status=status)
            return
        match = re.fullmatch(r"/api/runs/([^/]+)/visualizations/([^/]+)/open", path)
        if match:
            run_id = unquote(match.group(1))
            viz_id = unquote(match.group(2))
            status, payload = open_visualization(run_id, viz_id)
            self.send_json(payload, status=status)
            return
        match = re.fullmatch(r"/api/runs/([^/]+)/metadata", path)
        if match:
            run_id = unquote(match.group(1))
            status, payload = save_run_metadata(run_id, read_json_body(self))
            self.send_json(payload, status=status)
            return
        match = re.fullmatch(r"/api/ssh/servers/([^/]+)/test", path)
        if match:
            server_id = unquote(match.group(1))
            status, payload = test_ssh_server(server_id)
            self.send_json(payload, status=status)
            return
        match = re.fullmatch(r"/api/ssh/servers/([^/]+)/resources", path)
        if match:
            server_id = unquote(match.group(1))
            status, payload = ssh_remote_resource_snapshot(server_id)
            self.send_json(payload, status=status)
            return
        match = re.fullmatch(r"/api/projects/([^/]+)/git/(pull|push|commit-message|commit)", path)
        if match:
            project_id = unquote(match.group(1))
            action = match.group(2)
            if action == "commit-message":
                status, payload = generate_commit_message(project_id)
            elif action == "commit":
                status, payload = commit_project(project_id, read_json_body(self))
            else:
                status, payload = git_action(project_id, action)
            self.send_json(payload, status=status)
            return
        self.send_error(404)

    def do_DELETE(self) -> None:
        path = urlparse(self.path).path
        if path == "/api/ssh/servers":
            status, payload = clear_ssh_servers()
            self.send_json(payload, status=status)
            return
        match = re.fullmatch(r"/api/ssh/servers/([^/]+)", path)
        if match:
            server_id = unquote(match.group(1))
            status, payload = delete_ssh_server(server_id)
            self.send_json(payload, status=status)
            return
        match = re.fullmatch(r"/api/runs/([^/]+)", path)
        if match:
            run_id = unquote(match.group(1))
            status, payload = delete_run_record(run_id)
            self.send_json(payload, status=status)
            return
        self.send_error(404)

    def send_json(self, payload: dict[str, Any], status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_cors_headers()
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_cors_headers(self) -> None:
        origin = self.headers.get("Origin") or "http://127.0.0.1:5173"
        if re.fullmatch(r"https?://(127\.0\.0\.1|localhost):\d+", origin):
            self.send_header("Access-Control-Allow-Origin", origin)
        else:
            self.send_header("Access-Control-Allow-Origin", "http://127.0.0.1:5173")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def log_message(self, format: str, *args: Any) -> None:
        return


def main() -> None:
    thread = threading.Thread(target=sample_loop, daemon=True)
    thread.start()
    server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    print(f"local collector listening on http://127.0.0.1:{PORT}")
    print(f"config roots: {', '.join(str(root) for root in configured_roots())}")
    server.serve_forever()


if __name__ == "__main__":
    main()
