import ctypes
import os
import platform
import re
import shutil
import subprocess
import threading
import time
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path
from typing import Any

import psutil

try:
    import winreg
except ImportError:  # pragma: no cover - only available on Windows.
    winreg = None


AIDA64_MAPPING_NAMES = (
    "AIDA64_SensorValues",
    "Local\\AIDA64_SensorValues",
    "Global\\AIDA64_SensorValues",
)

AIDA64_START_RETRY_SECONDS = 60
_AIDA64_START_LOCK = threading.Lock()
_AIDA64_LAST_START_ATTEMPT = 0.0
_AIDA64_LAST_START_ERROR = ""
_AIDA64_LAST_START_PATH = ""
_AIDA64_START_REQUESTED = False
_AIDA64_EXECUTABLE_CACHE: Path | None = None

SENSOR_UNITS = {
    "temp": "C",
    "fan": "RPM",
    "duty": "%",
    "volt": "V",
    "curr": "A",
    "pwr": "W",
    "flow": "L/h",
    "liq": "%",
}

SENSOR_CATEGORIES = {
    "pwr": "power",
    "temp": "temperature",
    "volt": "electrical",
    "curr": "electrical",
    "fan": "cooling",
    "duty": "cooling",
    "flow": "cooling",
    "liq": "cooling",
    "sys": "system",
}


def decode_aida64_buffer(raw: bytes) -> str:
    if not raw:
        return ""
    if len(raw) > 1 and raw[1] == 0:
        end = len(raw)
        for index in range(0, len(raw) - 1, 2):
            if raw[index:index + 2] == b"\x00\x00":
                end = index
                break
        return raw[:end].decode("utf-16-le", errors="replace")
    end = raw.find(b"\x00")
    payload = raw if end < 0 else raw[:end]
    for encoding in ("utf-8", "mbcs", "latin-1"):
        try:
            return payload.decode(encoding)
        except (LookupError, UnicodeDecodeError):
            continue
    return payload.decode("latin-1", errors="replace")


def numeric_sensor_value(value: str) -> float | None:
    match = re.search(r"[-+]?(?:\d+(?:[.,]\d*)?|[.,]\d+)", str(value))
    if not match:
        return None
    try:
        return float(match.group(0).replace(",", "."))
    except ValueError:
        return None


def sensor_group(sensor_id: str, label: str) -> str:
    text = f"{sensor_id} {label}".upper()
    if "GPU" in text:
        return "GPU"
    if any(token in text for token in ("CPU", "CORE", "PACKAGE", "UNCORE", "SOC")):
        return "CPU"
    if any(token in text for token in ("DIMM", "DRAM", "MEMORY", "MEM ")):
        return "Memory"
    if any(token in text for token in ("NVME", "SSD", "HDD", "DRIVE", "DISK")):
        return "Storage"
    if any(token in text for token in ("BATTERY", "BATT", "DC IN", "DCIN", "PSU", "POWER SUPPLY")):
        return "Power supply"
    return "Board"


def infer_system_unit(sensor_id: str, label: str, value: str) -> str:
    value_text = str(value)
    text = f"{sensor_id} {label}".upper()
    if "%" in value_text or any(token in text for token in ("UTILIZATION", "TDP%", "LOAD")):
        return "%"
    if "CLOCK" in text or sensor_id.upper().endswith("CLK"):
        return "MHz"
    if "MEMORY" in text and any(token in text for token in ("USED", "FREE")):
        return "MB"
    return ""


