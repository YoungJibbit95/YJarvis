"""Domain isolation and only the explicitly approved, unwired V2 consumers."""

import ast
import importlib.util
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
AGENT_PACKAGE = ROOT / "apps" / "agent" / "jarvis_agent"
DOMAIN = AGENT_PACKAGE / "domain"
TOOL_RUNTIME = AGENT_PACKAGE / "tool_runtime.py"
PROVIDER_REGISTRY = AGENT_PACKAGE / "provider_registry.py"
WINDOWS_URL_PROVIDER = AGENT_PACKAGE / "providers" / "windows" / "url_open.py"
WINDOWS_CLIPBOARD_PROVIDER = AGENT_PACKAGE / "providers" / "windows" / "clipboard_read.py"
WINDOWS_CLIPBOARD_WRITE_PROVIDER = AGENT_PACKAGE / "providers" / "windows" / "clipboard_write.py"


def test_domain_imports_only_stdlib_pydantic_and_itself():
    assert (DOMAIN / "__init__.py").is_file()
    for path in sorted(DOMAIN.glob("*.py")):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                name = node.module or ""
                if node.level:
                    name = importlib.util.resolve_name("." * node.level + name, "jarvis_agent.domain")
                names = [name]
            else:
                continue
            for name in names:
                root = name.split(".", 1)[0]
                assert root in sys.stdlib_module_names or root == "pydantic" or name == "jarvis_agent.domain" or name.startswith("jarvis_agent.domain."), (path, name)


