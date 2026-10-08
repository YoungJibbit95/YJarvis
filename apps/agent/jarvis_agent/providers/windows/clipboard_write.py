"""Immediate CF_UNICODETEXT transfer using a short-lived, owned message window."""

import asyncio
import sys
from functools import cache

from pydantic import BaseModel

from ...domain.action import CapabilityName
from ...domain.tool_inputs import ClipboardWriteInput
from ...domain.tool_outputs import NoDataOutput


@cache
def _native_api():
    # Lazy process-lifetime bindings; no DLL loading during import/registration.
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.WinDLL("user32.dll", use_last_error=True, winmode=0x800)
    kernel32 = ctypes.WinDLL("kernel32.dll", use_last_error=True, winmode=0x800)
    # System32 only; preserve pointer-sized HWND/HGLOBAL/results on x64.
    for function, arguments, result in (
        (user32.CreateWindowExW, [wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR,
                                 wintypes.DWORD, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                 ctypes.c_int, wintypes.HWND, wintypes.HMENU,
                                 wintypes.HINSTANCE, ctypes.c_void_p], wintypes.HWND),
        (user32.DestroyWindow, [wintypes.HWND], wintypes.BOOL),
        (user32.OpenClipboard, [wintypes.HWND], wintypes.BOOL),
        (user32.EmptyClipboard, [], wintypes.BOOL),
        (user32.SetClipboardData, [wintypes.UINT, wintypes.HANDLE], wintypes.HANDLE),
        (user32.CloseClipboard, [], wintypes.BOOL),
        (kernel32.GlobalAlloc, [wintypes.UINT, ctypes.c_size_t], wintypes.HGLOBAL),
        (kernel32.GlobalLock, [wintypes.HGLOBAL], ctypes.c_void_p),
        (kernel32.GlobalUnlock, [wintypes.HGLOBAL], wintypes.BOOL),
        (kernel32.GlobalFree, [wintypes.HGLOBAL], wintypes.HGLOBAL),
    ):
        function.argtypes = arguments
        function.restype = result
    return ctypes, user32, kernel32


def _write_clipboard_text(text: str) -> None:
    # Encoding failure happens before any native resource or clipboard mutation.
    data = text.encode("utf-16-le") + b"\x00\x00"
    ctypes, user32, kernel32 = _native_api()
    ctypes.set_last_error(0)
    # Predefined system class, HWND_MESSAGE (-3), no visible style or foreign HWND.
    owner = user32.CreateWindowExW(0, "STATIC", None, 0, 0, 0, 0, 0, -3, None, None, None)
    if not owner:
        raise ctypes.WinError(ctypes.get_last_error(), "CreateWindowExW failed")
    try:
        ctypes.set_last_error(0)
        if not user32.OpenClipboard(owner):
            raise ctypes.WinError(ctypes.get_last_error(), "OpenClipboard failed")
        try:
            ctypes.set_last_error(0)
            if not user32.EmptyClipboard():
                raise ctypes.WinError(ctypes.get_last_error(), "EmptyClipboard failed")
            # Not transactional: previous contents are already gone from here on.
            ctypes.set_last_error(0)
            handle = kernel32.GlobalAlloc(0x0002, len(data))  # GMEM_MOVEABLE
            if not handle:
                raise ctypes.WinError(ctypes.get_last_error(), "GlobalAlloc failed")
            transferred = False
            try:
                ctypes.set_last_error(0)
                pointer = kernel32.GlobalLock(handle)
                if not pointer:
                    raise ctypes.WinError(ctypes.get_last_error(), "GlobalLock failed")
                try:
                    ctypes.memmove(pointer, data, len(data))
                finally:
                    ctypes.set_last_error(0)
                    still_locked = kernel32.GlobalUnlock(handle)
                    error = ctypes.get_last_error()
                    if not still_locked and error:
                        raise ctypes.WinError(error, "GlobalUnlock failed")
                    if still_locked:
                        # Our fresh allocation has only our one lock. Never hand
                        # Windows an allocation that is known to remain locked.
                        raise OSError("GlobalUnlock left the new allocation locked")
                ctypes.set_last_error(0)
                if not user32.SetClipboardData(13, handle):  # CF_UNICODETEXT
                    raise ctypes.WinError(ctypes.get_last_error(), "SetClipboardData failed")
                transferred = True  # Windows now owns this HGLOBAL; never free it.
            finally:
                if not transferred:
                    ctypes.set_last_error(0)
                    if kernel32.GlobalFree(handle):  # NULL means successful free.
                        raise ctypes.WinError(ctypes.get_last_error(), "GlobalFree failed")
        finally:
            ctypes.set_last_error(0)
            if not user32.CloseClipboard():
                raise ctypes.WinError(ctypes.get_last_error(), "CloseClipboard failed")
    finally:
        ctypes.set_last_error(0)
        if not user32.DestroyWindow(owner):
            raise ctypes.WinError(ctypes.get_last_error(), "DestroyWindow failed")


class WindowsClipboardWriteProvider:
    """Explicit clipboard.write provider; no policy, retry, discovery or wiring."""

    async def execute(self, capability: CapabilityName, input_data: BaseModel) -> NoDataOutput:
        if capability != "clipboard.write":
            raise KeyError(capability)
        if sys.platform != "win32":
            raise OSError("Windows clipboard writing requires a Windows host")
        payload = ClipboardWriteInput.model_validate(input_data)
        await asyncio.to_thread(_write_clipboard_text, payload.text)
        return NoDataOutput()
