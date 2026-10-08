# YJ2-05C1: semantic ToolRuntime kernel

Base main: `210da7cd5f3f104af40ef07a24c9aba0564a4f32`. The shared merge gate
completed before this branch started: accepted #18 was squash-merged as
`b275eb6`; main CI `37748981079` passed 6/6. Product #17 synchronized as `dd2eb39`,
adding exactly #18's six files with identical Product patch-id. Its CI
`37749222209` passed 6/6, then #17 squash-merged as `210da7c` with the exact same
tree. Final main CI `37749451856` passed 6/6. Since architecture baseline
`dea0e9e`, main includes accepted Core 00 through 05B3, Windows 00A/B/B.1 and
separate Product 00A/B/01A/02A work.

## One unwired execution boundary

`jarvis_agent.tool_runtime.ToolRuntime(provider).execute(capability, raw_input)`:

1. Looks up the exact semantic key in `CAPABILITY_CATALOG`.
2. Validates input with `spec.input_model.model_validate`.
3. Awaits the injected `ToolProvider.execute(capability, typed_input)` once.
4. Validates provider data with `spec.output_model.model_validate`.
5. Returns that typed output model.

The provider is a minimal Protocol receiving a `CapabilityName` and `BaseModel`,
returning an object for output validation. Only tests implement it here. There
is no provider registry, resolver or availability inference. The module lives
outside `tools/` because that existing package eagerly imports the legacy registry;
moving those imports or providers is unnecessary for this step.

Exact lookup rejects unknown keys with `KeyError` before input validation or
provider invocation. No legacy-name lookup, aliases, trimming, case folding or
fallback exists. Model validation retains the accepted defaults and strictness;
there is no extra coercion, clamping or JSON-string decoding. Existing model
instances are revalidated, including instances created through unvalidated
Pydantic construction/copy APIs. All 18 current specs have both contracts. If a
spec lacks either model, `TypeError` occurs before provider invocation, never a
free-form contract fallback.

Input/output failures propagate Pydantic `ValidationError`. Provider exceptions
propagate unchanged, including provider-raised timeout/cancellation; there are
no retries, catches, wrappers, timers or new cancellation handling. Output
validation occurs after invocation and cannot undo a provider's side effects.

`NoDataOutput` validates an empty record. It is not evidence of execution success.
No output is an Observation or carries added success/error/duration/timestamp
fields. `files.read` still means complete semantic content; schema validation
alone cannot verify whether an eventual provider read everything.

## Authority and isolation

This kernel is the first authorized non-domain consumer of the semantic catalog.
The AST gate exempts exactly `tool_runtime.py` from the legacy Domain-import ban,
and restricts its imports to the exact Protocol/model/name/catalog dependencies.
Every other application module remains forbidden from importing Domain or this
kernel. The legacy tool/approval/planner path has no new caller or adapter.

Mode, risk, reversibility, idempotence, dry-run and timeout remain metadata. The
kernel makes no allow/deny/confirm decision and does not enforce 30 seconds.
It is not ready for production authorization: there is no production wiring,
OS provider, policy, Observation, event, metric, persistence or provider discovery.
The explicit C1 authorization narrows the broader target in architecture section
8.3; remaining responsibilities require separate review and authorization.

Tests cover all 18 capabilities with raw data and model instances, call counts,
strict failures, unknown/legacy-like names, preserved defaults/text, asynchronous
suspension, exception identity and poisoned compatibility views. A cold-import
subprocess invokes all 18 with a fake under the existing file-write/network/
process/SQLite audit guard; existing negative controls remain. Legacy approval
and registry regressions continue, with an additional test rejecting any V2 entry.
No real OS/model/audio provider or macOS GUI integration is claimed.

Rollback: revert this PR. There is no data migration or configuration change.
Stop after the PR and external handoff. Do not merge it, begin 05C2 or YJW-01.
