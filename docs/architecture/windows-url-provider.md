# YJW-01A: isolated Windows semantic URL opening

Base main: `e79893fd17bd4fe967b9a31873d9744d7d050e76`. Accepted Core #21
squash-merged as `16f4be5`; post-merge CI `37758037502` passed 6/6. Product #22
synchronized as `122fa8c`, adding exactly #21's six files; Core/Product patch-ids
remained identical. CI `37758334855` passed 6/6 before squash merge `e79893f`,
whose tree matches the tested sync head. Final shared main CI `37758573535`
passed 6/6 and main was reread before this branch started. Since architecture
baseline `dea0e9e`, this includes accepted Core 00 through 05C2, Windows
00A/B/B.1 and separate Product 00A/B/01A/02A/02B/02C1 work.

## One native boundary

`providers/windows/url_open.py` implements the existing async `ToolProvider`
contract structurally. Both new package initializers contain only docstrings;
importing the provider never loads the eager legacy `tools` package, invokes an
opener or registers availability.

`WindowsUrlOpenProvider.execute(capability, input_data)`:

1. Accepts exactly `url.open`; any other key raises `KeyError`.
2. Rejects execution outside `sys.platform == "win32"` with an explicit `OSError`.
3. Reuses `UrlOpenInput.model_validate` at the native boundary. No independent URL
   grammar, scheme conversion or relaxed validator is introduced. This also rejects
   unvalidated constructed/copied models when the provider is called directly.
4. Awaits `asyncio.to_thread(os.startfile, str(payload.url), "open")` once.
5. Returns `NoDataOutput()` after the native call returns normally.

The existing Domain contract remains the only source of HTTP(S) validation. C1
still validates input first, so invalid runtime input never enters this provider.
The provider's reuse of that same model is defensive revalidation before native
side effects, not a replacement for C1. No Domain/C1/C2 code changes.

The URL is one native argument, with a constant operation and no arguments string,
shell, PowerShell, subprocess, quoting routine or command interpolation. C1 also
revalidates the typed output. Native exceptions propagate unchanged, without retry,
fallback, error normalization, Observation, persistence or metrics.

Python's [os.startfile documentation](https://docs.python.org/3.11/library/os.html#os.startfile)
describes its Windows ShellExecute boundary and immediate return after launch;
it supplies no application exit status. Returning here does not prove the page
loaded or that a browser remains open. [asyncio.to_thread](https://docs.python.org/3.11/library/asyncio-task.html#asyncio.to_thread)
keeps this synchronous native call outside the event-loop thread. Sources checked
2026-10-08. There is no custom executor, detached job or timeout/cancellation policy.
Cancelling an await cannot undo a native launch or guarantee stopping an already
running worker. Native protocol-handler configuration remains a host concern.

## Explicit composition only

An intentional Windows setup can supply:

```python
registry = CapabilityProviderRegistry()
registry.register("url.open", WindowsUrlOpenProvider())
runtime = ToolRuntime(registry)
```

This example is not installed in any bootstrap. No composition helper or global
registry is needed. A fresh registry is empty, and only this explicit registration
makes `url.open` available; the other 17 capabilities stay unavailable. Registry
availability still means registration, not platform discovery or health. A wrongly
registered Windows provider on Linux/macOS raises on execution instead of guessing
another browser implementation. Legacy `open_url`, AgentService, TurnEngine,
planner availability, approvals and wire/DB paths remain unchanged.

## Evidence and limits

The isolation exception names exactly `providers/windows/url_open.py`, alongside
the previously approved kernel and registry. Other provider-tree modules gain no
exemption. Initializers must stay inert; direct provider imports are restricted to
the exact Domain types, BaseModel and native/async modules. Allowed OS/async attribute
access is only startfile/platform/to_thread. The cold-import audit additionally
blocks both native-launch audit events while keeping all prior I/O guards.

Tests exercise the real provider through C1/C2, HTTP(S) validation, single literal
argument forwarding, empty typed output, every other capability's rejection,
native exception identity, explicit availability and an actual worker thread with
a responsive event loop. Native openers are always mocks; shell/process calls are
blocked. Windows runs with its actual Python platform and a mocked os.startfile;
Linux verifies actual rejection plus controlled Windows-branch fakes. Cold imports
and registration are audited without loading Legacy. No real browser starts in CI.

Actual browser launch/page loading, macOS, packaged Electron and audio integration
are not verified by these tests. No policy or production authorization is added.
Rollback: revert this PR; no data/configuration migration or cleanup is necessary.
Stop after PR/CI/handoff; do not merge it or start YJW-01B/YJ2-05C3.
