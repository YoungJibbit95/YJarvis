"""Only temporary inventories and controlled native allocations are used in CI."""

import ctypes
import os
import stat
import subprocess
import sys
import textwrap
from contextlib import contextmanager
from dataclasses import FrozenInstanceError
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, call
from uuid import UUID

import pytest

from jarvis_agent.domain.capability_catalog import CAPABILITY_CATALOG
from jarvis_agent.provider_registry import CapabilityProviderRegistry, CapabilityUnavailableError
from jarvis_agent.providers.windows import app_resolver
from jarvis_agent.providers.windows.app_resolver import (
    WindowsAppAmbiguousError,
    WindowsAppDiscoveryError,
    WindowsAppNotFoundError,
    WindowsAppResolver,
    WindowsAppTarget,
)


@pytest.fixture(autouse=True)
def native(monkeypatch):
    app_resolver._native_api.cache_clear()
    state = SimpleNamespace(paths=["R:\\Menü\\Programs", "S:\\Shared\\Programs"], calls=[],
                            allocations=[], freed=[], results=[0, 0], null=set(), copy_error=None,
                            call_error=None, free_error=None, drive_type=3)

    def known_folder(guid, flags, token, output):
        index = len(state.calls)
        state.calls.append((str(UUID(bytes_le=ctypes.string_at(guid, 16))), flags, token))
        if index not in state.null:
            buffer = ctypes.create_unicode_buffer(state.paths[index])
            state.allocations.append(buffer)  # Own buffers; never free real COM memory.
            ctypes.cast(output, ctypes.POINTER(ctypes.c_void_p))[0] = ctypes.addressof(buffer)
        if state.call_error:
            raise state.call_error
        return state.results[index]

    def free(pointer):
        state.freed.append(pointer.value)
        if state.free_error:
            raise state.free_error

    state.shell32 = SimpleNamespace(SHGetKnownFolderPath=Mock(side_effect=known_folder))
    state.ole32 = SimpleNamespace(CoTaskMemFree=Mock(side_effect=free))
    state.kernel32 = SimpleNamespace(GetDriveTypeW=Mock(side_effect=lambda path: state.drive_type))
    libraries = {"shell32.dll": state.shell32, "ole32.dll": state.ole32, "kernel32.dll": state.kernel32}
    state.loader = Mock(side_effect=lambda name, **kwargs: libraries[name])
    monkeypatch.setattr(ctypes, "WinDLL", state.loader, raising=False)
    real_copy = ctypes.wstring_at

    def copy(pointer):
        assert pointer.value not in state.freed
        if state.copy_error:
            raise state.copy_error
        return real_copy(pointer)

    monkeypatch.setattr(ctypes, "wstring_at", copy)
    yield state
    app_resolver._native_api.cache_clear()


@pytest.fixture
def inventory(monkeypatch, tmp_path, native):
    user, common = tmp_path / "Programs", tmp_path / "CommonPrograms"
    user.mkdir()
    common.mkdir()
    monkeypatch.setattr(app_resolver, "sys", SimpleNamespace(platform="win32"))
    folders = Mock(return_value=(user, common))
    monkeypatch.setattr(app_resolver, "_program_folders", folders)
    # Execution cannot escape into shell/process APIs even during fixture scans.
    forbidden = Mock(side_effect=AssertionError("Unexpected launch"))
    monkeypatch.setattr(os, "system", forbidden)
    monkeypatch.setattr(os, "startfile", forbidden, raising=False)
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    return SimpleNamespace(user=user, common=common, folders=folders, native=native)


def shortcut(root, name):
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"fixture, not parsed or launched")
    return path


