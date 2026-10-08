# YJ2-05C2: explicit provider registration and availability

Base main: `28c30f6f460076e4f5f0c049b256a53a0541288b`. Accepted #19 squash-merged
as `ac5b73d`; post-merge CI `37753022180` passed 6/6. Product #20 synchronized as
`8218a43`, adding exactly #19's six files, with both patches unchanged. Its CI
`37753270892` passed 6/6 before squash merge `28c30f6` (identical tested tree).
Final common main CI `37753542892` passed 6/6 and main was reread before C2 began.
Relative to architecture baseline `dea0e9e`, this includes accepted Core 00 through
05C1, Windows 00A/B/B.1 and separate Product 00A/B/01A/02A/02B work.

## Known is not available

`CAPABILITY_CATALOG` defines 18 known semantic capabilities. A new
`CapabilityProviderRegistry` starts empty and owns an instance-local mapping of
capabilities to explicitly injected `ToolProvider` implementations. There is no
global registration, OS detection, auto-discovery or fallback provider.

| API | Behavior |
| --- | --- |
| `register(capability, provider)` | Exact catalog lookup, then register once. Unknown key: `KeyError`; duplicate: `ValueError`, including re-registering the same object. Existing registration is retained. |
| `resolve(capability)` | Exact catalog lookup, then return the original registered provider. Known but unregistered: `CapabilityUnavailableError`, a `LookupError` with a `capability` attribute, distinct from unknown-key `KeyError`. |
| `available_capabilities()` | Immutable tuple snapshot of registered keys, sorted lexically, independent of insertion order. |
| `execute(capability, typed_input)` | Resolve and await that provider once, passing the same capability/input and returning its raw data. Provider exceptions propagate unchanged. |

Registration expects an implementation of the existing async `ToolProvider`
Protocol. This is a code-injected boundary, not an untrusted plugin loader.
Availability describes explicit registration only: it neither probes provider
health nor grants permission, promises success, or changes after a provider error.
A single provider can explicitly serve multiple capabilities; different providers
can serve different keys. Duplicate replacement and unregister APIs are not needed
for this step. Returned availability snapshots cannot mutate registry membership.

## Composition preserves C1

```python
registry = CapabilityProviderRegistry()
registry.register("clipboard.read", fake_provider)
runtime = ToolRuntime(registry)
output = await runtime.execute("clipboard.read", {})
```

Only test fakes exist here. The registry structurally implements `ToolProvider`;
`tool_runtime.py` is unchanged. C1 performs semantic lookup and input validation
before calling registry execution, so invalid input never reaches registry
resolution or a provider. For a known unregistered capability, valid input leads
to `CapabilityUnavailableError`; invalid input still fails C1 validation first.
Unknown capability raises the catalog's `KeyError` before registry execution.
C1 validates provider output afterward, including revalidation of model instances.

The registry itself does not duplicate validation, normalize output, catch provider
exceptions, retry or enforce timeouts. Direct `resolve`/`execute` callers must honor
the typed provider contract; the validated execution boundary remains ToolRuntime.
No policy, approval, Observation, event or persistence responsibility is added.
Catalog metadata/models and all legacy/wire/DB paths remain unchanged.

## Isolation and evidence

The exact allowed non-domain consumers are `tool_runtime.py` and
`provider_registry.py`. The latter imports only semantic identity/catalog,
`BaseModel` and the existing `ToolProvider` Protocol. All other application modules
remain forbidden from importing Domain, kernel or registry. In particular, no
planner/UI availability wiring or legacy adapter exists. The kernel cannot import
the registry; composition is injected.

Tests cover empty/partial/full registration, deterministic isolated snapshots,
exact provider identity, unknown/legacy-like keys, duplicates, explicit
unavailability, single delegation, two-provider selection, C1 validation order,
output failures, unchanged exception identity and forbidden legacy-view access.
Cold-import tests register, resolve and execute all 18 using fakes under the
existing process/network/SQLite/file-write audit guard; the C1-only case and all
six negative controls remain. Existing catalog snapshots and legacy regressions run.

No Windows/macOS provider, native tool, GUI or audio integration is claimed.
Rollback: revert this PR; no migration or personal-data cleanup is needed.
Stop after PR/CI/handoff. Do not merge it, begin YJ2-05C3 or YJW-01.
