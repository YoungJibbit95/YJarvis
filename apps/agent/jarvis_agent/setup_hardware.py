"""Read-only setup boundary. No discovery at import, shell commands or Core wiring."""
from __future__ import annotations

import ctypes
import os
from pathlib import Path
import shutil
import sys

from .hardware_profile import Architecture, HardwareProfile, Platform


def _count(value: object, *, allow_zero: bool = False) -> int | None:
    if type(value) is int and (0 if allow_zero else 1) <= value <= 2**53 - 1:
        return value
    return None


def _platform() -> Platform:
    return {"win32": "windows", "darwin": "macos", "linux": "linux"}.get(sys.platform, "unknown")


def _architecture(host: Platform) -> Architecture:
    try:
        if host == "windows":
            kernel = ctypes.WinDLL("kernel32", use_last_error=True)
            current = kernel.GetCurrentProcess
            current.argtypes, current.restype = [], ctypes.c_void_p
            query = kernel.IsWow64Process2
            query.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint16), ctypes.POINTER(ctypes.c_uint16)]
            query.restype = ctypes.c_int
            process, native = ctypes.c_uint16(), ctypes.c_uint16()
            if not query(current(), ctypes.byref(process), ctypes.byref(native)):
                return "unknown"
            return {0x8664: "x86_64", 0xAA64: "arm64"}.get(native.value, "other")
        if host in ("linux", "macos"):
            machine = os.uname().machine.lower()
            if not machine:
                return "unknown"
            return {"x86_64": "x86_64", "amd64": "x86_64", "aarch64": "arm64", "arm64": "arm64"}.get(machine, "other")
    except (OSError, AttributeError, ValueError):
        pass
    return "unknown"


def _total_memory(host: Platform) -> int | None:
    try:
        if host == "windows":
            class MemoryStatus(ctypes.Structure):
                _fields_ = [("length", ctypes.c_uint32), ("load", ctypes.c_uint32)] + [
                    (name, ctypes.c_uint64) for name in
                    ("total_physical", "available_physical", "total_page_file", "available_page_file",
                     "total_virtual", "available_virtual", "available_extended_virtual")
                ]
            status = MemoryStatus()
            status.length = ctypes.sizeof(status)
            query = ctypes.WinDLL("kernel32", use_last_error=True).GlobalMemoryStatusEx
            query.argtypes, query.restype = [ctypes.POINTER(MemoryStatus)], ctypes.c_int
            return _count(status.total_physical) if query(ctypes.byref(status)) else None
        if host == "linux":
            pages, page_size = _count(os.sysconf("SC_PHYS_PAGES")), _count(os.sysconf("SC_PAGE_SIZE"))
            return _count(pages * page_size) if pages is not None and page_size is not None else None
        if host == "macos":
            # Fixed OS library: ctypes.util.find_library can invoke external commands.
            query = ctypes.CDLL("/usr/lib/libSystem.B.dylib").sysctlbyname
            query.argtypes = [ctypes.c_char_p, ctypes.c_void_p, ctypes.POINTER(ctypes.c_size_t), ctypes.c_void_p, ctypes.c_size_t]
            query.restype = ctypes.c_int
            memory = ctypes.c_uint64()
            size = ctypes.c_size_t(ctypes.sizeof(memory))
            if query(b"hw.memsize", ctypes.byref(memory), ctypes.byref(size), None, 0) == 0 and size.value == ctypes.sizeof(memory):
                return _count(memory.value)
    except (OSError, AttributeError, ValueError, OverflowError):
        pass
    return None


def _available_storage(runtime_dir: Path | None, host: Platform) -> int | None:
    try:
        # The process boundary supplies its already resolved app-data directory.
        # Never create a missing directory or silently measure a different ancestor.
        if runtime_dir is None or not runtime_dir.is_absolute() or str(runtime_dir).startswith(("\\\\", "//")):
            return None
        if host == "windows":
            query = ctypes.WinDLL("kernel32", use_last_error=True).GetDriveTypeW
            query.argtypes, query.restype = [ctypes.c_wchar_p], ctypes.c_uint32
            if query(runtime_dir.anchor) != 3:  # DRIVE_FIXED; skip mapped/network/removable drives.
                return None
        if not runtime_dir.is_dir():
            return None
        return _count(shutil.disk_usage(runtime_dir).free, allow_zero=True)
    except (OSError, AttributeError, ValueError, OverflowError):
        return None


def inspect_hardware(runtime_dir: Path | None) -> HardwareProfile:
    host = _platform()
    try:
        cpus = _count(os.cpu_count())
    except (OSError, NotImplementedError):
        cpus = None
    return HardwareProfile(
        platform=host, architecture=_architecture(host), logical_cpu_count=cpus,
        total_memory_bytes=_total_memory(host), available_storage_bytes=_available_storage(runtime_dir, host),
        storage_path_scope="app_runtime_directory",
    )
