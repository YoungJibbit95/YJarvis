"""Read-only Start Menu shortcut discovery; no launch, Domain or runtime coupling."""

import os
import stat
import sys
from dataclasses import dataclass
from functools import cache
from pathlib import Path, PureWindowsPath
from uuid import UUID


@dataclass(frozen=True)
class WindowsAppTarget:
    """Internal discovery result, not a persisted identity or launch authorization."""

    display_name: str
    shortcut_path: Path


class WindowsAppDiscoveryError(OSError):
    """The trusted discovery boundary could not be read completely."""


class WindowsAppNotFoundError(LookupError):
    pass


class WindowsAppAmbiguousError(LookupError):
    def __init__(self, display_name: str, candidates: tuple[WindowsAppTarget, ...]):
        self.display_name = display_name
        self.candidates = candidates  # Internal diagnostics only; no paths in message.
        super().__init__(f"Ambiguous Start Menu name: {display_name!r} ({len(candidates)} shortcuts)")


@cache
def _native_api():
    import ctypes
    from ctypes import wintypes

    class GUID(ctypes.Structure):
        _fields_ = [("Data1", ctypes.c_uint32), ("Data2", ctypes.c_uint16),
                    ("Data3", ctypes.c_uint16), ("Data4", ctypes.c_ubyte * 8)]

    shell32 = ctypes.WinDLL("shell32.dll", winmode=0x800)  # System32 only.
    ole32 = ctypes.WinDLL("ole32.dll", winmode=0x800)
    kernel32 = ctypes.WinDLL("kernel32.dll", winmode=0x800)
    shell32.SHGetKnownFolderPath.argtypes = [ctypes.POINTER(GUID), wintypes.DWORD,
                                           wintypes.HANDLE, ctypes.POINTER(ctypes.c_void_p)]
    shell32.SHGetKnownFolderPath.restype = ctypes.c_int32  # Signed HRESULT, not LastError.
    ole32.CoTaskMemFree.argtypes = [ctypes.c_void_p]
    ole32.CoTaskMemFree.restype = None
    kernel32.GetDriveTypeW.argtypes = [wintypes.LPCWSTR]
    kernel32.GetDriveTypeW.restype = wintypes.UINT
    return ctypes, GUID, shell32, ole32, kernel32


def _program_folders() -> tuple[Path, ...]:
    ctypes, GUID, shell32, ole32, kernel32 = _native_api()
    folders = []
    for folder_id in (
        "A77F5D77-2E2B-44C3-A6A2-ABA601054A51",  # FOLDERID_Programs (current user)
        "0139D44E-6AFE-49F2-8690-3DAFCAE6FFB8",  # FOLDERID_CommonPrograms
    ):
        guid = GUID.from_buffer_copy(UUID(folder_id).bytes_le)
        pointer = ctypes.c_void_p()
        try:
            # No KF_FLAG_CREATE, environment fallback, or alternate user token.
            result = shell32.SHGetKnownFolderPath(ctypes.byref(guid), 0, None, ctypes.byref(pointer))
            if result != 0:
                raise WindowsAppDiscoveryError(f"SHGetKnownFolderPath failed: 0x{result & 0xffffffff:08X}")
            if not pointer.value:
                raise WindowsAppDiscoveryError("SHGetKnownFolderPath returned no path")
            value = ctypes.wstring_at(pointer)
        finally:
            # Required even on failed HRESULTs; freeing NULL is explicitly allowed.
            ole32.CoTaskMemFree(pointer)
        path = PureWindowsPath(value)
        if (not path.is_absolute() or len(path.drive) != 2 or path.drive[1] != ":"
                or ".." in path.parts):
            raise WindowsAppDiscoveryError("Known Folder is not an absolute local drive path")
        # Reject UNC/device paths above, mapped network drives and unknown drives here.
        if kernel32.GetDriveTypeW(path.anchor) not in {2, 3, 5, 6}:
            raise WindowsAppDiscoveryError("Known Folder drive is not local")
        folders.append(Path(value))
    return tuple(folders)


def _is_link(info: os.stat_result) -> bool:
    return stat.S_ISLNK(info.st_mode) or bool(
        getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT
    )


def _plain_directory(path: Path) -> bool:
    info = path.lstat()
    return stat.S_ISDIR(info.st_mode) and not _is_link(info)


class WindowsAppResolver:
    """Fresh, deterministic local discovery on each call; never opens a shortcut."""

    def inventory(self) -> tuple[WindowsAppTarget, ...]:
        if sys.platform != "win32":
            raise OSError("Windows application resolution requires a Windows host")
        targets = {}
        # Deduplicate identical roots/paths, not names or distinct case-sensitive files.
        for root_name in sorted({str(path) for path in _program_folders()}):
            root = Path(root_name)
            # Check ancestors from the drive down, so a redirected parent is not scanned.
            if not all(_plain_directory(path) for path in (*reversed(root.parents), root)):
                continue
            pending = [root]
            while pending:
                directory = pending.pop()
                if not _plain_directory(directory):
                    continue
                with os.scandir(directory) as entries:
                    ordered = sorted(entries, key=lambda entry: (entry.name.casefold(), entry.name))
                for entry in ordered:
                    info = entry.stat(follow_symlinks=False)
                    if _is_link(info):
                        continue
                    path = Path(entry.path)
                    if stat.S_ISDIR(info.st_mode):
                        pending.append(path)
                    elif stat.S_ISREG(info.st_mode) and path.suffix.casefold() == ".lnk":
                        targets[str(path)] = WindowsAppTarget(path.stem, path)
        return tuple(sorted(targets.values(), key=lambda target: (
            target.display_name.casefold(), target.display_name,
            str(target.shortcut_path).casefold(), str(target.shortcut_path),
        )))

    def resolve(self, display_name: str) -> WindowsAppTarget:
        if not isinstance(display_name, str):
            raise TypeError("display_name must be a string")
        # No stripping, alias conversion, fuzzy matching or input-to-path conversion.
        matches = tuple(target for target in self.inventory()
                        if target.display_name.casefold() == display_name.casefold())
        if not matches:
            raise WindowsAppNotFoundError(f"No Start Menu shortcut for {display_name!r}")
        if len(matches) > 1:
            raise WindowsAppAmbiguousError(display_name, matches)
        return matches[0]
