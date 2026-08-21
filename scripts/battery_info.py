"""System battery information for ExpMon's Hardware Power view.

Queries the Windows battery through the native IOCTL interface
(\\\\.\\BATTERY — the same data source powercfg uses): cycle count,
designed / full-charged / current capacity in Wh, chemistry, health
percent and live charge/voltage/rate status. Desktop machines without a
battery simply report present=False and the UI hides the battery panel.

Pure ctypes; no third-party dependencies.
"""

import ctypes
import ctypes.wintypes
import platform
from typing import Any

GENERIC_READ = 0x80000000
GENERIC_WRITE = 0x40000000
FILE_SHARE_READ = 0x00000001
FILE_SHARE_WRITE = 0x00000002
OPEN_EXISTING = 3
INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value
ERROR_MORE_DATA = 234
ERROR_FILE_NOT_FOUND = 2
ERROR_INVALID_FUNCTION = 1

# CTL_CODE(FILE_DEVICE_BATTERY(0x29), Function, METHOD_BUFFERED(0), FILE_ANY_ACCESS(0))
IOCTL_BATTERY_QUERY_TAG = 0x29 << 16 | 0x10 << 2
IOCTL_BATTERY_QUERY_INFORMATION = 0x29 << 16 | 0x11 << 2
IOCTL_BATTERY_QUERY_STATUS = 0x29 << 16 | 0x12 << 2

BATTERY_INFORMATION_LEVEL = 0
BATTERY_MANUFACTURE_NAME = 6
BATTERY_DEVICE_NAME = 7
BATTERY_SERIAL_NUMBER = 8

BATTERY_CRITICAL = 0x00000001
BATTERY_POWER_ON_LINE = 0x00000002
BATTERY_DISCHARGING = 0x00000004
BATTERY_CHARGING = 0x00000008


class BATTERY_QUERY_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("BatteryTag", ctypes.c_uint32),
        ("InformationLevel", ctypes.c_uint32),
    ]


class BATTERY_WAIT_STATUS(ctypes.Structure):
    _fields_ = [
        ("BatteryTag", ctypes.c_uint32),
        ("Timeout", ctypes.c_uint32),
        ("PowerState", ctypes.c_uint32),
        ("Capacity", ctypes.c_uint32),
        ("Voltage", ctypes.c_uint32),
        ("Rate", ctypes.c_int32),
    ]


class BATTERY_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("Capabilities", ctypes.c_uint32),
        ("Technology", ctypes.c_uint8),
        ("Reserved", ctypes.c_uint8 * 3),
        ("Chemistry", ctypes.c_char * 4),
        ("DesignedCapacity", ctypes.c_uint32),
        ("FullChargedCapacity", ctypes.c_uint32),
        ("DefaultAlert1", ctypes.c_uint32),
        ("DefaultAlert2", ctypes.c_uint32),
        ("CriticalBias", ctypes.c_uint32),
        ("CycleCount", ctypes.c_uint32),
    ]


def _no_battery(message: str = "") -> dict[str, Any]:
    payload: dict[str, Any] = {"present": False, "supported": False}
    if message:
        payload["error"] = message
    return payload


def _query_string(kernel32, handle, tag: int, level: int) -> str:
    query = BATTERY_QUERY_INFORMATION(tag, level)
    size = 128
    for _ in range(6):  # bounded retry loop for ERROR_MORE_DATA
        buffer = ctypes.create_string_buffer(size)
        returned = ctypes.wintypes.DWORD(0)
        ok = kernel32.DeviceIoControl(
            handle,
            IOCTL_BATTERY_QUERY_INFORMATION,
            ctypes.byref(query),
            ctypes.sizeof(query),
            buffer,
            size,
            ctypes.byref(returned),
            None,
        )
        if ok:
            raw = buffer.raw[: returned.value]
            text = raw.decode("utf-16-le", errors="ignore").split("\x00", 1)[0]
            return text.strip()
        error = ctypes.get_last_error()
        if error == ERROR_MORE_DATA and returned.value > size:
            size = int(returned.value) * 2
            continue
        return ""
    return ""


