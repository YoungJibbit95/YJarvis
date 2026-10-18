# YJSEC-01 — Atomic approval claim before legacy tool execution

## Authorization and inspected baseline

The user authorized this single Core security step on 2026-10-18. This supersedes
the stale YJW-01D-only authorization snapshots for this step alone. Branch:
`codex/yjsec-01-atomic-approval-claim`. One PR, external review, no self-merge or
auto-merge, and no next-step work.

Fetched Main/base: `68fa1df76e096dce45ee0c42f39012df0efe27a3`, identical to the
user's verified baseline. The working tree was clean and no PR was open at the
start gate. Baseline [CI (seven successful jobs)](https://github.com/YoungJibbit95/YJarvis/actions/runs/38295554765)
and [Wiki validation/publication](https://github.com/YoungJibbit95/YJarvis/actions/runs/38295554596)
were checked against that exact SHA. Main already contains YJCORE-01 and the
accepted legacy/cross-platform work; the master architecture remains a migration
target, not a claim of additional implemented capabilities.

## Broken boundary and correction

Previously, two `AgentService.handle_approval_decision` calls could both read
`pending` in `TurnEngine`, then both resolve by ID and continue. The new regression
test failed on that unchanged production code with `['approved', 'approved']`
after an async barrier ensured both reads had completed.

`Database.resolve_approval` now implements the shared claim:

```sql
UPDATE approvals
SET status = ?, decision = ?, decided_at = ?
WHERE id = ? AND status = 'pending'
```

Only `("approved", "approve")` and `("denied", "deny")` are accepted. The method
returns `True` only when exactly one row changed **and commit completed**. It
returns `False` for missing/terminal rows. SQLite serializes competing writes
across connections and service instances; an in-memory lock is not the authority.
No DB schema, migration or dependency is added.

TurnEngine retains the preliminary read for the existing missing/resolved errors
and action data. It validates the decision, obtains the committed claim, and
rejects a loser with `ValueError("Approval wurde bereits entschieden")` before
consuming learned-trigger/narration context, publishing events, executing tools,
persisting results, recording learning, or finishing a response. Both decisions
use this boundary. No pending state is restored after a claimed action fails.

## Compatibility

`AgentService`, HTTP request/response DTOs and HTTP 400 error handling are
unchanged. Existing precedence remains: unknown ID, already-decided approval,
then invalid decision on a pending approval. The internal DB method's return
changes from `None` to a boolean claim result; all repository callers were
inspected. The persistence integration test's direct caller may ignore it;
TurnEngine must check it. Invalid status/decision pairs now fail without writing.

Session/run IDs, approval status names/timestamps, ToolRegistry requirements,
tool inputs/results, learning, events and winner chat text remain unchanged.
YJCORE-01 narration and fallback/evidence rules remain unchanged and run only
after the existing persisted ToolResult. They cannot authorize another dispatch.
Instance-local context is still optional: another instance or a restart may lack
it, while rejected decisions leave that instance's cached context untouched.

## Crash, cancellation and restart boundaries

| Interruption point | Durable evidence and restart behavior |
|---|---|
| Before successful claim | Approval can remain pending. No dispatch is authorized. A later explicit decision may claim it. |
| Committed claim, no observed dispatch | Approval is terminal; retry/restart rejects it, even if execution never started. `approved` is permission, not completion. |
| Dispatch may have happened, no persisted ToolResult | External outcome is `UNKNOWN_OUTCOME`. No automatic retry/re-execution or invented success. |
| ToolResult persisted, before assistant narration/message | The recorded tool outcome remains; chat completion/publication can be absent. Restart does not rerun the action or automatically resume narration. |
| Restart with an already-decided approval | Both approve and deny reject the existing decision without another dispatch or final response. |

Cancellation while a commit is in flight can also leave the caller uncertain
whether the claim committed. The stored status is authoritative on a subsequent
explicit request. Failure/cancellation propagates; it does not become a success
response. Result/learning/message persistence errors may leave partial records,
as in the existing lifecycle, but cannot authorize replay. Event delivery is not
a durable outbox and a persisted assistant message is not proof of delivery.

This is **one winning decision and at-most-one ToolRegistry dispatch per approval
through this lifecycle**, not exactly-once effects in an external OS/application.
Individual legacy tools may already perform their own internal subprocess retries.
A terminal claim alone cannot distinguish skipped, started or completed external
work. `UNKNOWN_OUTCOME` is documentation of this uncertainty, not a new stored
status, API field or implemented reconciliation state machine.

Persistent dispatch/reconciliation and stronger outcome evidence need separate
design/authorization with YJ2-06, YJ2-11/12 and YJNX D14. No migration or hidden
recovery executor is introduced here.

## Verification and evidence limits

`tests/test_approval_claim.py` uses real temporary SQLite files and async barriers
after both pending reads, with same-service and separate-service instances.
The matrix covers approve/approve, approve/deny and deny/deny, successful/failed
tools, and YJCORE-01 enabled/disabled. Additional tests cover the direct DB claim,
immutable decisions, invalid inputs, loser context preservation while the winner
is paused after commit, other sessions/runs, sequential replays, actual SQL-write
failure, injected commit/result/learning/message persistence failures, and
cancellation at five lifecycle boundaries followed by service reconstruction.

Fixtures count the internal ToolRegistry call and inspect persisted rows/events;
they do not measure external effects. Restart tests reconstruct services and
reinitialize the same SQLite file after deterministic task cancellation; they
are not real process-kill, power-loss, OS automation or native model tests.
Existing lifecycle, narration/transport, AppleScript/legacy and isolated Windows
provider tests remain part of the required full suite. Exact commands, local
results and final-head CI/Wiki evidence are recorded in the PR handoff.

## Scope, rollback and review

No changes to routing/planning, risk classes, availability/providers, V2 runtime
wiring, policy/trust, local API caller authentication (separate D13 gate),
UI/voice, installers/dependencies, multi-action execution or Nexus integration.

Rollback is a normal code revert without DB migration or data deletion. Preserve
approvals, ToolRuns and personal runtime data. Reverting reintroduces the
concurrent-decision vulnerability; do not reset terminal approvals to pending.

Review questions: Does every continuation require a committed winning claim?
Can any loser consume context or publish success? Are the concurrency proof and
`UNKNOWN_OUTCOME` limitations kept distinct from external exactly-once claims?

**STOP — EXTERNAL CHATGPT REVIEW REQUIRED.** Green CI is not approval. No
YJCORE-02/03, YJ2-05C3, YJNX or other next-step work is authorized by this PR.
