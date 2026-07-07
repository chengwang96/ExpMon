from __future__ import annotations

import argparse
import getpass
import json
import os
import platform
import shutil
import socket
import subprocess
import time
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

import psutil


HOST_HISTORY: list[dict[str, Any]] = []
IO_HISTORY: tuple[float, float, float, float, float] | None = None
MAX_HISTORY = int(os.environ.get("EXPMON_AGENT_MAX_HISTORY", "240"))
TOKEN = os.environ.get("EXPMON_AGENT_TOKEN", "").strip()
GPU_CACHE: tuple[float, list[dict[str, Any]]] | None = None
GPU_CACHE_SECONDS = float(os.environ.get("EXPMON_AGENT_GPU_CACHE_SECONDS", "10"))

NVIDIA_POWER_LIMIT_CATALOG_W = {
    "rtx 5090": 575,
    "rtx 5080": 360,
    "rtx 4090 laptop": 150,
    "rtx 4080 laptop": 150,
    "rtx 4070 laptop": 115,
    "rtx 4060 laptop": 115,
    "rtx 4050 laptop": 115,
    "rtx 4090": 450,
    "rtx 4080 super": 320,
    "rtx 4080": 320,
    "rtx 4070 ti super": 285,
    "rtx 4070 ti": 285,
    "rtx 4070 super": 220,
    "rtx 4070": 200,
    "rtx 4060 ti": 160,
    "rtx 4060": 115,
    "rtx 3090 ti": 450,
    "rtx 3090": 350,
    "rtx 3080 ti": 350,
    "rtx 3080": 320,
    "rtx 3070 ti": 290,
    "rtx 3070": 220,
    "rtx 3060 ti": 200,
    "rtx 3060": 170,
    "rtx 3050": 130,
}


def mib(value: float) -> float:
    return round(value / 1024 / 1024, 2)


def gb(value: float) -> float:
    return round(value / 1024 / 1024 / 1024, 2)


def memory_breakdown(memory: Any) -> list[dict[str, Any]]:
    total = float(getattr(memory, "total", 0) or 0)
    if total <= 0:
        return []

    def row(key: str, label: str, value: float, note: str = "") -> dict[str, Any] | None:
        value = float(value or 0)
        if value < 0:
            return None
        return {
            "key": key,
            "label": label,
            "valueGb": gb(value),
            "percent": round((value / total) * 100, 1) if total else 0,
            "note": note,
        }

    system = platform.system().lower()
    if system == "windows":
        rows = [
            row("windows_used", "In use", getattr(memory, "used", 0), "Windows: committed physical memory in use"),
            row("windows_available", "Available", getattr(memory, "available", 0), "Windows: immediately available without paging"),
            *windows_memory_counter_rows(row),
        ]
    elif system == "darwin":
        rows = [
            row("macos_wired", "Wired", getattr(memory, "wired", 0), "macOS: memory that cannot be paged out"),
            row("macos_active", "Active", getattr(memory, "active", 0), "macOS: recently used application memory"),
            row("macos_inactive", "Inactive", getattr(memory, "inactive", 0), "macOS: reclaimable inactive memory"),
            row("macos_compressed", "Compressed", getattr(memory, "compressed", 0), "macOS: memory compressed by the kernel"),
            row("macos_free", "Free", getattr(memory, "free", 0), "macOS: unused pages"),
        ]
    elif system == "linux":
        rows = linux_memory_proc_rows(row) or [
            row("linux_used", "Used", max(0, total - float(getattr(memory, "available", 0) or 0)), "Linux: total - available"),
            row("linux_buffers", "Buffers", getattr(memory, "buffers", 0), "Linux: block device buffers"),
            row("linux_cache", "Cache", getattr(memory, "cached", 0), "Linux: file cache and reclaimable cache"),
            row("linux_shared", "Shared", getattr(memory, "shared", 0), "Linux: tmpfs/shared memory"),
            row("linux_available", "Available", getattr(memory, "available", 0), "Linux: estimated memory available to new processes"),
        ]
    else:
        rows = [
            row("used", "Used", getattr(memory, "used", 0)),
            row("available", "Available", getattr(memory, "available", 0)),
            row("free", "Free", getattr(memory, "free", 0)),
        ]
    return [item for item in rows if item and item["valueGb"] > 0]


