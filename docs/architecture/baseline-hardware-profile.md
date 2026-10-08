# YJUX-02C1: read-only baseline hardware profile

This step adds a small local system snapshot to setup. Hardware, the accepted
model catalog and readiness remain three independent data sources. There are
no recommendations, model selections, GPU probes or installation operations.

## Baseline and ownership

Base main: `28c30f6f460076e4f5f0c049b256a53a0541288b`. The user's explicit
Product authorization takes precedence over the Core-step labels in repository
guidance. The complete shared gate finished before this branch began:

- Core #19 squash main `ac5b73d`: [6/6 CI](https://github.com/YoungJibbit95/YJarvis/actions/runs/37753022180).
- Product #20 synchronized head `8218a43`: exactly the six expected Core files,
  unchanged Product patch; [6/6 CI](https://github.com/YoungJibbit95/YJarvis/actions/runs/37753270892).
- Product #20 squash main `28c30f6`: identical combined tree;
  [6/6 CI](https://github.com/YoungJibbit95/YJarvis/actions/runs/37753542892).

Compared with architecture baseline `dea0e9e`, this includes accepted CI,
domain/persistence/orchestration extractions, Windows startup, typed capability
contracts/catalog/kernel, and Product foundations/shell/readiness/model browsing.
Core PR #21 (`c0617da`) affects separate provider-registry/test/guidance files;
no shared setup/API file was changed there at inspection. Its checkout
and concurrent README modification are untouched.

## Contract and system boundary

`HardwareProfile` is strict, immutable and forbids extra fields. Numeric fields
are JSON-safe integers; CPU count and total RAM must be positive or null. Free
storage can be zero for a full filesystem; null alone means unknown.

| Field | Meaning |
| --- | --- |
| `platform` | windows, macos, linux, or unknown; no guessed OS version |
| `architecture` | x86_64, arm64, other, or unknown |
| `logical_cpu_count` | OS-reported logical CPUs, not physical cores or performance |
| `total_memory_bytes` | OS-reported physical RAM, not currently free RAM, swap or VRAM |
| `available_storage_bytes` | Available bytes at the existing app runtime directory |
| `storage_path_scope` | Always app_runtime_directory; no user path is exposed |

Platform-specific reads live only in `setup_hardware.py`, outside the neutral
Core/domain/runtime. The process boundary injects its already resolved
`config.runtime_dir`. No probing happens at module import. Each failed probe
returns an explicit unknown without erasing successful independent measurements.

- Platform uses `sys.platform`; CPU count uses `os.cpu_count()`.
- Windows architecture uses the native-machine result of
  [IsWow64Process2](https://learn.microsoft.com/en-us/windows/win32/api/wow64apiset/nf-wow64apiset-iswow64process2).
  Missing/failed APIs produce unknown. Other hosts use `os.uname().machine`.
  Emulation can affect the architecture reported to a POSIX process; this is not
  accelerator or instruction-set capability verification.
- Windows RAM reads `ullTotalPhys` through
  [GlobalMemoryStatusEx](https://learn.microsoft.com/en-us/windows/win32/api/sysinfoapi/nf-sysinfoapi-globalmemorystatusex)
  with the documented 64-byte structure and checked success result.
- Linux RAM uses positive `SC_PHYS_PAGES` times `SC_PAGE_SIZE` via
  [os.sysconf](https://docs.python.org/3.11/library/os.html#os.sysconf).
- macOS calls read-only `sysctlbyname("hw.memsize")` through the fixed OS library
  `/usr/lib/libSystem.B.dylib`, with a checked uint64 buffer and no new value.
  [Apple documents hw.memsize as RAM bytes](https://developer.apple.com/documentation/kernel/1387446-sysctlbyname/determining_system_capabilities).
  Its ABI/error paths are mocked in tests; a real macOS run remains NOT RUN.

There is no `platform.machine()`/`platform.uname()` fallback: Python 3.11's
Windows implementation can call `ver` through a subprocess. No subprocess,
PowerShell, command-line utilities, network client or new dependency is used.

## Storage scope

The snapshot uses [shutil.disk_usage](https://docs.python.org/3.11/library/shutil.html#shutil.disk_usage)
at the **existing configured runtime directory**. This is an app-data filesystem
measurement, not a chosen future installation directory, free space at every
configured model path, or a reservation. No settings are added and no directory
is created. Missing/inaccessible/relative paths return null; there is no ancestor
or home-directory fallback. UNC paths are skipped; Windows also requires
GetDriveTypeW to report DRIVE_FIXED before filesystem inspection. POSIX values
describe the configured mounted filesystem visible to the backend.

Container/VM limits, quotas, mount configuration and other processes can affect
reported resources. Counts and RAM do not guarantee what inference may allocate.
Free storage is volatile and must be checked again by any future installer.

## API and UI

GET `/v1/setup/hardware` returns the profile with `Cache-Control: no-store`.
The small synchronous probe runs in FastAPI's existing worker pool. There is no
cache, periodic scan or background discovery service. POST/PUT/PATCH/DELETE/HEAD
are unsupported (405) and do not invoke the probe. Catalog and readiness routes
keep their behavior, as do settings, database, approvals and chat gating.

The "Dieses System" disclosure is available in first run and the existing app
setup notice. Opening it fetches and strictly validates its own DTO. Loading,
eight-second abort timeout, error and retry are local to that component; closing
it aborts its request. Unknown values say "Unbekannt", known byte quantities use
GiB (2^30 bytes), and small positive quantities are not rounded to a false zero.
No performance rating or model recommendation is inferred.

## Evidence and limits

Windows local validation: 1119 Python tests, 196 focused hardware/API/readiness
tests, 68 DTO/presentation tests and 22 startup tests passed. Pip check, Ruff,
npm ci, typecheck, Electron entry-point syntax checks and production build passed.
The existing small Node loader is shared by catalog and hardware tests; both
run in Linux and Windows desktop CI. No test framework/dependency was added.

Windows renderer verification used the real backend and an isolated temporary
runtime/database. The real profile returned x86_64, 12 logical CPUs,
34,129,563,648 bytes RAM and approximately 13.9 GiB free at that temporary app-data
location. Independent Windows CIM/drive reads agreed (storage changes over time).
First-run and normal-app reopening, keyboard focus, unknowns, malformed response,
timeout and successful retry were checked. Layouts at 1320x860, 960x760 and
480x780 had no horizontal overflow. Catalog stayed loaded and chat stayed blocked
when hardware failed. Readiness JSON, catalog JSON and the complete logical
SQLite dump were identical before/after first-run browsing and error checks.
A preview-only Python audit hook recorded zero forbidden process, network or
write attempts during real hardware requests. Test controls are outside Git.

Electron GUI, actual macOS/Apple Silicon, HiDPI, inference/audio and packaged-app
verification: **NOT RUN**. Existing npm audit reports 21 findings; dependencies
are unchanged. The existing unavailable Windows voice executable surfaced in the
normal-app preview and was not repaired in this step.

## Rollback and stop

Revert this step's commit to remove its additive transport, UI and tests.
No migration, model cleanup or personal-data deletion is needed. GPU/VRAM,
CUDA/Metal/DirectML, ranking/recommendations, installers/downloads/progress,
checksums, auto-selection, packaging and Core provider/runtime work are excluded.
YJUX-02C2 and all later work require external review and explicit authorization.
