# YJarvis V2 architecture source

The complete supplied source of truth is stored in
[YJarvis_V2_Architecture_and_Browser_Agent_Master_Prompt.md](YJarvis_V2_Architecture_and_Browser_Agent_Master_Prompt.md).
It contains the rescue architecture, ordered roadmap, browser-agent master prompt,
review prompt, and mandatory stop gate. It describes a target architecture, not
features implemented by YJ2-00.

The imported document is byte-for-byte identical to the user-supplied file:

```text
SHA-256: 2093ae708a2dda5589a9826cc16af93118a8452e25ce7e2947c2ca4abd05e173
Git blob: c04d2d42527d3083846ac288934523f31550adf3
```

These hashes identify the imported version; an explicitly approved future revision
must update this provenance note rather than pretending to be the original.

The source baseline is `dea0e9e6a266584e9c8efaf53dd82138aecbd662`.
At the start of YJ2-00, GitHub `main` matched that SHA exactly, so no baseline
adaptation or intervening-commit review was necessary.

Do not silently rewrite the supplied architecture to fit an implementation.
Explain material deviations and obtain the user's approval. Future architecture
invariants are review criteria until introduced and tested in their own approved
roadmap steps; YJ2-00 does not retrofit them into legacy runtime code.

Operational entry points: [development setup](../development.md),
[contribution/review protocol](../../CONTRIBUTING.md), and
[agent guardrails](../../AGENTS.md).

## Accepted handoff updates (2026-10-07)

The user authorized Codex implementation and small, releasable PR cycles with
the same mandatory external-review stop gate. The original source above remains
unchanged, including its historical browser-agent wording.

- [Windows/cross-platform addendum](02_WINDOWS_CROSS_PLATFORM_ARCHITECTURE_ADDENDUM.md):
  the supplied addendum, copied verbatim; target requirements, not a Windows port.
- [YJ2-03 TurnEngine shell](turn-engine-shell.md): current extraction, preserved
  behavior, verification limits and review questions.

YJW-00 is the proposed next step after YJ2-03 external acceptance and explicit
user authorization. No next-step implementation is included here.