def windows_memory_counter_rows(row: Any) -> list[dict[str, Any] | None]:
    command = (
        "[Console]::OutputEncoding=[System.Text.Encoding]::UTF8; "
        "Get-CimInstance Win32_PerfFormattedData_PerfOS_Memory | "
        "Select-Object CacheBytes,CommittedBytes | ConvertTo-Json -Compress"
    )
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", command],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=2,
        )
        parsed = json.loads(result.stdout) if result.returncode == 0 and result.stdout.strip() else {}
    except Exception:
        parsed = {}
    if not isinstance(parsed, dict):
        parsed = {}
    return [
        row("windows_cache", "Cache", to_float(parsed.get("CacheBytes")), "Windows: system cache bytes"),
        row("windows_committed", "Committed", to_float(parsed.get("CommittedBytes")), "Windows: committed virtual memory, may exceed physical RAM"),
    ]


def linux_memory_proc_rows(row: Any) -> list[dict[str, Any] | None]:
    values: dict[str, int] = {}
    try:
        with open("/proc/meminfo", "r", encoding="utf-8") as handle:
            for line in handle:
                key, raw = line.split(":", 1)
                values[key] = int(raw.strip().split()[0])
    except Exception:
        return []
    total = values.get("MemTotal", 0)
    if total <= 0:
        return []
    kib = 1024
    return [
        row("linux_used", "Used", max(0, total - values.get("MemAvailable", 0)) * kib, "Linux: MemTotal - MemAvailable"),
        row("linux_buffers", "Buffers", values.get("Buffers", 0) * kib, "Linux: block device buffers"),
        row("linux_cache", "Cache", (values.get("Cached", 0) + values.get("SReclaimable", 0)) * kib, "Linux: file cache plus reclaimable slab"),
        row("linux_shared", "Shared", values.get("Shmem", 0) * kib, "Linux: tmpfs/shared memory"),
        row("linux_available", "Available", values.get("MemAvailable", 0) * kib, "Linux: estimated memory available to new processes"),
    ]


def to_float(value: Any) -> float:
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return 0.0


def optional_float(value: Any) -> float | None:
    text = str(value or "").strip().lower()
    if not text or "n/a" in text or "not supported" in text or "not available" in text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def catalog_power_limit_w(name: str) -> float | None:
    normalized = " ".join(str(name or "").lower().replace("geforce", "").split())
    for key, watts in NVIDIA_POWER_LIMIT_CATALOG_W.items():
        if key in normalized:
            return float(watts)
    return None


def io_rates(read_total: float, write_total: float, rx_total: float, tx_total: float) -> tuple[float, float, float, float]:
    global IO_HISTORY
    now = time.time()
    previous = IO_HISTORY
    IO_HISTORY = (now, read_total, write_total, rx_total, tx_total)
    if not previous:
        return 0, 0, 0, 0
    previous_time, previous_read, previous_write, previous_rx, previous_tx = previous
    elapsed = max(0.001, now - previous_time)
    return (
        round(max(0, read_total - previous_read) / elapsed, 2),
        round(max(0, write_total - previous_write) / elapsed, 2),
        round(max(0, rx_total - previous_rx) / elapsed, 2),
        round(max(0, tx_total - previous_tx) / elapsed, 2),
    )