def parse_aida64_sensor_payload(payload: str) -> list[dict[str, Any]]:
    fragment = re.sub(r"<\?xml[^>]*\?>", "", str(payload or "")).strip()
    if not fragment:
        return []
    try:
        root = ET.fromstring(f"<aida64>{fragment}</aida64>")
    except ET.ParseError:
        return []

    sensors: list[dict[str, Any]] = []
    for element in root:
        kind = str(element.tag).lower().strip()
        fields = {str(child.tag).lower(): (child.text or "").strip() for child in element}
        sensor_id = fields.get("id", "").strip()
        label = fields.get("label", sensor_id).strip() or sensor_id
        value = fields.get("value", "").strip()
        if not sensor_id or not value:
            continue
        unit = SENSOR_UNITS.get(kind, "")
        if kind == "sys":
            unit = infer_system_unit(sensor_id, label, value)
        sensors.append({
            "id": sensor_id,
            "label": label,
            "type": kind,
            "category": SENSOR_CATEGORIES.get(kind, "other"),
            "group": sensor_group(sensor_id, label),
            "value": value,
            "numericValue": numeric_sensor_value(value),
            "unit": unit,
            "source": "aida64-shared-memory",
        })

    category_order = {"power": 0, "temperature": 1, "electrical": 2, "cooling": 3, "system": 4, "other": 5}
    sensors.sort(key=lambda row: (
        category_order.get(str(row.get("category")), 9),
        str(row.get("group")),
        str(row.get("label")),
        str(row.get("id")),
    ))
    return sensors


def _read_windows_mapping(name: str) -> bytes | None:
    if platform.system().lower() != "windows":
        return None

    file_map_read = 0x0004
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.OpenFileMappingW.argtypes = (ctypes.c_uint32, ctypes.c_bool, ctypes.c_wchar_p)
    kernel32.OpenFileMappingW.restype = ctypes.c_void_p
    kernel32.MapViewOfFile.argtypes = (ctypes.c_void_p, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_size_t)
    kernel32.MapViewOfFile.restype = ctypes.c_void_p
    kernel32.UnmapViewOfFile.argtypes = (ctypes.c_void_p,)
    kernel32.CloseHandle.argtypes = (ctypes.c_void_p,)

    class MemoryBasicInformation(ctypes.Structure):
        _fields_ = [
            ("BaseAddress", ctypes.c_void_p),
            ("AllocationBase", ctypes.c_void_p),
            ("AllocationProtect", ctypes.c_uint32),
            ("PartitionId", ctypes.c_uint16),
            ("RegionSize", ctypes.c_size_t),
            ("State", ctypes.c_uint32),
            ("Protect", ctypes.c_uint32),
            ("Type", ctypes.c_uint32),
        ]

    kernel32.VirtualQuery.argtypes = (ctypes.c_void_p, ctypes.POINTER(MemoryBasicInformation), ctypes.c_size_t)
    kernel32.VirtualQuery.restype = ctypes.c_size_t

    handle = kernel32.OpenFileMappingW(file_map_read, False, name)
    if not handle:
        return None
    view = kernel32.MapViewOfFile(handle, file_map_read, 0, 0, 0)
    if not view:
        kernel32.CloseHandle(handle)
        return None
    try:
        info = MemoryBasicInformation()
        if not kernel32.VirtualQuery(view, ctypes.byref(info), ctypes.sizeof(info)):
            return None
        size = min(max(int(info.RegionSize), 4096), 4 * 1024 * 1024)
        return ctypes.string_at(view, size)
    finally:
        kernel32.UnmapViewOfFile(view)
        kernel32.CloseHandle(handle)


def read_aida64_shared_memory() -> tuple[str, list[dict[str, Any]]]:
    for name in AIDA64_MAPPING_NAMES:
        try:
            raw = _read_windows_mapping(name)
        except (OSError, ValueError):
            continue
        if raw:
            sensors = parse_aida64_sensor_payload(decode_aida64_buffer(raw))
            return name, sensors
    return "", []


def _executable_candidate(value: str | os.PathLike[str] | None) -> Path | None:
    text = os.path.expandvars(str(value or "")).strip().strip('"')
    if not text:
        return None
    # Uninstall DisplayIcon values may include an icon index after the executable.
    text = re.sub(r"\s*,\s*-?\d+\s*$", "", text).strip().strip('"')
    path = Path(text).expanduser()
    try:
        if path.is_file() and path.suffix.casefold() == ".exe":
            return path.resolve()
    except OSError:
        return None
    return None


