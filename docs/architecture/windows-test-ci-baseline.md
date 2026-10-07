# YJW-00A: Windows test and CI baseline

## Scope and provenance

The user externally accepted YJ2-03 and authorized its squash merge. PR #5 became
`main` commit `65490d251a24287dba1329dfaa8c70102a5e41e6`; all four jobs in
[main CI 37651353894](https://github.com/YoungJibbit95/YJarvis/actions/runs/37651353894)
succeeded. That head was read again before creating `yjv2/w00a-windows-ci-baseline`.
YJW-00A changes tests, a development dependency, CI and documentation only.

The platform addendum remains the target architecture. This step does not port
startup scripts, Electron backend discovery, Ollama, tools, audio or file safety.
The accepted TurnEngine remains thin; future YJ2-04 routing should return decisions
without emitting lifecycle events. No orchestration changes are made here.

## Three baseline failures and their fixes

The focused baseline reproduced **3 failures / 48 passes** on Windows 11 Pro x64
10.0.26100 and Python 3.11.1 before changes.

| Failure | Cause and correction |
| --- | --- |
| Domain isolation import | In this Windows/Python 3.11.1 environment, an isolated `-c` child with an audit hook raises `AttributeError: 'bytes' object has no attribute 'co_filename'` while importing cached bytecode. A minimal no-op-hook `decimal` import also fails; the same probe run from a real script succeeds. The test now prepares a script before launching the child with `-I`. The domain is still first imported and validated under the complete audit guard. No preload, exception suppression or weakened assertion is used. This is a reproduced environment behavior, not a claim about all Python 3.11 releases. |
| DST fold / `Europe/Berlin` | Windows lacks the IANA database used by `ZoneInfo`. `tzdata==2026.5; sys_platform == "win32"` is added to development requirements only. Source inspection found `ZoneInfo` only in the DST test; current runtime/domain code uses caller-supplied timestamps and does not load named zones. No speculative runtime dependency is added. |
| User-home expansion | The test assumed POSIX `HOME`. It now sets `USERPROFILE` on Windows and `HOME` on POSIX, using the real path resolver. The assertion is strengthened from string-prefix matching to exact equality with the resolved expected child path. |

The isolation probe keeps all original blocked events: file writes, subprocesses,
`os.system`/`os.posix_spawn`, socket connect/bind and SQLite connections. It retains
domain import/validation/serialization and forbidden-runtime-import assertions.
The child runs in an empty working directory; the parent verifies that it stays
empty and that the prepared script is unchanged. Six negative controls attempt
real file writes (both `open` and `os.open`), subprocess creation, socket bind,
socket connect and SQLite connection, and require the expected audit rejection.
The audit hook is a regression detector, not a security sandbox.

No production module, contract, path policy, runtime dependency or test marker is
changed. There are no test skips, xfails or Windows exclusions.

Sources for platform semantics:

- [Python 3.11 `expanduser`](https://docs.python.org/3.11/library/os.path.html#os.path.expanduser)
  documents Windows `USERPROFILE` and the removal of Windows `HOME` handling.
- [Python 3.11 `zoneinfo` data sources](https://docs.python.org/3.11/library/zoneinfo.html#data-sources)
  documents the system database and first-party `tzdata` fallback.

## CI evidence boundaries

The existing Ubuntu jobs stay unchanged. Two additional jobs use the x64
`windows-2025` hosted runner and native PowerShell:

- `windows-python-tests`: Python 3.11, full runtime/dev dependency installation,
  environment/dependency recording, `pip check`, complete `python -m pytest -q`.
- `windows-desktop-checks`: Node 22, `npm ci`, typecheck, both Electron entry-point
  syntax checks, renderer build, nonempty build-output and unchanged-manifest checks.

Actions remain SHA-pinned, credentials are not persisted, permissions remain
read-only and no failure is ignored. Native validation commands use separate
PowerShell steps so a later successful command cannot hide an earlier failure.
Windows Server CI supplements local Windows 11 testing; it is not a Windows 11
interactive desktop test. Exact final commands, versions and results belong in
the PR handoff. Local setup is in [the development guide](../development.md).

CI proves installation, automated tests and static desktop checks on its actual
runners. It does not prove Electron startup, backend discovery, Ollama generation,
microphone, STT/TTS/playback, native OS tools, packaging or macOS runtime behavior.
Existing macOS instructions/support remain; no macOS integration pass is claimed.

Known risks remain: 21 npm audit findings, unlocked Python transitive dependencies,
no server-enforced main protection, and interactive platform coverage gaps. The
two new job names must also be included if an administrator later configures
required checks; workflow files alone do not enforce branch protection.

Rollback is a revert of this PR; no schema or runtime data changes need reversal.
After CI and handoff, stop for external ChatGPT review. Do not merge this PR or
start YJW-00B, other runtime-port work, or YJ2-04 without explicit authorization.