def nvidia_gpus() -> list[dict[str, Any]]:
    global GPU_CACHE
    now = time.time()
    if GPU_CACHE and now - GPU_CACHE[0] <= GPU_CACHE_SECONDS:
        return GPU_CACHE[1]
    nvidia = shutil.which("nvidia-smi")
    if not nvidia:
        return []
    query = "index,uuid,name,memory.total,memory.used,utilization.gpu,power.draw,power.limit,enforced.power.limit,temperature.gpu"
    try:
        result = subprocess.run(
            [nvidia, f"--query-gpu={query}", "--format=csv,noheader,nounits"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=2,
        )
    except Exception:
        return GPU_CACHE[1] if GPU_CACHE else []
    if result.returncode != 0:
        return GPU_CACHE[1] if GPU_CACHE else []

    rows: list[dict[str, Any]] = []
    for line in result.stdout.splitlines():
        parts = [part.strip() for part in line.split(",")]
        if len(parts) < 10:
            continue
        total = to_float(parts[3])
        used = to_float(parts[4])
        util = to_float(parts[5])
        power_limit = optional_float(parts[7]) or optional_float(parts[8])
        power_limit_source = "nvidia-smi" if power_limit else "unknown"
        if power_limit is None:
            power_limit = catalog_power_limit_w(parts[2])
            power_limit_source = "catalog" if power_limit else "unknown"
        rows.append(
            {
                "index": int(to_float(parts[0])),
                "uuid": parts[1],
                "name": parts[2],
                "memoryTotalMiB": total,
                "memoryUsedMiB": used,
                "memoryPercent": round((used / total) * 100, 1) if total else 0,
                "utilization": util,
                "powerDrawW": to_float(parts[6]),
                "powerLimitW": power_limit,
                "powerLimitSource": power_limit_source,
                "temperatureC": to_float(parts[9]),
                "busy": util > 0 or used > 0,
                "processes": [],
            }
        )

    try:
        proc_result = subprocess.run(
            [nvidia, "--query-compute-apps=pid,process_name,used_memory,gpu_uuid", "--format=csv,noheader,nounits"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=2,
        )
    except Exception:
        proc_result = None
    if proc_result and proc_result.returncode == 0:
        for line in proc_result.stdout.splitlines():
            parts = [part.strip() for part in line.split(",")]
            if len(parts) < 4:
                continue
            gpu_uuid = parts[3]
            gpu_index = next((gpu["index"] for gpu in rows if gpu.get("uuid") == gpu_uuid), 0)
            process = {
                "pid": int(to_float(parts[0])),
                "name": os.path.basename(parts[1]) or parts[1],
                "command": parts[1],
                "usedMemoryMiB": to_float(parts[2]),
                "gpuUuid": gpu_uuid,
                "gpuIndex": gpu_index,
            }
            for gpu in rows:
                if gpu.get("uuid") == gpu_uuid:
                    gpu.setdefault("processes", []).append(process)
    GPU_CACHE = (now, rows)
    return rows


def top_processes() -> list[dict[str, Any]]:
    if os.name == "nt":
        return windows_top_processes()
    rows = []
    for process in psutil.process_iter(["pid", "name", "memory_info"]):
        try:
            cpu = process.cpu_percent(interval=None)
            memory_info = process.info.get("memory_info")
            name = str(process.info.get("name") or f"pid {process.pid}")
            rows.append(
                {
                    "pid": int(process.info.get("pid") or 0),
                    "name": name,
                    "command": name,
                    "cpu": round(float(cpu or 0), 1),
                    "memoryGb": gb(getattr(memory_info, "rss", 0) if memory_info else 0),
                }
            )
        except (psutil.AccessDenied, psutil.NoSuchProcess, psutil.ZombieProcess):
            continue
    return sorted(rows, key=lambda item: (float(item.get("cpu") or 0), float(item.get("memoryGb") or 0)), reverse=True)[:8]


def windows_top_processes() -> list[dict[str, Any]]:
    command = (
        "[Console]::OutputEncoding=[System.Text.Encoding]::UTF8; "
        "Get-CimInstance Win32_PerfFormattedData_PerfProc_Process | "
        "Where-Object { $_.IDProcess -gt 0 -and $_.Name -notin @('Idle','_Total') } | "
        "Sort-Object PercentProcessorTime -Descending | "
        "Select-Object -First 8 IDProcess,Name,PercentProcessorTime,WorkingSetPrivate | "
        "ConvertTo-Json -Compress"
    )
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", command],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=4,
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
    processes = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        name = str(row.get("Name") or f"pid {row.get('IDProcess') or 0}")
        processes.append(
            {
                "pid": int(to_float(row.get("IDProcess") or 0)),
                "name": name,
                "command": name,
                "cpu": round(to_float(row.get("PercentProcessorTime")), 1),
                "memoryGb": round(to_float(row.get("WorkingSetPrivate")) / 1073741824, 3),
            }
        )
    return processes


def sample_host() -> dict[str, Any]:
    memory = psutil.virtual_memory()
    disk = psutil.disk_io_counters()
    net = psutil.net_io_counters()
    read_total = mib(getattr(disk, "read_bytes", 0)) if disk else 0
    write_total = mib(getattr(disk, "write_bytes", 0)) if disk else 0
    rx_total = mib(getattr(net, "bytes_recv", 0)) if net else 0
    tx_total = mib(getattr(net, "bytes_sent", 0)) if net else 0
    disk_read, disk_write, net_rx, net_tx = io_rates(read_total, write_total, rx_total, tx_total)
    cores = [round(float(value), 1) for value in psutil.cpu_percent(interval=0.1, percpu=True)]
    gpus = nvidia_gpus()
    sampled_at = datetime.now().isoformat(timespec="seconds")
    history_row = {
        "time": datetime.now().strftime("%H:%M:%S"),
        "ts": sampled_at,
        "read": disk_read,
        "write": disk_write,
        "rx": net_rx,
        "tx": net_tx,
    }
    HOST_HISTORY.append(history_row)
    if len(HOST_HISTORY) > MAX_HISTORY:
        del HOST_HISTORY[:-MAX_HISTORY]
    return {
        "hostname": socket.gethostname(),
        "os": platform.platform(),
        "remoteOs": platform.system().lower(),
        "user": getpass.getuser(),
        "cpuUsage": round(float(psutil.cpu_percent(interval=None)), 1),
        "cores": cores,
        "memoryUsedGb": gb(memory.used),
        "memoryTotalGb": gb(memory.total),
        "memoryBreakdown": memory_breakdown(memory),
        "diskRead": disk_read,
        "diskWrite": disk_write,
        "netRx": net_rx,
        "netTx": net_tx,
        "processes": top_processes(),
        "gpus": gpus,
        "gpusTotal": len(gpus),
        "gpusBusy": sum(1 for gpu in gpus if gpu.get("busy")),
        "history": list(HOST_HISTORY),
        "sampledAt": sampled_at,
        "pythonPath": os.sys.executable,
    }


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if TOKEN:
            supplied = self.headers.get("X-ExpMon-Agent-Token") or self.headers.get("Authorization", "").removeprefix("Bearer ").strip()
            if supplied != TOKEN:
                self.send_json({"ok": False, "error": "unauthorized"}, status=401)
                return
        if self.path == "/api/health":
            self.send_json({"ok": True, "hostname": socket.gethostname()})
            return
        if self.path == "/api/host":
            self.send_json(sample_host())
            return
        self.send_error(404)

    def send_json(self, payload: dict[str, Any], status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: Any) -> None:
        return


def main() -> None:
    parser = argparse.ArgumentParser(description="ExpMon lightweight remote resource collector")
    parser.add_argument("--host", default=os.environ.get("EXPMON_AGENT_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("EXPMON_AGENT_PORT", "5194")))
    args = parser.parse_args()
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"ExpMon remote agent listening on http://{args.host}:{args.port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