def _registry_aida64_candidates() -> list[str]:
    if winreg is None:
        return []

    candidates: list[str] = []
    app_path_keys = (
        (winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\App Paths\aida64.exe"),
        (winreg.HKEY_LOCAL_MACHINE, r"Software\Microsoft\Windows\CurrentVersion\App Paths\aida64.exe"),
    )
    for hive, key_name in app_path_keys:
        try:
            with winreg.OpenKey(hive, key_name) as key:
                candidates.append(str(winreg.QueryValueEx(key, "")[0]))
        except OSError:
            continue

    uninstall_roots = (
        (winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Uninstall"),
        (winreg.HKEY_LOCAL_MACHINE, r"Software\Microsoft\Windows\CurrentVersion\Uninstall"),
        (winreg.HKEY_LOCAL_MACHINE, r"Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
    )
    for hive, key_name in uninstall_roots:
        try:
            with winreg.OpenKey(hive, key_name) as root:
                for index in range(winreg.QueryInfoKey(root)[0]):
                    try:
                        with winreg.OpenKey(root, winreg.EnumKey(root, index)) as entry:
                            display_name = str(winreg.QueryValueEx(entry, "DisplayName")[0])
                            if not display_name.casefold().startswith("aida64"):
                                continue
                            try:
                                install_location = str(winreg.QueryValueEx(entry, "InstallLocation")[0])
                                candidates.append(str(Path(install_location) / "aida64.exe"))
                            except OSError:
                                pass
                            try:
                                candidates.append(str(winreg.QueryValueEx(entry, "DisplayIcon")[0]))
                            except OSError:
                                pass
                    except OSError:
                        continue
        except OSError:
            continue

    # Portable copies are not registered as installed applications, but Windows
    # records executables that have been run in the Compatibility Assistant store.
    compatibility_keys = (
        r"Software\Microsoft\Windows NT\CurrentVersion\AppCompatFlags\Compatibility Assistant\Store",
        r"Software\Microsoft\Windows NT\CurrentVersion\AppCompatFlags\Compatibility Assistant\Persisted",
    )
    for key_name in compatibility_keys:
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_name) as key:
                value_count = winreg.QueryInfoKey(key)[1]
                for index in range(value_count):
                    value_name = str(winreg.EnumValue(key, index)[0])
                    if re.search(r"(?i)(?:^|[\\/])aida64[^\\/]*\.exe$", value_name):
                        candidates.append(value_name)
        except OSError:
            continue
    return candidates


def find_aida64_executable(processes: list[dict[str, Any]] | None = None) -> Path | None:
    global _AIDA64_EXECUTABLE_CACHE
    if _AIDA64_EXECUTABLE_CACHE and _AIDA64_EXECUTABLE_CACHE.is_file():
        return _AIDA64_EXECUTABLE_CACHE

    candidates: list[str | os.PathLike[str] | None] = [os.environ.get("EXPMON_AIDA64_PATH")]
    candidates.extend(process.get("exe") for process in processes or [])
    candidates.extend(_registry_aida64_candidates())

    command_path = shutil.which("aida64.exe")
    if command_path:
        candidates.append(command_path)
    for root_name in ("ProgramFiles", "ProgramFiles(x86)", "LOCALAPPDATA"):
        root = os.environ.get(root_name)
        if not root:
            continue
        for product in ("AIDA64 Extreme", "AIDA64 Engineer", "AIDA64 Business", "AIDA64 Network Audit"):
            candidates.append(Path(root) / "FinalWire" / product / "aida64.exe")

    for candidate in candidates:
        executable = _executable_candidate(candidate)
        if executable:
            _AIDA64_EXECUTABLE_CACHE = executable
            return executable
    return None


def auto_start_aida64(aida64: dict[str, Any]) -> dict[str, Any]:
    global _AIDA64_LAST_START_ATTEMPT
    global _AIDA64_LAST_START_ERROR
    global _AIDA64_LAST_START_PATH
    global _AIDA64_START_REQUESTED

    result = {
        "autoStartSupported": platform.system().lower() == "windows",
        "autoStartAttempted": _AIDA64_START_REQUESTED,
        "autoStartSucceeded": _AIDA64_START_REQUESTED and not _AIDA64_LAST_START_ERROR,
        "autoStartError": _AIDA64_LAST_START_ERROR,
        "executableFound": bool(_AIDA64_LAST_START_PATH),
    }
    if not result["autoStartSupported"]:
        return result
    if aida64.get("running"):
        executable = find_aida64_executable(aida64.get("processes"))
        result["executableFound"] = bool(executable)
        return result

    with _AIDA64_START_LOCK:
        if detect_aida64().get("running"):
            return result
        now = time.monotonic()
        if _AIDA64_LAST_START_ATTEMPT and now - _AIDA64_LAST_START_ATTEMPT < AIDA64_START_RETRY_SECONDS:
            return result

        _AIDA64_LAST_START_ATTEMPT = now
        _AIDA64_START_REQUESTED = True
        executable = find_aida64_executable(aida64.get("processes"))
        _AIDA64_LAST_START_PATH = str(executable or "")
        if not executable:
            _AIDA64_LAST_START_ERROR = (
                "AIDA64 executable was not found; install it or set EXPMON_AIDA64_PATH"
            )
        else:
            try:
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                startupinfo.wShowWindow = 0
                creationflags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
                subprocess.Popen(
                    [str(executable), "/SILENT"],
                    cwd=str(executable.parent),
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    startupinfo=startupinfo,
                    creationflags=creationflags,
                    close_fds=True,
                )
                _AIDA64_LAST_START_ERROR = ""
            except OSError as error:
                if getattr(error, "winerror", None) == 740:
                    # AIDA64 portable builds commonly request the highest available
                    # integrity level so they can load their hardware driver. Let
                    # Windows show the UAC consent dialog, while keeping AIDA64's UI
                    # itself hidden after consent.
                    try:
                        shell32 = ctypes.WinDLL("shell32", use_last_error=True)
                        shell32.ShellExecuteW.argtypes = (
                            ctypes.c_void_p,
                            ctypes.c_wchar_p,
                            ctypes.c_wchar_p,
                            ctypes.c_wchar_p,
                            ctypes.c_wchar_p,
                            ctypes.c_int,
                        )
                        shell32.ShellExecuteW.restype = ctypes.c_void_p
                        launch_result = shell32.ShellExecuteW(
                            None,
                            "runas",
                            str(executable),
                            "/SILENT",
                            str(executable.parent),
                            0,
                        )
                        if int(launch_result or 0) <= 32:
                            raise OSError(ctypes.get_last_error(), "AIDA64 elevation was cancelled or failed")
                        _AIDA64_LAST_START_ERROR = ""
                    except (OSError, ValueError) as elevated_error:
                        _AIDA64_LAST_START_ERROR = str(elevated_error)
                else:
                    _AIDA64_LAST_START_ERROR = str(error)
            except ValueError as error:
                _AIDA64_LAST_START_ERROR = str(error)

        result.update({
            "autoStartAttempted": True,
            "autoStartSucceeded": not _AIDA64_LAST_START_ERROR,
            "autoStartError": _AIDA64_LAST_START_ERROR,
            "executableFound": bool(_AIDA64_LAST_START_PATH),
        })
        return result


def detect_aida64() -> dict[str, Any]:
    processes = []
    for process in psutil.process_iter(["pid", "name", "exe"]):
        try:
            name = str(process.info.get("name") or "")
            if not name.lower().startswith("aida64"):
                continue
            processes.append({
                "pid": int(process.info.get("pid") or 0),
                "name": name,
                "exe": str(process.info.get("exe") or ""),
            })
        except (psutil.AccessDenied, psutil.NoSuchProcess):
            continue

    driver_running = False
    if platform.system().lower() == "windows":
        try:
            driver_running = psutil.win_service_get("AIDA64Driver").status() == "running"
        except (AttributeError, psutil.Error, OSError):
            driver_running = False
    return {
        "detected": bool(processes),
        "running": bool(processes),
        "processes": processes,
        "driverRunning": driver_running,
    }


def fallback_gpu_sensors(gpus: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    sensors = []
    for gpu in gpus or []:
        index = int(gpu.get("index") or 0) + 1
        name = str(gpu.get("name") or f"GPU {index}")
        power = float(gpu.get("powerDrawW") or 0)
        temperature = float(gpu.get("temperatureC") or 0)
        if power > 0:
            sensors.append({
                "id": f"PGPU{index}",
                "label": name,
                "type": "pwr",
                "category": "power",
                "group": "GPU",
                "value": f"{power:.2f}",
                "numericValue": power,
                "unit": "W",
                "source": "nvidia-smi",
            })
        if temperature > 0:
            sensors.append({
                "id": f"TGPU{index}",
                "label": name,
                "type": "temp",
                "category": "temperature",
                "group": "GPU",
                "value": f"{temperature:.1f}",
                "numericValue": temperature,
                "unit": "C",
                "source": "nvidia-smi",
            })
    return sensors


def first_sensor_value(sensors: list[dict[str, Any]], ids: tuple[str, ...], label: str = "") -> float | None:
    id_set = {item.upper() for item in ids}
    for sensor in sensors:
        if str(sensor.get("id") or "").upper() in id_set:
            value = sensor.get("numericValue")
            return float(value) if isinstance(value, (int, float)) else None
    if label:
        target = label.casefold()
        for sensor in sensors:
            if str(sensor.get("label") or "").casefold() == target:
                value = sensor.get("numericValue")
                return float(value) if isinstance(value, (int, float)) else None
    return None


def summarize_power_sensors(sensors: list[dict[str, Any]]) -> dict[str, Any]:
    power_sensors = [sensor for sensor in sensors if sensor.get("category") == "power"]
    cpu_package = first_sensor_value(power_sensors, ("PCPUPKG",), "CPU Package")
    if cpu_package is None:
        cpu_package = first_sensor_value(power_sensors, ("PCPU",), "CPU")

    gpu_board_values = []
    for sensor in power_sensors:
        sensor_id = str(sensor.get("id") or "").upper()
        value = sensor.get("numericValue")
        if re.fullmatch(r"PGPU\d+", sensor_id) and isinstance(value, (int, float)):
            gpu_board_values.append(float(value))
    gpu_board = sum(gpu_board_values) if gpu_board_values else None

    component_values = [value for value in (cpu_package, gpu_board) if value is not None]
    component_total = sum(component_values) if component_values else None
    return {
        "cpuPackageW": round(cpu_package, 3) if cpu_package is not None else None,
        "gpuBoardW": round(gpu_board, 3) if gpu_board is not None else None,
        "componentTotalW": round(component_total, 3) if component_total is not None else None,
        "componentTotalComplete": cpu_package is not None and gpu_board is not None,
        "powerSensorCount": len(power_sensors),
        "sensorCount": len(sensors),
        "componentTotalScope": "CPU package + discrete GPU board power; not wall power",
    }


def hardware_power_payload(gpus: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    aida64 = detect_aida64()
    aida64.update(auto_start_aida64(aida64))
    mapping_name, sensors = read_aida64_shared_memory()
    source = "aida64-shared-memory" if sensors else ""
    if not sensors:
        sensors = fallback_gpu_sensors(gpus)
        source = "nvidia-smi" if sensors else "system"

    aida64.update({
        "sharedMemoryAvailable": bool(mapping_name),
        "sharedMemoryName": mapping_name,
        "exportReady": bool(mapping_name and sensors and source == "aida64-shared-memory"),
    })
    return {
        "ok": True,
        "platform": platform.system(),
        "sampledAt": datetime.now().isoformat(timespec="seconds"),
        "source": source,
        "aida64": aida64,
        "summary": summarize_power_sensors(sensors),
        "sensors": sensors,
    }
