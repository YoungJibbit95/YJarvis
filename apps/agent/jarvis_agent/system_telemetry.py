from __future__ import annotations

import os
import platform
import re
import subprocess
from datetime import datetime, timezone
from typing import Any


_TEMP_NUMBER_REGEX = re.compile(r"(-?\d+(?:\.\d+)?)")
_ISTATS_TEMP_REGEX = re.compile(r"cpu\s+temp(?:erature)?\s*:\s*(-?\d+(?:\.\d+)?)", re.IGNORECASE)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _run_command(command: list[str], timeout_seconds: float = 1.2) -> str:
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
    except Exception:
        return ""

    if completed.returncode != 0:
        return ""
    return (completed.stdout or "").strip()


def _safe_float(value: str | None) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except Exception:
        return None


def _cpu_temp_from_osx_cpu_temp() -> float | None:
    output = _run_command(["osx-cpu-temp"])
    if not output:
        return None
    match = _TEMP_NUMBER_REGEX.search(output)
    return _safe_float(match.group(1) if match else None)


def _cpu_temp_from_istats() -> float | None:
    output = _run_command(["istats", "cpu", "temp", "--no-graphs"])
    if not output:
        return None
    match = _ISTATS_TEMP_REGEX.search(output)
    if match:
        return _safe_float(match.group(1))
    fallback = _TEMP_NUMBER_REGEX.search(output)
    return _safe_float(fallback.group(1) if fallback else None)


def _cpu_temp_from_linux_thermal_zone() -> float | None:
    candidates = [
        "/sys/class/thermal/thermal_zone0/temp",
        "/sys/class/hwmon/hwmon0/temp1_input",
    ]
    for candidate in candidates:
        try:
            with open(candidate, "r", encoding="utf-8") as file:
                raw = file.read().strip()
        except Exception:
            continue
        value = _safe_float(raw)
        if value is None:
            continue
        # Linux often stores millidegree Celsius.
        if value > 1000:
            value = value / 1000.0
        if 1 <= value <= 130:
            return value
    return None


def _cpu_utilization_from_loadavg() -> float | None:
    cpu_count = os.cpu_count() or 0
    if cpu_count <= 0:
        return None
    try:
        load_1m = os.getloadavg()[0]
    except Exception:
        return None
    utilization = (float(load_1m) / float(cpu_count)) * 100.0
    return max(0.0, min(100.0, utilization))


def _estimated_temp_from_utilization(utilization_percent: float | None) -> float | None:
    if utilization_percent is None:
        return None
    # Conservative estimate to still provide a useful "warm/cool" signal
    # when no hardware sensor is readable without elevated privileges.
    base_temp = 36.0
    dynamic = utilization_percent * 0.37
    estimated = base_temp + dynamic
    return max(30.0, min(92.0, estimated))


def collect_system_telemetry() -> dict[str, Any]:
    system_name = platform.system().lower()
    cpu_temp_c: float | None = None
    source = "unavailable"
    estimated = False

    if system_name == "darwin":
        cpu_temp_c = _cpu_temp_from_osx_cpu_temp()
        if cpu_temp_c is not None:
            source = "osx-cpu-temp"
        else:
            cpu_temp_c = _cpu_temp_from_istats()
            if cpu_temp_c is not None:
                source = "istats"
    elif system_name == "linux":
        cpu_temp_c = _cpu_temp_from_linux_thermal_zone()
        if cpu_temp_c is not None:
            source = "thermal_zone"

    cpu_utilization_percent = _cpu_utilization_from_loadavg()

    if cpu_temp_c is None:
        cpu_temp_c = _estimated_temp_from_utilization(cpu_utilization_percent)
        if cpu_temp_c is not None:
            source = "load_estimate"
            estimated = True

    if cpu_temp_c is not None:
        cpu_temp_c = round(cpu_temp_c, 1)
    if cpu_utilization_percent is not None:
        cpu_utilization_percent = round(cpu_utilization_percent, 1)

    return {
        "cpu_temperature_c": cpu_temp_c,
        "cpu_temperature_source": source,
        "cpu_temperature_estimated": estimated,
        "cpu_utilization_percent": cpu_utilization_percent,
        "collected_at": _utc_now_iso(),
    }
