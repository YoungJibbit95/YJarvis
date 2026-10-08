"""On-demand Windows DXGI descriptors; no devices, contexts or models are created."""
from __future__ import annotations

import ctypes as ct
import sys

from .accelerator_profile import AcceleratorAdapter, AcceleratorProfile

_HRESULT = ct.c_int32
_UINT = ct.c_uint32
_NOT_FOUND = 0x887A0002
_MAX_ADAPTERS = 64


class _GUID(ct.Structure):
    _fields_ = [("data1", _UINT), ("data2", ct.c_uint16), ("data3", ct.c_uint16),
                ("data4", ct.c_ubyte * 8)]


class _LUID(ct.Structure):
    _fields_ = [("low", _UINT), ("high", ct.c_int32)]


class _AdapterDesc1(ct.Structure):
    # Fixed-width WCHAR/UINT/LONG also keep the mocked ABI correct on Linux.
    _fields_ = [("description", ct.c_uint16 * 128), ("vendor_id", _UINT),
                ("device_id", _UINT), ("subsystem_id", _UINT), ("revision", _UINT),
                ("dedicated_video_memory", ct.c_size_t),
                ("dedicated_system_memory", ct.c_size_t),
                ("shared_system_memory", ct.c_size_t), ("luid", _LUID), ("flags", _UINT)]


def _method(pointer: ct.c_void_p, slot: int, result, *arguments):
    address = ct.cast(pointer, ct.POINTER(ct.POINTER(ct.c_void_p))).contents[slot]
    if not address:
        raise OSError("Missing DXGI method")
    return ct.WINFUNCTYPE(result, ct.c_void_p, *arguments)(address)


def _release(pointer: ct.c_void_p) -> None:
    _method(pointer, 2, _UINT)(pointer)


def _normalize(desc: _AdapterDesc1) -> AcceleratorAdapter:
    units = list(desc.description)
    if 0 not in units:
        raise ValueError("Unterminated adapter description")
    name = bytes(desc.description)[:units.index(0) * 2].decode("utf-16-le").strip()
    # DXGI reports these byte counts. Zero is a measured value; values outside
    # the JSON/JS exact-integer range are unknown, never rounded or estimated.
    def memory(value: int) -> int | None:
        return value if 0 <= value <= 2**53 - 1 else None

    return AcceleratorAdapter(
        display_name=name,
        dedicated_video_memory_bytes=memory(desc.dedicated_video_memory),
        shared_system_memory_bytes=memory(desc.shared_system_memory),
        classification={0: "hardware", 2: "software"}.get(desc.flags, "unknown"),
    )


def _windows_adapters() -> tuple[AcceleratorAdapter, ...]:
    # Fixed system DLL, restricted to System32 (LOAD_LIBRARY_SEARCH_SYSTEM32).
    library = ct.WinDLL("dxgi.dll", winmode=0x00000800)
    create = library.CreateDXGIFactory1
    create.argtypes = [ct.POINTER(_GUID), ct.POINTER(ct.c_void_p)]
    create.restype = _HRESULT
    iid = _GUID(0x770AAE78, 0xF26F, 0x4DBA,
                (ct.c_ubyte * 8)(0xA8, 0x29, 0x25, 0x3C, 0x83, 0xD1, 0xB3, 0x87))
    factory = ct.c_void_p()
    if create(ct.byref(iid), ct.byref(factory)) != 0 or not factory.value:
        raise OSError("DXGI factory unavailable")
    try:
        # SDK vtable slots include IUnknown and inherited IDXGI methods.
        enumerate_adapter = _method(factory, 12, _HRESULT, _UINT, ct.POINTER(ct.c_void_p))
        adapters = []
        for index in range(_MAX_ADAPTERS + 1):
            adapter = ct.c_void_p()
            result = enumerate_adapter(factory, index, ct.byref(adapter))
            if result & 0xFFFFFFFF == _NOT_FOUND:
                return tuple(adapters)
            if result != 0 or not adapter.value:
                raise OSError("DXGI enumeration failed")
            try:
                if index == _MAX_ADAPTERS:
                    raise OSError("DXGI enumeration exceeds bounded profile")
                desc = _AdapterDesc1()
                if _method(adapter, 10, _HRESULT, ct.POINTER(_AdapterDesc1))(adapter, ct.byref(desc)) != 0:
                    raise OSError("DXGI descriptor unavailable")
                adapters.append(_normalize(desc))
            finally:
                _release(adapter)
    finally:
        _release(factory)
    raise OSError("DXGI enumeration did not terminate")


def inspect_accelerators() -> AcceleratorProfile:
    if sys.platform != "win32":
        return AcceleratorProfile(status="unsupported", adapters=())
    try:
        return AcceleratorProfile(status="available", adapters=_windows_adapters())
    except (OSError, AttributeError, ValueError):
        # No partial list or raw driver errors; a fresh GET can retry enumeration.
        return AcceleratorProfile(status="unknown", adapters=())
