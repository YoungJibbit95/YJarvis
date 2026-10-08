# YJarvis implementation guardrails

Read `docs/architecture/YJarvis_V2_Architecture_and_Browser_Agent_Master_Prompt.md`
and `CONTRIBUTING.md` before editing. The architecture describes a migration target,
not capabilities already present in the legacy application.

- Work only on the step explicitly authorized by the user. YJ2-00 through
  YJ2-05C2 and YJW-00A/B/B.1 are accepted; the current authorized step is YJW-01A:
  one isolated Windows semantic url.open provider, without production wiring.
- Use one branch and one PR per step. Never work directly on `main`, stack an
  unreviewed step, merge your own migration PR, or enable auto-merge.
- The user explicitly authorized Codex for implementation on 2026-10-07,
  superseding the historical agent/tooling restriction in the architecture source.
  Use direct GitHub operations and normal tools; no agent delegation is required.
- For YJW-01A, add only the Windows url.open provider using a native opening
  boundary without shell interpolation, plus tests and documentation. The legacy
  execution path, planner specs, approvals, routing and wire/DB names stay unchanged.
  Keep all accepted spec metadata and input/output models unchanged.
  Do not begin apps/clipboard/files providers, auto-discovery, adapters, production
  wiring, planner availability, timeout enforcement, Observations, persistence/events,
  policy, UI/voice, packaging, YJW-01B or YJ2-05C3. Import never grants availability.
- Read `docs/architecture/02_WINDOWS_CROSS_PLATFORM_ARCHITECTURE_ADDENDUM.md`.
  Core code stays OS-neutral; platform startup code belongs at the process boundary.
- Keep each cycle small and independently reviewable, with exactly one releasable
  goal. If the scope needs deep changes across multiple subsystems, stop and split
  the proposed work before proceeding. No WIP PRs or unnecessary future scaffolds.
- Read the actual current branch and compare it with the documented baseline;
  never overwrite concurrent user changes or force-push without an explicit need.
- Run the documented tests and build. Report commands and actual results. Never
  turn an unavailable macOS integration test into a claimed success.
- Inspect the final diff for unrelated changes, generated files, and secrets.
  Document out-of-scope findings rather than silently fixing them.
- Use every section of `.github/pull_request_template.md` and provide the external
  review handoff required by the architecture.

After a PR: inspect checks, fix in-scope failures, complete the handoff, and STOP.
Green CI is not approval. Start no next branch, preparatory commit, or roadmap step
until external review is complete and the user explicitly authorizes continuation.