def test_known_folders_copy_both_paths_and_free_each_allocation(native):
    assert app_resolver._program_folders() == tuple(Path(path) for path in native.paths)
    assert native.calls == [
        ("a77f5d77-2e2b-44c3-a6a2-aba601054a51", 0, None),
        ("0139d44e-6afe-49f2-8690-3dafcae6ffb8", 0, None),
    ]
    assert native.freed == [ctypes.addressof(buffer) for buffer in native.allocations]
    assert native.kernel32.GetDriveTypeW.call_args_list == [call("R:\\"), call("S:\\")]
    assert native.loader.call_args_list == [call(name, winmode=0x800) for name in (
        "shell32.dll", "ole32.dll", "kernel32.dll")]
    assert app_resolver._native_api() is app_resolver._native_api()
    _, guid, _, _, _ = app_resolver._native_api()
    assert ctypes.sizeof(guid) == 16 and ctypes.alignment(guid) == 4
    assert native.shell32.SHGetKnownFolderPath.restype is ctypes.c_int32
    assert native.shell32.SHGetKnownFolderPath.argtypes == [ctypes.POINTER(guid), ctypes.wintypes.DWORD,
                                                          ctypes.wintypes.HANDLE, ctypes.POINTER(ctypes.c_void_p)]
    assert native.ole32.CoTaskMemFree.argtypes == [ctypes.c_void_p]
    assert native.ole32.CoTaskMemFree.restype is None
    assert native.kernel32.GetDriveTypeW.argtypes == [ctypes.wintypes.LPCWSTR]
    assert native.kernel32.GetDriveTypeW.restype is ctypes.wintypes.UINT


@pytest.mark.parametrize("index", [0, 1])
@pytest.mark.parametrize("allocate", [False, True])
def test_hresult_failure_frees_even_failure_output_and_returns_no_partial_inventory(native, index, allocate):
    native.results[index] = ctypes.c_int32(0x80070005).value
    if not allocate:
        native.null.add(index)
    with pytest.raises(WindowsAppDiscoveryError, match="0x80070005"):
        app_resolver._program_folders()
    assert len(native.calls) == index + 1
    assert len(native.freed) == index + 1
    assert [pointer for pointer in native.freed if pointer] == [ctypes.addressof(buffer) for buffer in native.allocations]


def test_success_without_pointer_is_explicit_error_and_null_free_is_safe(native):
    native.null.add(0)
    with pytest.raises(WindowsAppDiscoveryError, match="returned no path"):
        app_resolver._program_folders()
    assert native.freed == [None]


@pytest.mark.parametrize("stage", ["call_error", "copy_error"])
def test_python_boundary_exception_still_frees_assigned_pointer(native, stage):
    failure = OSError("controlled native/copy error")
    setattr(native, stage, failure)
    with pytest.raises(OSError) as caught:
        app_resolver._program_folders()
    assert caught.value is failure
    assert native.freed == [ctypes.addressof(native.allocations[0])]


def test_cleanup_exception_preserves_native_error_context(native):
    native.results[0] = -1
    native.free_error = OSError("controlled free boundary error")
    with pytest.raises(OSError) as caught:
        app_resolver._program_folders()
    assert caught.value is native.free_error
    assert isinstance(caught.value.__context__, WindowsAppDiscoveryError)
    assert "0xFFFFFFFF" in str(caught.value.__context__)


def test_dll_load_error_propagates_before_memory_acquisition(native):
    failure = OSError("controlled loader failure")
    native.loader.side_effect = failure
    with pytest.raises(OSError) as caught:
        app_resolver._program_folders()
    assert caught.value is failure and native.calls == native.freed == []


@pytest.mark.parametrize("path", ["", "relative", "R:relative", "\\Programs", "\\\\server\\share\\Programs",
                                  "\\\\?\\R:\\Programs", "\\\\.\\R:\\Programs", "R:\\Programs\\..\\Other"])
def test_invalid_or_nonlocal_native_path_fails_after_free_before_scan(native, path):
    native.paths[0] = path
    with pytest.raises(WindowsAppDiscoveryError, match="absolute local drive"):
        app_resolver._program_folders()
    assert native.freed == [ctypes.addressof(native.allocations[0])]
    native.kernel32.GetDriveTypeW.assert_not_called()


@pytest.mark.parametrize("drive_type", [0, 1, 4])
def test_unknown_missing_and_network_drives_fail_closed(native, drive_type):
    native.drive_type = drive_type
    with pytest.raises(WindowsAppDiscoveryError, match="drive is not local"):
        app_resolver._program_folders()
    assert native.freed == [ctypes.addressof(native.allocations[0])]


