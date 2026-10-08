"""Domain isolation and the two explicitly allowed, unwired C1/C2 consumers."""

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


def test_legacy_runtime_has_no_domain_kernel_or_provider_registry_imports():
    # Ensure this test inspects a full repository, not a partial contract checkout.
    assert (AGENT_PACKAGE / "agent_service.py").is_file()
    for path in sorted(AGENT_PACKAGE.rglob("*.py")):
        if DOMAIN in path.parents or path in {TOOL_RUNTIME, PROVIDER_REGISTRY}:
            continue
        for name in imported_names(path):
            assert not any(name == forbidden or name.startswith(forbidden + ".")
                           for forbidden in ("jarvis_agent.domain", "jarvis_agent.tool_runtime",
                                             "jarvis_agent.provider_registry")), (path, name)


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


def run_domain_probe(tmp_path, side_effect=""):
    program = textwrap.dedent(
        """
        import os
        import sys
        sys.dont_write_bytecode = True
        sys.path.insert(0, sys.argv[1])

        def forbid_runtime_access(event, args):
            if event in {"subprocess.Popen", "os.system", "os.posix_spawn",
                         "socket.connect", "socket.bind", "sqlite3.connect"}:
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