def imported_names(path):
    package = ".".join(path.relative_to(AGENT_PACKAGE.parent).parts[:-1])
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            yield from (alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            name = node.module or ""
            if node.level:
                name = importlib.util.resolve_name("." * node.level + name, package)
            yield name
            yield from (f"{name}.{alias.name}" for alias in node.names)


def test_legacy_runtime_has_no_domain_kernel_registry_or_v2_provider_imports():
    # Ensure this test inspects a full repository, not a partial contract checkout.
    assert (AGENT_PACKAGE / "agent_service.py").is_file()
    for path in sorted(AGENT_PACKAGE.rglob("*.py")):
        if DOMAIN in path.parents or path in {TOOL_RUNTIME, PROVIDER_REGISTRY, WINDOWS_URL_PROVIDER, WINDOWS_CLIPBOARD_PROVIDER, WINDOWS_CLIPBOARD_WRITE_PROVIDER}:
            continue
        for name in imported_names(path):
            assert not any(name == forbidden or name.startswith(forbidden + ".")
                           for forbidden in ("jarvis_agent.domain", "jarvis_agent.tool_runtime",
                                             "jarvis_agent.provider_registry", "jarvis_agent.providers")), (path, name)


@pytest.mark.parametrize("path, extra", [
    (TOOL_RUNTIME, {"typing", "typing.Protocol"}),
    (PROVIDER_REGISTRY, {"jarvis_agent.tool_runtime", "jarvis_agent.tool_runtime.ToolProvider"}),
])
def test_kernel_and_registry_import_only_their_exact_semantic_dependencies(path, extra):
    assert path.is_file()
    allowed = {
        "__future__", "__future__.annotations",
        "pydantic", "pydantic.BaseModel",
        "jarvis_agent.domain.action", "jarvis_agent.domain.action.CapabilityName",
        "jarvis_agent.domain.capability_catalog",
        "jarvis_agent.domain.capability_catalog.CAPABILITY_CATALOG",
    }
    assert set(imported_names(path)) <= allowed | extra
    # No legacy view access via an attribute, name or dynamic string lookup either.
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        value = (node.id if isinstance(node, ast.Name) else
                 node.attr if isinstance(node, ast.Attribute) else
                 node.value if isinstance(node, ast.Constant) else None)
        assert not (isinstance(value, str) and value.startswith("LEGACY_")), value


def test_windows_url_provider_has_only_exact_native_and_contract_dependencies():
    assert WINDOWS_URL_PROVIDER.is_file()
    assert set(imported_names(WINDOWS_URL_PROVIDER)) <= {
        "asyncio", "os", "sys", "pydantic", "pydantic.BaseModel",
        "jarvis_agent.domain.action", "jarvis_agent.domain.action.CapabilityName",
        "jarvis_agent.domain.tool_inputs", "jarvis_agent.domain.tool_inputs.UrlOpenInput",
        "jarvis_agent.domain.tool_outputs", "jarvis_agent.domain.tool_outputs.NoDataOutput",
    }
    # No blanket exemption for providers/. Both package initializers stay inert.
    for path in (AGENT_PACKAGE / "providers" / "__init__.py",
                 AGENT_PACKAGE / "providers" / "windows" / "__init__.py"):
        body = ast.parse(path.read_text(encoding="utf-8")).body
        assert len(body) == 1 and isinstance(body[0], ast.Expr)
        assert isinstance(body[0].value, ast.Constant) and isinstance(body[0].value.value, str)
    for node in ast.walk(ast.parse(WINDOWS_URL_PROVIDER.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
            if node.value.id in {"os", "sys", "asyncio"}:
                assert (node.value.id, node.attr) in {
                    ("os", "startfile"), ("sys", "platform"), ("asyncio", "to_thread"),
                }


def test_clipboard_provider_imports_only_exact_contract_and_native_dependencies():
    assert WINDOWS_CLIPBOARD_PROVIDER.is_file()
    assert set(imported_names(WINDOWS_CLIPBOARD_PROVIDER)) <= {
        "asyncio", "sys", "ctypes", "ctypes.wintypes", "functools", "functools.cache",
        "pydantic", "pydantic.BaseModel",
        "jarvis_agent.domain.action", "jarvis_agent.domain.action.CapabilityName",
        "jarvis_agent.domain.tool_inputs", "jarvis_agent.domain.tool_inputs.ClipboardReadInput",
        "jarvis_agent.domain.tool_outputs", "jarvis_agent.domain.tool_outputs.ClipboardReadOutput",
    }
    attributes = {
        "asyncio": {"to_thread"}, "sys": {"platform"},
        "ctypes": {"WinDLL", "set_last_error", "get_last_error", "WinError", "string_at", "c_void_p", "c_size_t"},
        "wintypes": {"HWND", "BOOL", "UINT", "HANDLE", "HGLOBAL"},
        "user32": {"OpenClipboard", "IsClipboardFormatAvailable", "GetClipboardData", "CloseClipboard"},
        "kernel32": {"GlobalLock", "GlobalSize", "GlobalUnlock"},
    }
    tree = ast.parse(WINDOWS_CLIPBOARD_PROVIDER.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id in attributes:
            assert node.attr in attributes[node.value.id], (node.value.id, node.attr)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            assert node.func.id not in {"open", "exec", "eval", "__import__", "getattr"}


def test_clipboard_write_provider_imports_only_exact_contract_and_native_dependencies():
    assert WINDOWS_CLIPBOARD_WRITE_PROVIDER.is_file()
    assert set(imported_names(WINDOWS_CLIPBOARD_WRITE_PROVIDER)) <= {
        "asyncio", "sys", "ctypes", "ctypes.wintypes", "functools", "functools.cache",
        "pydantic", "pydantic.BaseModel",
        "jarvis_agent.domain.action", "jarvis_agent.domain.action.CapabilityName",
        "jarvis_agent.domain.tool_inputs", "jarvis_agent.domain.tool_inputs.ClipboardWriteInput",
        "jarvis_agent.domain.tool_outputs", "jarvis_agent.domain.tool_outputs.NoDataOutput",
    }
    attributes = {
        "asyncio": {"to_thread"}, "sys": {"platform"},
        "ctypes": {"WinDLL", "set_last_error", "get_last_error", "WinError", "memmove", "c_int", "c_void_p", "c_size_t"},
        "wintypes": {"HWND", "HMENU", "HINSTANCE", "DWORD", "LPCWSTR", "BOOL", "UINT", "HANDLE", "HGLOBAL"},
        "user32": {"CreateWindowExW", "DestroyWindow", "OpenClipboard", "EmptyClipboard", "SetClipboardData", "CloseClipboard"},
        "kernel32": {"GlobalAlloc", "GlobalLock", "GlobalUnlock", "GlobalFree"},
    }
    tree = ast.parse(WINDOWS_CLIPBOARD_WRITE_PROVIDER.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id in attributes:
            assert node.attr in attributes[node.value.id], (node.value.id, node.attr)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            assert node.func.id not in {"open", "exec", "eval", "__import__", "getattr"}


def run_domain_probe(tmp_path, side_effect=""):
    program = textwrap.dedent(
        """
        import os
        import sys
        sys.dont_write_bytecode = True
        sys.path.insert(0, sys.argv[1])

        def forbid_runtime_access(event, args):
            if event in {"subprocess.Popen", "os.system", "os.posix_spawn",
                         "socket.connect", "socket.bind", "sqlite3.connect",
                         "os.startfile", "os.startfile/2"}:
                raise AssertionError("Unexpected side effect: " + event)
            if event == "open":
                _, mode, flags = args
                if (isinstance(mode, str) and any(c in mode for c in "wax+")) or (
                    isinstance(flags, int) and flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND)
                ):
                    raise AssertionError("Unexpected file write")

        sys.addaudithook(forbid_runtime_access)
        from jarvis_agent.domain import Action, ActionPlan, Observation, PlannedAction, PolicyDecision, Turn
        from jarvis_agent.domain import ToolSpecV2
        from jarvis_agent.domain.capability_catalog import CAPABILITY_CATALOG, LEGACY_TOOL_CATALOG, LEGACY_TOOL_TO_CAPABILITY
        import json
        inputs = json.loads(sys.argv[2])
        outputs = json.loads(sys.argv[3])
        assert len(CAPABILITY_CATALOG) == len(LEGACY_TOOL_CATALOG) == len(LEGACY_TOOL_TO_CAPABILITY) == 18
        assert set(CAPABILITY_CATALOG) == set(LEGACY_TOOL_TO_CAPABILITY.values())
        assert inputs.keys() == LEGACY_TOOL_CATALOG.keys()
        assert outputs.keys() == LEGACY_TOOL_CATALOG.keys()
        for name, capability in LEGACY_TOOL_TO_CAPABILITY.items():
            spec = CAPABILITY_CATALOG[capability]
            assert spec is LEGACY_TOOL_CATALOG[name]
            assert ToolSpecV2.model_validate(spec.model_dump()) == spec
            payload = spec.input_model.model_validate(inputs[name])
            assert spec.input_model.model_validate(payload) == payload
            assert spec.input_model.model_validate_json(payload.model_dump_json()) == payload
            spec.input_model.model_json_schema()
            result = spec.output_model.model_validate(outputs[name]["data"])
            assert spec.output_model.model_validate(result) == result
            assert spec.output_model.model_validate_json(result.model_dump_json()) == result
            spec.output_model.model_json_schema()
        from uuid import UUID
        action = Action(id=UUID(int=1), capability="example.unregistered", arguments={"command": "never execute this"},
                        mode="system", risk="critical", reversible=False, requires_result=True)
        step = PlannedAction(action=action)
        plan = ActionPlan(id=UUID(int=2), turn_id=UUID(int=3), goal="Inert example", summary="Data only", actions=[step], status="approved")
        PolicyDecision(action_id=action.id, verdict="allow", reason_code="FIXTURE", human_reason="Data only", policy_source="test")
        Turn(id=UUID(int=3), session_id=UUID(int=4), input_mode="text", user_text="Inert example",
             created_at="2026-10-06T17:00:00Z", updated_at="2026-10-06T17:00:00Z")
        Observation(action_id=action.id, success=True, summary="Inert result", data={}, duration_ms=0, occurred_at="2026-10-06T17:00:00Z")
        assert ActionPlan.model_validate_json(plan.model_dump_json()) == plan
        unexpected = [name for name in sys.modules if name.startswith("jarvis_agent.")
                      and name != "jarvis_agent.domain" and not name.startswith("jarvis_agent.domain.")]
        assert not unexpected, unexpected
        """
    )
    program += "\n" + side_effect + '\nprint("isolated-domain-ok")\n'
    # A real script avoids the Windows/Python 3.11.1 audit/import failure seen
    # with -c, even with a no-op hook. Keep -I and install the full audit guard
    # before importing the domain; do not preload the modules under test.
    script = tmp_path / "domain_probe.py"
    script.write_text(program, encoding="utf-8")
    workdir = tmp_path / "work"
    workdir.mkdir()
    result = subprocess.run(
        [sys.executable, "-I", str(script), str(AGENT_PACKAGE.parent),
         (ROOT / "tests" / "fixtures" / "tool_inputs.json").read_text(encoding="utf-8"),
         (ROOT / "tests" / "fixtures" / "tool_outputs.json").read_text(encoding="utf-8")],
        cwd=workdir,
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    assert not list(workdir.iterdir())
    assert set(tmp_path.iterdir()) == {script, workdir}
    assert script.read_text(encoding="utf-8") == program
    return result


def test_import_and_validation_do_not_access_runtime_services(tmp_path):
    result = run_domain_probe(tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.strip() == "isolated-domain-ok"


def test_windows_provider_cold_import_and_registration_are_inert(tmp_path):
    program = textwrap.dedent('''
        from jarvis_agent.provider_registry import CapabilityProviderRegistry
        registry = CapabilityProviderRegistry()
        from jarvis_agent.providers.windows.url_open import WindowsUrlOpenProvider
        provider = WindowsUrlOpenProvider()
        assert registry.available_capabilities() == ()
        registry.register("url.open", provider)
        assert registry.available_capabilities() == ("url.open",)
        assert registry.resolve("url.open") is provider
        assert CapabilityProviderRegistry().available_capabilities() == ()
        allowed = {"jarvis_agent.domain", "jarvis_agent.tool_runtime",
                   "jarvis_agent.provider_registry", "jarvis_agent.providers",
                   "jarvis_agent.providers.windows", "jarvis_agent.providers.windows.url_open"}
        unexpected = [name for name in sys.modules if name.startswith("jarvis_agent.")
                      and name not in allowed and not name.startswith("jarvis_agent.domain.")]
        assert not unexpected, unexpected
    ''')
    result = run_domain_probe(tmp_path, program)
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.strip() == "isolated-domain-ok"


@pytest.mark.parametrize("event", ["os.startfile", "os.startfile/2"])
def test_probe_blocks_native_launch_audit_events_without_opening_a_browser(tmp_path, event):
    result = run_domain_probe(tmp_path, f"sys.audit({event!r}, 'https://example.test', 'open')")
    assert result.returncode != 0
    assert "AssertionError: Unexpected side effect: " + event in result.stderr


def test_clipboard_package_import_and_registration_do_not_load_or_call_native_code(tmp_path):
    program = textwrap.dedent('''
        def forbid_native(event, args):
            if event.startswith("ctypes."):
                raise AssertionError("Unexpected native access: " + event)
        sys.addaudithook(forbid_native)
        import jarvis_agent.providers.windows
        assert "jarvis_agent.providers.windows.url_open" not in sys.modules
        assert "jarvis_agent.providers.windows.clipboard_read" not in sys.modules
        from jarvis_agent.provider_registry import CapabilityProviderRegistry
        from jarvis_agent.providers.windows.clipboard_read import WindowsClipboardReadProvider
        registry = CapabilityProviderRegistry()
        provider = WindowsClipboardReadProvider()
        assert registry.available_capabilities() == ()
        registry.register("clipboard.read", provider)
        assert registry.available_capabilities() == ("clipboard.read",)
        assert registry.resolve("clipboard.read") is provider
        assert CapabilityProviderRegistry().available_capabilities() == ()
        allowed = {"jarvis_agent.domain", "jarvis_agent.tool_runtime",
                   "jarvis_agent.provider_registry", "jarvis_agent.providers",
                   "jarvis_agent.providers.windows", "jarvis_agent.providers.windows.clipboard_read"}
        unexpected = [name for name in sys.modules if name.startswith("jarvis_agent.")
                      and name not in allowed and not name.startswith("jarvis_agent.domain.")]
        assert not unexpected, unexpected
    ''')
    result = run_domain_probe(tmp_path, program)
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.strip() == "isolated-domain-ok"


@pytest.mark.parametrize("attempt_native", [False, True])
def test_clipboard_write_import_and_registration_are_inert_with_native_audit_control(tmp_path, attempt_native):
    program = textwrap.dedent('''
        def forbid_native(event, args):
            if event.startswith("ctypes."):
                raise AssertionError("Unexpected native access: " + event)
        sys.addaudithook(forbid_native)
        if ATTEMPT_NATIVE:
            sys.audit("ctypes.dlopen", "user32.dll")  # audit control, no actual DLL load
        import jarvis_agent.providers.windows
        assert not any(name.startswith("jarvis_agent.providers.windows.") for name in sys.modules)
        from jarvis_agent.provider_registry import CapabilityProviderRegistry
        from jarvis_agent.providers.windows.clipboard_write import WindowsClipboardWriteProvider
        registry = CapabilityProviderRegistry()
        provider = WindowsClipboardWriteProvider()
        assert registry.available_capabilities() == ()
        registry.register("clipboard.write", provider)
        assert registry.available_capabilities() == ("clipboard.write",)
        assert registry.resolve("clipboard.write") is provider
        assert CapabilityProviderRegistry().available_capabilities() == ()
        allowed = {"jarvis_agent.domain", "jarvis_agent.tool_runtime",
                   "jarvis_agent.provider_registry", "jarvis_agent.providers",
                   "jarvis_agent.providers.windows", "jarvis_agent.providers.windows.clipboard_write"}
        unexpected = [name for name in sys.modules if name.startswith("jarvis_agent.")
                      and name not in allowed and not name.startswith("jarvis_agent.domain.")]
        assert not unexpected, unexpected
    ''')
    result = run_domain_probe(tmp_path, f"ATTEMPT_NATIVE = {attempt_native!r}\n" + program)
    if attempt_native:
        assert result.returncode != 0
        assert "Unexpected native access: ctypes.dlopen" in result.stderr
    else:
        assert result.returncode == 0, result.stdout + result.stderr
        assert result.stdout.strip() == "isolated-domain-ok"


@pytest.mark.parametrize("use_registry", [False, True])
def test_tool_runtime_cold_import_and_fake_invocation_have_no_runtime_side_effects(tmp_path, use_registry):
    # Reuse the unchanged audit guard, installed before ANY domain/kernel import.
    # A synchronous fake coroutine needs no event-loop socket pair on Windows.
    program = textwrap.dedent('''
        from jarvis_agent.tool_runtime import ToolRuntime

        class FakeProvider:
            calls = 0

            async def execute(self, capability, input_data):
                self.calls += 1
                assert type(input_data) is CAPABILITY_CATALOG[capability].input_model
                return output_data

        provider = FakeProvider()
        allowed_consumers = {"jarvis_agent.domain", "jarvis_agent.tool_runtime"}
        if USE_REGISTRY:
            from jarvis_agent.provider_registry import CapabilityProviderRegistry
            registry = CapabilityProviderRegistry()
            assert registry.available_capabilities() == ()
            for capability in CAPABILITY_CATALOG:
                registry.register(capability, provider)
                assert registry.resolve(capability) is provider
            assert registry.available_capabilities() == tuple(sorted(CAPABILITY_CATALOG))
            runtime = ToolRuntime(registry)
            allowed_consumers.add("jarvis_agent.provider_registry")
        else:
            runtime = ToolRuntime(provider)

        async def invoke_all():
            for name, capability in LEGACY_TOOL_TO_CAPABILITY.items():
                global output_data
                output_data = outputs[name]["data"]
                result = await runtime.execute(capability, inputs[name])
                assert type(result) is CAPABILITY_CATALOG[capability].output_model

        invocation = invoke_all()
        try:
            invocation.send(None)
        except StopIteration:
            pass
        else:
            raise AssertionError("Fake provider unexpectedly suspended")
        finally:
            invocation.close()
        assert provider.calls == 18
        unexpected = [name for name in sys.modules if name.startswith("jarvis_agent.")
                      and name not in allowed_consumers
                      and not name.startswith("jarvis_agent.domain.")]
        assert not unexpected, unexpected
    ''')
    result = run_domain_probe(tmp_path, f"USE_REGISTRY = {use_registry!r}\n" + program)
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.strip() == "isolated-domain-ok"


@pytest.mark.parametrize("side_effect, expected", [
    ('open("forbidden.txt", "w")', "Unexpected file write"),
    ('os.open("forbidden.txt", os.O_WRONLY | os.O_CREAT)', "Unexpected file write"),
    ('import subprocess; subprocess.run([sys.executable, "-c", "pass"], check=True)',
     "Unexpected side effect: subprocess.Popen"),
    ('import socket; socket.socket().bind(("127.0.0.1", 0))',
     "Unexpected side effect: socket.bind"),
    ('import socket; socket.socket().connect(("127.0.0.1", 9))',
     "Unexpected side effect: socket.connect"),
    ('import sqlite3; sqlite3.connect(":memory:")',
     "Unexpected side effect: sqlite3.connect"),
])
def test_domain_probe_rejects_actual_io_attempts(tmp_path, side_effect, expected):
    result = run_domain_probe(tmp_path, side_effect)
    assert result.returncode != 0
    assert "AssertionError: " + expected in result.stderr, result.stdout + result.stderr
    assert "isolated-domain-ok" not in result.stdout