def test_inventory_is_sorted_nested_and_does_not_read_or_modify_shortcuts(inventory, monkeypatch):
    paths = [shortcut(inventory.user, "Visual Studio Code.lnk"),
             shortcut(inventory.user, "Tools/GitHub Desktop.lnk"),
             shortcut(inventory.common, "VLC media player.LNK")]
    before = {path: (path.read_bytes(), path.stat().st_mtime_ns) for path in paths}
    with monkeypatch.context() as guarded:
        guarded.setattr(Path, "open", Mock(side_effect=AssertionError("Shortcut content must not be opened")))
        targets = WindowsAppResolver().inventory()
    assert targets == tuple(WindowsAppTarget(path.stem, path) for path in (paths[1], paths[0], paths[2]))
    assert {path: (path.read_bytes(), path.stat().st_mtime_ns) for path in paths} == before
    inventory.native.loader.assert_not_called()
    with pytest.raises(FrozenInstanceError):
        targets[0].display_name = "changed"


def test_filter_only_regular_lnk_files(inventory):
    expected = shortcut(inventory.user, "Actual App.lnk")
    for name in ("app.exe", "app.txt", "app.url", "app.cmd", "app.bat", "app.ps1", "app", "fake.lnk.exe"):
        shortcut(inventory.user, name)
    (inventory.user / "directory.lnk").mkdir()
    assert WindowsAppResolver().inventory() == (WindowsAppTarget("Actual App", expected),)


@pytest.mark.parametrize("name", ["Visual Studio Code", "visual studio code", "VISUAL STUDIO CODE"])
def test_full_name_casefold_match(inventory, name):
    path = shortcut(inventory.user, "Visual Studio Code.lnk")
    assert WindowsAppResolver().resolve(name) == WindowsAppTarget("Visual Studio Code", path)


@pytest.mark.parametrize("name", ["Visual", "Code", "Visual Studio", "Visual Studio Code.exe", "Visual Studio Code.lnk",
                                  " Visual Studio Code", "Visual Studio Code ", "App Visual Studio Code",
                                  "the Visual Studio Code", "Finder", "Safari", "", "unknown",
                                  "R:\\Visual Studio Code.lnk", "../Visual Studio Code", "https://example.com", "cmd /c start"])
def test_no_guessing_trimming_alias_path_or_shell_interpretation(inventory, name):
    shortcut(inventory.user, "Visual Studio Code.lnk")
    with pytest.raises(WindowsAppNotFoundError):
        WindowsAppResolver().resolve(name)


def test_casefold_is_documented_python_comparison_without_unicode_normalization(inventory):
    path = shortcut(inventory.user, "Straße.lnk")
    assert WindowsAppResolver().resolve("STRASSE").shortcut_path == path
    shortcut(inventory.user, "Café.lnk")
    with pytest.raises(WindowsAppNotFoundError):
        WindowsAppResolver().resolve("Cafe\u0301")


def test_ambiguity_retains_all_distinct_paths_in_stable_order(inventory, monkeypatch):
    paths = [shortcut(inventory.user, "Z/Example.lnk"), shortcut(inventory.common, "Example.lnk"),
             shortcut(inventory.user, "A/example.LNK")]
    resolver = WindowsAppResolver()
    with pytest.raises(WindowsAppAmbiguousError) as first:
        resolver.resolve("EXAMPLE")
    assert {str(target.shortcut_path) for target in first.value.candidates} == {str(path) for path in paths}
    assert first.value.display_name == "EXAMPLE"
    assert str(inventory.user) not in str(first.value) and str(inventory.common) not in str(first.value)
    inventory.folders.return_value = (inventory.common, inventory.user)
    real_scandir = os.scandir

    @contextmanager
    def reversed_scan(path):
        with real_scandir(path) as entries:
            yield iter(reversed(list(entries)))

    monkeypatch.setattr(os, "scandir", reversed_scan)
    with pytest.raises(WindowsAppAmbiguousError) as second:
        resolver.resolve("EXAMPLE")
    assert second.value.candidates == first.value.candidates
    assert resolver.inventory() == first.value.candidates


