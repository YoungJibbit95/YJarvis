"""Read only CF_UNICODETEXT through a lazy, synchronous Win32 boundary."""

import asyncio
import sys
from functools import cache

from pydantic import BaseModel

from ...domain.action import CapabilityName
from ...domain.tool_inputs import ClipboardReadInput
from ...domain.tool_outputs import ClipboardReadOutput


@cache
def _native_api():
    # Keep DLL loading and all native access out of import/instantiation.
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.WinDLL("user32.dll", use_last_error=True, winmode=0x800)
    kernel32 = ctypes.WinDLL("kernel32.dll", use_last_error=True, winmode=0x800)
    # LOAD_LIBRARY_SEARCH_SYSTEM32; explicit pointer-sized handles/results on x64.
    for function, arguments, result in (
        (user32.OpenClipboard, [wintypes.HWND], wintypes.BOOL),
        (user32.IsClipboardFormatAvailable, [wintypes.UINT], wintypes.BOOL),
        (user32.GetClipboardData, [wintypes.UINT], wintypes.HANDLE),
        (user32.CloseClipboard, [], wintypes.BOOL),
        (kernel32.GlobalLock, [wintypes.HGLOBAL], ctypes.c_void_p),
        (kernel32.GlobalSize, [wintypes.HGLOBAL], ctypes.c_size_t),
        (kernel32.GlobalUnlock, [wintypes.HGLOBAL], wintypes.BOOL),
    ):
        function.argtypes = arguments
        function.restype = result
    return ctypes, user32, kernel32


def _read_clipboard_text() -> str:
    # Retain lazy DLL bindings for process lifetime, not new loads on every read.
    ctypes, user32, kernel32 = _native_api()

    ctypes.set_last_error(0)
    if not user32.OpenClipboard(None):
        raise ctypes.WinError(ctypes.get_last_error(), "OpenClipboard failed")
    try:
        ctypes.set_last_error(0)
        if not user32.IsClipboardFormatAvailable(13):  # CF_UNICODETEXT only
            error = ctypes.get_last_error()
            if error:
                raise ctypes.WinError(error, "IsClipboardFormatAvailable failed")
            return ""
        ctypes.set_last_error(0)
        handle = user32.GetClipboardData(13)
        if not handle:
            raise ctypes.WinError(ctypes.get_last_error(), "GetClipboardData failed")
        ctypes.set_last_error(0)
        pointer = kernel32.GlobalLock(handle)
        if not pointer:
            raise ctypes.WinError(ctypes.get_last_error(), "GlobalLock failed")
        try:
            ctypes.set_last_error(0)
            size = kernel32.GlobalSize(handle)
            if not size:
                raise ctypes.WinError(ctypes.get_last_error(), "GlobalSize failed")
            # Clipboard memory is untrusted. Never scan past its allocation.
            data = ctypes.string_at(pointer, size)
        finally:
            ctypes.set_last_error(0)
            if not kernel32.GlobalUnlock(handle):
                error = ctypes.get_last_error()
                # Zero also means a successful final unlock (NO_ERROR).
                if error:
                    raise ctypes.WinError(error, "GlobalUnlock failed")
    finally:
        ctypes.set_last_error(0)
        if not user32.CloseClipboard():
            raise ctypes.WinError(ctypes.get_last_error(), "CloseClipboard failed")

    # Decode only up to the first aligned UTF-16 NUL, preserving all text.
    # Allocation padding after the terminator is not part of CF_UNICODETEXT.
    for end in range(0, len(data) - 1, 2):
        if data[end:end + 2] == b"\x00\x00":
            return data[:end].decode("utf-16-le")
    raise ValueError("CF_UNICODETEXT is not NUL-terminated within its allocation")


class WindowsClipboardReadProvider:
    """Explicit ToolProvider for clipboard.read; no discovery or fallback."""

    async def execute(self, capability: CapabilityName, input_data: BaseModel) -> ClipboardReadOutput:
        if capability != "clipboard.read":
            raise KeyError(capability)
        if sys.platform != "win32":
            raise OSError("Windows clipboard reading requires a Windows host")
        ClipboardReadInput.model_validate(input_data)
        text = await asyncio.to_thread(_read_clipboard_text)
        return ClipboardReadOutput(text=text)