def battery_payload() -> dict[str, Any]:
    """Returns battery info for the power endpoint; never raises."""
    if platform.system().lower() != "windows":
        return _no_battery("not windows")

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateFileW.argtypes = (
        ctypes.c_wchar_p, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_void_p,
        ctypes.c_uint32, ctypes.c_uint32, ctypes.c_void_p,
    )
    kernel32.CreateFileW.restype = ctypes.c_void_p
    kernel32.DeviceIoControl.argtypes = (
        ctypes.c_void_p, ctypes.c_uint32, ctypes.c_void_p, ctypes.c_uint32,
        ctypes.c_void_p, ctypes.c_uint32, ctypes.POINTER(ctypes.wintypes.DWORD), ctypes.c_void_p,
    )
    kernel32.DeviceIoControl.restype = ctypes.c_int
    kernel32.CloseHandle.argtypes = (ctypes.c_void_p,)

    handle = kernel32.CreateFileW(
        "\\\\.\\BATTERY", GENERIC_READ | GENERIC_WRITE,
        FILE_SHARE_READ | FILE_SHARE_WRITE, None, OPEN_EXISTING, 0, None,
    )
    if handle == INVALID_HANDLE_VALUE or not handle:
        error = ctypes.get_last_error()
        if error == ERROR_FILE_NOT_FOUND:
            return _no_battery("no battery device")
        return _no_battery(f"open failed: {error}")

    try:
        tag_buffer = ctypes.c_uint32(0)
        returned = ctypes.wintypes.DWORD(0)
        ok = kernel32.DeviceIoControl(
            handle, IOCTL_BATTERY_QUERY_TAG,
            None, 0, ctypes.byref(tag_buffer), ctypes.sizeof(tag_buffer),
            ctypes.byref(returned), None,
        )
        if not ok:
            return _no_battery(f"query tag failed: {ctypes.get_last_error()}")
        tag = tag_buffer.value

        info = BATTERY_INFORMATION()
        ok = kernel32.DeviceIoControl(
            handle, IOCTL_BATTERY_QUERY_INFORMATION,
            ctypes.byref(BATTERY_QUERY_INFORMATION(tag, BATTERY_INFORMATION_LEVEL)),
            ctypes.sizeof(BATTERY_QUERY_INFORMATION),
            ctypes.byref(info), ctypes.sizeof(info), ctypes.byref(returned), None,
        )
        if not ok:
            return _no_battery(f"query information failed: {ctypes.get_last_error()}")

        status = BATTERY_WAIT_STATUS(tag, 0, 0, 0, 0, 0)
        ok = kernel32.DeviceIoControl(
            handle, IOCTL_BATTERY_QUERY_STATUS,
            ctypes.byref(status), ctypes.sizeof(status),
            ctypes.byref(status), ctypes.sizeof(status), ctypes.byref(returned), None,
        )
        status_flags = status.PowerState if ok else 0
        capacity_mwh = status.Capacity if ok else None
        voltage_mv = status.Voltage if ok else None
        rate_mw = status.Rate if ok else None

        designed_mwh = info.DesignedCapacity or 0
        full_mwh = info.FullChargedCapacity or 0

        if status_flags & BATTERY_CHARGING:
            charge_status = "charging"
        elif status_flags & BATTERY_DISCHARGING:
            charge_status = "discharging"
        elif status_flags & BATTERY_CRITICAL:
            charge_status = "critical"
        elif status_flags & BATTERY_POWER_ON_LINE:
            charge_status = "full"
        else:
            charge_status = "idle"

        payload: dict[str, Any] = {
            "present": True,
            "supported": True,
            "name": _query_string(kernel32, handle, tag, BATTERY_DEVICE_NAME),
            "manufacturer": _query_string(kernel32, handle, tag, BATTERY_MANUFACTURE_NAME),
            "serialNumber": _query_string(kernel32, handle, tag, BATTERY_SERIAL_NUMBER),
            "chemistry": info.Chemistry.decode("ascii", errors="ignore").strip("\x00 "),
            "designedCapacityWh": round(designed_mwh / 1000.0, 2) if designed_mwh else None,
            "fullChargeCapacityWh": round(full_mwh / 1000.0, 2) if full_mwh else None,
            "currentCapacityWh": round(capacity_mwh / 1000.0, 2) if capacity_mwh is not None else None,
            "cycleCount": int(info.CycleCount) if info.CycleCount else 0,
            "healthPercent": round(full_mwh * 100.0 / designed_mwh, 1) if designed_mwh else None,
            "chargePercent": round(capacity_mwh * 100.0 / full_mwh, 1)
            if capacity_mwh is not None and full_mwh else None,
            "status": charge_status,
            "voltageV": round(voltage_mv / 1000.0, 3) if voltage_mv is not None else None,
            # Positive = charging, negative = discharging (Windows convention).
            "rateW": round(rate_mw / 1000.0, 3) if rate_mw is not None else None,
        }
        return payload
    finally:
        kernel32.CloseHandle(handle)


if __name__ == "__main__":
    import json
    print(json.dumps(battery_payload(), indent=2))