def test_same_path_from_repeated_or_overlapping_roots_is_not_ambiguous(inventory):
    path = shortcut(inventory.user, "Nested/Example.lnk")
    inventory.folders.return_value = (inventory.user, inventory.user, path.parent)
    assert WindowsAppResolver().resolve("Example") == WindowsAppTarget("Example", path)


def test_inventory_is_fresh_not_a_persisted_cache(inventory):
    resolver = WindowsAppResolver()
    assert resolver.inventory() == ()
    path = shortcut(inventory.user, "New.lnk")
    assert resolver.resolve("New").shortcut_path == path
    path.unlink()
    with pytest.raises(WindowsAppNotFoundError):
        resolver.resolve("New")


@pytest.mark.parametrize("mode, attributes", [(stat.S_IFDIR, stat.FILE_ATTRIBUTE_REPARSE_POINT),
                                             (stat.S_IFREG, stat.FILE_ATTRIBUTE_REPARSE_POINT),
                                             (stat.S_IFLNK, 0), (stat.S_IFIFO, 0)])
def test_link_reparse_and_special_entries_are_never_returned_or_descended(inventory, monkeypatch, mode, attributes):
    shortcut(inventory.user, "Linked.lnk/Outside.lnk")
    real_scandir = os.scandir
    scanned = []

    @contextmanager
    def scan(path):
        scanned.append(path)
        with real_scandir(path) as entries:
            yield [SimpleNamespace(name=entry.name, path=entry.path,
                                   stat=lambda **kwargs: SimpleNamespace(st_mode=mode, st_file_attributes=attributes))
                   for entry in entries]

    monkeypatch.setattr(os, "scandir", scan)
    assert WindowsAppResolver().inventory() == ()
    assert set(scanned) == {inventory.user, inventory.common}


@pytest.mark.parametrize("location", ["root", "ancestor"])
def test_reparse_root_or_ancestor_prevents_scan(inventory, monkeypatch, location):
    shortcut(inventory.user, "Hidden.lnk")
    rejected = inventory.user if location == "root" else inventory.user.parent
    real_lstat = Path.lstat

    def lstat(path):
        if path == rejected:
            return SimpleNamespace(st_mode=stat.S_IFDIR, st_file_attributes=stat.FILE_ATTRIBUTE_REPARSE_POINT)
        return real_lstat(path)

    monkeypatch.setattr(Path, "lstat", lstat)
    assert WindowsAppResolver().inventory() == ()


@pytest.mark.parametrize("stage", ["root", "scan", "entry"])
def test_filesystem_errors_abort_instead_of_hiding_ambiguity(inventory, monkeypatch, stage):
    shortcut(inventory.user, "Example.lnk")
    failure = PermissionError("controlled unreadable inventory")
    if stage == "root":
        monkeypatch.setattr(app_resolver, "_plain_directory", Mock(side_effect=failure))
    elif stage == "scan":
        monkeypatch.setattr(os, "scandir", Mock(side_effect=failure))
    else:
        @contextmanager
        def scan(path):
            yield [SimpleNamespace(name="Example.lnk", path=str(path / "Example.lnk"), stat=Mock(side_effect=failure))]
        monkeypatch.setattr(os, "scandir", scan)
    with pytest.raises(PermissionError) as caught:
        WindowsAppResolver().resolve("Example")
    assert caught.value is failure


def test_missing_root_is_not_created_or_hidden(inventory):
    missing = inventory.user / "missing"
    inventory.folders.return_value = (missing, inventory.common)
    with pytest.raises(FileNotFoundError):
        WindowsAppResolver().inventory()
    assert not missing.exists()


@pytest.mark.parametrize("value", [None, 1, True, Path("Example.lnk"), b"Example"])
def test_no_coercion_or_discovery_for_non_string(inventory, value):
    with pytest.raises(TypeError):
        WindowsAppResolver().resolve(value)
    inventory.folders.assert_not_called()


