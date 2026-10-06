# YJarvis implementation guardrails

Read `docs/architecture/YJarvis_V2_Architecture_and_Browser_Agent_Master_Prompt.md`
and `CONTRIBUTING.md` before editing. The architecture describes a migration target,
not capabilities already present in the legacy application.

- Work only on the roadmap step explicitly authorized by the user. The initial
  authorized step is YJ2-00: baseline CI and architecture guardrails.
- Use one branch and one PR per step. Never work directly on `main`, stack an
  unreviewed step, merge your own migration PR, or enable auto-merge.
- Do not use or delegate to Codex. Use direct GitHub operations and normal tools.
- For YJ2-00, do not change runtime behavior, approvals, tools, voice, persistence,
  planning, memory, routines, or the UI. Do not scaffold YJ2-01 or later modules.
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
