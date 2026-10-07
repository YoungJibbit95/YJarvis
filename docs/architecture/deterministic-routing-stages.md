# YJ2-04A: deterministic legacy routing stages

This is a behavior-preserving extraction from main
`399ce0b580ac64419cf53ee09d3c2cafafbe5906`, after external acceptance of YJW-00B.
It is the first user-authorized part of YJ2-04, not the V2 router/planner runtime.

This note records the YJ2-04A extraction. YJ2-04B subsequently moves the remaining
planner fallback from the facade into the [legacy planner adapter](legacy-planner-adapter.md),
preserving the priority and confirmation behavior described here.

## Boundaries and exact legacy priority

`TurnEngine -> LegacyRouting compatibility facade -> routing_stages.py`.
The facade coordinates these small boundaries in this order:

1. `LegacySafetyStage.resolve_confirmation`: consume accepted pending text or
   discard pending confirmation when another message arrives.
2. `LegacySafetyStage.check`: hard safety block, including after confirmation.
3. Same safety stage: request confirmation unless already confirmed.
4. `LegacyLearningStage.instruction`: existing learning commands.
5. `LocalFastPaths`: quick local reply.
6. Same local boundary: system status.
7. Same local boundary: utility reply.
8. Same local boundary: clarification.
9. `LegacyLearningStage.learned_command`: learned trigger before heuristics.
10. `LegacyHeuristicFastPath`: unchanged German parser and registry membership.
11. Existing optional, feature-flagged planner fallback in the facade.
12. Facade: clarification for an unrecognized tool-like request.
13. Facade: conversational fallback.

All three intent sources retain the existing adaptive routing call. Learning
instructions retain their action-resolver callback, including optional legacy
planner resolution for `/learn`; that callback disables learned-trigger recursion.
`LearningEngine`, safety helpers, conversation helpers, regexes and planner code
remain unchanged. No platform/provider filtering or new OS checks are introduced.

## Decisions and wire compatibility

The stage module has no EventBus, response-layer or direct LLM dependency and does not
emit lifecycle events. `ConfirmationResolution` contains effective input and an
acceptance boolean; `LegacyRoute` retains the existing reply/intent/fallback
shape and is re-exported by the facade for compatibility. These are internal
legacy values, not public V2 contracts or event schemas.

The facade alone translates accepted confirmation metadata into the existing
`thinking / Sicherheitsbestaetigung akzeptiert` event, immediately after consuming
pending state and before checking a hard block or calling learning. Splitting
confirmation resolution from safety checking preserves timing even if a later
stage raises. Tool approval remains independently required by TurnEngine.
The existing pending-confirmation dictionary alias on AgentService is preserved.

## Characterization and limits

The first commit added 35 routing cases and ran them against the unmodified
router together with all 37 lifecycle cases (72 passed). The matrix makes every
later stage match while selecting each earlier winner in turn. German golden
cases assert exact tools/arguments; other cases cover learning, adaptive routing,
confirmation state, planner gating and fallback. Additional extraction tests
verify metadata without a response dependency, session isolation, hard blocking
after confirmation and event timing before downstream failure (43 routing cases
in total). The original 37 lifecycle tests remain byte-for-byte unchanged.

Observed pre-existing overlaps deliberately remain: `datei lesen /tmp/test.txt`
hits the utility date substring; `zeige erinnerungen 6` asks for reminder details;
short `Jarvis, oeffne Safari` hits the readiness reply. Tests characterize these
outcomes rather than silently changing NLU in this structural PR.

Tests use temporary SQLite and stub model I/O; they do not validate real model
quality, macOS automation, Windows tools or audio. No runtime dependencies,
database migration, UI, startup or native integration changes are included.

## Deferred work and rollback

- YJ2-04B: isolate the existing planner fallback; no adapter is scaffolded here.
- YJ2-05: ToolSpec V2 / ToolRuntime and later provider availability.
- YJ2-06: centralized policy in strict compatibility mode, before trust changes.
- No ActionPlan runtime, new protocol, UI/voice, packaging or performance changes.

Rollback: revert this PR's squash commit (or both commits in reverse order if
merged without squash). No data cleanup or migration rollback is necessary.
After the PR and all checks: STOP for external ChatGPT diff/architecture review.