@pytest.mark.parametrize("platform", ["linux", "darwin"])
def test_non_windows_fails_before_native_or_filesystem(monkeypatch, native, platform):
    monkeypatch.setattr(app_resolver, "sys", SimpleNamespace(platform=platform))
    scan = Mock(side_effect=AssertionError("No filesystem discovery on this host"))
    monkeypatch.setattr(os, "scandir", scan)
    for operation in (WindowsAppResolver().inventory, lambda: WindowsAppResolver().resolve("Example")):
        with pytest.raises(OSError, match="requires a Windows host"):
            operation()
    native.loader.assert_not_called()
    scan.assert_not_called()


def test_actual_host_platform_with_only_controlled_roots(monkeypatch, tmp_path, native):
    roots = Mock(return_value=(tmp_path,))
    monkeypatch.setattr(app_resolver, "_program_folders", roots)
    if sys.platform == "win32":
        assert WindowsAppResolver().inventory() == ()
        roots.assert_called_once()
    else:
        with pytest.raises(OSError, match="requires a Windows host"):
            WindowsAppResolver().inventory()
        roots.assert_not_called()
    native.loader.assert_not_called()


def test_resolver_never_grants_apps_open_availability(inventory):
    assert "apps.open" in CAPABILITY_CATALOG
    registry = CapabilityProviderRegistry()
    resolver = WindowsAppResolver()
    shortcut(inventory.user, "Example.lnk")
    resolver.resolve("Example")
    assert registry.available_capabilities() == CapabilityProviderRegistry().available_capabilities() == ()
    with pytest.raises(CapabilityUnavailableError):
        registry.resolve("apps.open")
    assert not hasattr(resolver, "execute")


@pytest.mark.parametrize("control", ["", "os.scandir", "ctypes.dlopen", "subprocess.Popen", "socket.connect", "sqlite3.connect", "write"])
def test_cold_import_and_instantiation_are_inert(tmp_path, control):
    program = textwrap.dedent('''
        import os, sys, dataclasses, pathlib, uuid, functools
        sys.dont_write_bytecode = True
        sys.path.insert(0, sys.argv[1])
        def guard(event, args):
            if event.startswith("ctypes.") or event in {
                "os.scandir", "subprocess.Popen", "os.system", "os.posix_spawn",
                "os.startfile", "os.startfile/2", "socket.connect", "socket.bind", "sqlite3.connect"
            }:
                raise AssertionError("Forbidden: " + event)
            if event == "open":
                _, mode, flags = args
                if (isinstance(mode, str) and any(c in mode for c in "wax+")) or (
                    isinstance(flags, int) and flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND)
                ):
                    raise AssertionError("Forbidden: write")
        sys.addaudithook(guard)
        control = sys.argv[2]
        if control == "write":
            open("forbidden.txt", "w")
        elif control:
            sys.audit(control, "controlled negative probe")
        import jarvis_agent.providers.windows
        assert not any(name.startswith("jarvis_agent.providers.windows.") for name in sys.modules)
        from jarvis_agent.providers.windows.app_resolver import WindowsAppResolver
        WindowsAppResolver()
        allowed = {"jarvis_agent.providers", "jarvis_agent.providers.windows",
                   "jarvis_agent.providers.windows.app_resolver"}
        assert not [name for name in sys.modules if name.startswith("jarvis_agent.") and name not in allowed]
        print("inert-resolver-ok")
    ''')
    script = tmp_path / "probe.py"
    script.write_text(program, encoding="utf-8")
    result = subprocess.run([sys.executable, "-I", str(script), str(Path(__file__).resolve().parents[1] / "apps/agent"), control],
                            cwd=tmp_path, capture_output=True, text=True, timeout=20, check=False)
    if control:
        assert result.returncode != 0 and "Forbidden: " + control in result.stderr
    else:
        assert result.returncode == 0, result.stdout + result.stderr
        assert result.stdout.strip() == "inert-resolver-ok"
    assert set(tmp_path.iterdir()) == {script}
