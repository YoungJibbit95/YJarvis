# YJW-00B.1: external Ollama reuse reliability

Recovery base: `662c6e73c40a6a5fba194b9cb9f81c2df151339c`.
YJ2-04B is externally accepted. Main CI run `37669930173`, attempts 1 and 2,
failed the same Windows external HTTP reuse test after 527 passing Python tests.
This is a repeated failure, not a one-time flake.

## Diagnosis and limits

Previously, one `healthy()` failure immediately authorized a local spawn.
Its 1000 ms abort signal starts before `fetch()`; cold initialization or scheduling
can exhaust that budget even when the server is already listening. The catch
returns false, indistinguishable to the caller from a genuinely offline service.

On native Windows, Node 22.23.3, temporary instrumentation recorded listening,
fetch dispatch, abort, request receipt, response and body cancellation. Ordinary
IPv4 and `localhost` probes succeeded: first probe about 50 ms, subsequent probes
about 2-9 ms, with successful body cancellation. With a controlled 1100 ms pause
before the first real fetch, the listening server received no first request;
`TimeoutError` occurred around 1145 ms and the old code attempted the forbidden
spawn. The next real probe succeeded. With this fix, the same experiment reused
the endpoint around 1169 ms with no spawn. Diagnostic logging is not shipped.

This demonstrates a production failure mechanism, not proof of the exact scheduler
or fetch-initialization delay on the historical GitHub runners. Those logs have no
probe-stage diagnostics. DNS and body cancellation did not fail in local probes;
the original test already uses an IPv4 literal. No OS-specific cause is assumed.

## Runtime change

`ensureOllama()` confirms a failed probe exactly once before deciding offline.
Each attempt retains `healthy()`'s 1000 ms timeout; no unconditional sleep or
retry loop is added to the shared probe. A successful first attempt stays fast.
An unresponsive endpoint now consumes two probe budgets, approximately two seconds
when the event loop is responsive. JavaScript timers are not hard wall-clock bounds
under event-loop starvation. Shutdown is checked before and after each probe;
an active probe can finish its existing timeout, but cannot trigger another probe
or spawn after shutdown.

Success returns null and registers no child. Two failures retain the existing
local-host allowlist and one `ollama serve` spawn with the configured `OLLAMA_HOST`.
Unavailable remote endpoints still throw; no local substitution, external PID
discovery, external termination or shell execution is introduced.

## Regression evidence

The original real HTTP test retains the forbidden-spawn assertion and now repeats
three reuse/stop/health cycles. New cases cover expiration before dispatch using
the real fetch and abort signal, a real first request that never receives headers,
two unanswered requests with bounded completion, 503/connection failure, injected
ownership decisions, and shutdown before/during either probe. Local/remote offline
tests require exactly two probes and at most the one authorized local spawn.
The delayed-response regression failed against the original runtime with
`external Ollama must not spawn after one timeout`; it passes with confirmation.
There are no skips, xfails, CI exceptions, dependencies or fake-success probes
replacing real HTTP coverage. Linux and Windows run the same startup suite.

## Scope, verification limits and rollback

Only startup reliability, its tests and current scope documentation change.
Planner/router, tools, providers, policy, audio, UI, packaging and dependency
manifests are untouched. CI/manual results at the final commit are recorded in
the PR. A GUI launch does not prove audio/native tool parity or macOS integration.
The separately reported missing local Electron binary is an installation issue;
repairing ignored `node_modules` does not change the dependency graph or this PR.

Revert this recovery commit to restore the single-probe behavior and tests; no
database, model, settings or user-data rollback is needed. Persistent slowness can
still exhaust both budgets. No finite probe guarantees arbitrary future readiness.
Leave this PR open for external review; YJ2-05A and YJW-01 remain unauthorized.
