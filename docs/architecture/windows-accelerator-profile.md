# YJUX-02C2A: read-only Windows accelerator profile

This step adds Windows adapter facts to setup. Baseline hardware, accelerators,
model catalog and readiness remain independent sources. No model suitability,
capability availability or performance is inferred from these descriptors.

## Baseline and ownership

Base main: `e79893fd17bd4fe967b9a31873d9744d7d050e76`. The user's explicit Product
authorization supersedes the historical Core-step labels in repository guidance.
The required shared merge gate completed before this branch began:

- Core #21 squash main `16f4be5`: [6/6 CI](https://github.com/YoungJibbit95/YJarvis/actions/runs/37758037502).
- Product #22 synchronized head `122fa8c`: exactly the six expected Core files;
  unchanged Product patch; [6/6 CI](https://github.com/YoungJibbit95/YJarvis/actions/runs/37758334855).
- Product #22 squash main `e79893f`: identical combined tree;
  [6/6 CI](https://github.com/YoungJibbit95/YJarvis/actions/runs/37758573535).

Compared with architecture baseline `dea0e9e`, main includes accepted CI,
domain/persistence/orchestration/router/planner extractions, Windows startup,
typed capability contracts/catalog/kernel/provider registry, and Product
foundations/shell/readiness/model browsing/baseline hardware. The parallel Core
checkout moved to `yjv2/w01a-windows-url-provider` during this step. Its PR #23
(`5de1b0e`) changes eight separate provider/test/guidance files; its concurrent
README work is also untouched. No setup/API overlap was observed.

## Separate contract

GET `/v1/setup/accelerators` returns a strict, frozen `AcceleratorProfile` with
`Cache-Control: no-store`. Its immutable tuple contains at most 64 adapters.
Unknown fields, coerced numeric values, invalid classifications and unavailable
profiles with adapter entries are rejected. The frontend validates the same shape.

| Field | Meaning |
| --- | --- |
| `status` | `available`: enumeration completed, including a valid empty list; `unknown`: Windows enumeration could not be read reliably; `unsupported`: non-Windows |
| `adapters[].display_name` | Nonblank native description, up to 128 Unicode characters; plain text, no inferred vendor |
| `adapters[].dedicated_video_memory_bytes` | DXGI dedicated video memory; integer bytes or null |
| `adapters[].shared_system_memory_bytes` | DXGI maximum system memory this adapter may consume; integer bytes or null |
| `adapters[].classification` | `hardware`, `software`, or `unknown`, solely from native flags |

Memory values are nonnegative JSON-safe integers through `2^53 - 1`. Native zero
is preserved; null means unrepresentable/unknown, never zero or an estimate.
Shared system memory is **an upper bound**, not reserved memory, free memory,
dedicated VRAM or guaranteed inference capacity. It is not added to dedicated
memory or summed across adapters. Dedicated system memory is not exposed or folded
into another field. No RAM-based formula is used.

## Native boundary

`setup_accelerators.py` is a Product/Setup inspector, outside Domain, ToolRuntime,
Provider Registry, Planner and Policy. Imports never probe. Non-Windows returns
unsupported before referencing Windows-only ctypes loading/calling conventions.
There is no macOS Metal/unified-memory or Linux GPU implementation.

Each GET creates one DXGI factory, enumerates its snapshot and releases it.
It loads the fixed system `dxgi.dll` restricted to System32, with explicit
HRESULT, argument and calling-convention definitions. Fixed-width WCHAR, UINT,
LONG and pointer-sized SIZE_T match the native descriptor ABI. There is no new
dependency, shell, subprocess, command-line utility, network client, filesystem
write, settings/database access, configuration or device/context creation.

The implementation follows these primary sources:

- [CreateDXGIFactory1](https://learn.microsoft.com/en-us/windows/win32/api/dxgi/nf-dxgi-createdxgifactory1)
  creates the requested IDXGIFactory1 interface. Its reference is released after
  success on every exit path.
- [EnumAdapters1](https://learn.microsoft.com/en-us/windows/win32/api/dxgi/nf-dxgi-idxgifactory1-enumadapters1)
  returns one owned adapter reference per successful call. Each is released in
  `finally`, including failed descriptor reads/normalization. Only
  DXGI_ERROR_NOT_FOUND ends enumeration successfully. Other failures discard the
  entire partial list. More than 64 entries produces unknown after releasing
  the extra entry; there is no unbounded loop.
- [GetDesc1](https://learn.microsoft.com/en-us/windows/win32/api/dxgi/nf-dxgi-idxgiadapter1-getdesc1)
  supplies [DXGI_ADAPTER_DESC1](https://learn.microsoft.com/en-us/windows/win32/api/dxgi/ns-dxgi-dxgi_adapter_desc1).
  Blank, unterminated or invalid UTF-16 descriptions fail closed to unknown.
- [DXGI_ADAPTER_FLAG](https://learn.microsoft.com/en-us/windows/win32/api/dxgi/ne-dxgi-dxgi_adapter_flag)
  identifies software adapters on the supported Windows 11 target. NONE maps to
  hardware, SOFTWARE to software; reserved/unexpected combinations remain unknown.
  Description strings never determine classification. Software entries are shown.
- The [Microsoft SDK header](https://github.com/microsoft/win32metadata/blob/main/generation/WinSDK/RecompiledIdlHeaders/shared/dxgi.h)
  defines IID_IDXGIFactory1 and inherited COM vtable order: Release slot 2,
  EnumAdapters1 slot 12 and GetDesc1 slot 10 (zero-based).

Adapter order is DXGI enumeration order, not a preference or performance ranking.
Factory/driver errors are not exposed as raw implementation details. Driver and
VM environments can change descriptors; a new GET takes a fresh snapshot.

## API and UI behavior

Only GET invokes this inspector. Unsupported methods return 405 without invoking
it. The synchronous native call runs in FastAPI's existing worker pool; there is
no scheduled/background scanner or persistent cache. Closing the UI or its
eight-second timeout aborts the HTTP client and ignores late results; it cannot
cancel an already executing native driver call. No backend hard timeout is claimed.

Opening "Dieses System" loads baseline hardware and the "Grafik / Beschleuniger"
subsection independently, both in first run and the existing app status disclosure.
Its loading/error/retry state is local. A successful empty enumeration differs
from a read failure and from an unsupported OS. Memory uses binary GiB; unknown
says "Unbekannt", and small positive quantities do not round to a false zero.
Software adapters are explicitly labeled. No install, selection or recommendation
action is added. Baseline HardwareProfile and readiness/chat gating are unchanged.

## Validation and limitations

Windows local: 1188 Python tests passed, including 41 new contract/native/API tests;
89 setup DTO/presentation tests and 22 startup tests passed. Pip check, Ruff,
npm ci, typecheck, Electron entry-point syntax checks and production build passed.
The Node tests run in both Linux and Windows desktop CI. Real-host probe smoke is
part of the Python suite: Windows calls DXGI without requiring a GPU or nonempty
result; non-Windows requires unsupported. Mocked ctypes COM vtables verify ABI,
IID, method slots, native this pointers, HRESULT handling and Release calls.

The real Windows probe here returned RTX 3070 Ti (hardware, 8,406,433,792 dedicated
bytes) and Microsoft Basic Render Driver (software, zero dedicated bytes). Each
reported a 17,064,781,824-byte shared-system-memory upper bound. These are native
descriptor values, not marketing capacity, a benchmark or a suitability claim.

Renderer verification used the real backend in an isolated temporary runtime.
First-run and normal-app views, keyboard opening, malformed DTO, HTTP 500, native
unknown, unsupported, eight-second timeout and successful retry were checked.
At 1320x860, 960x760 and 480x780 there was no horizontal overflow. Accelerator
failures left the baseline display, three catalog cards and readiness intact;
the normal app's send button stayed disabled. Readiness/catalog JSON and the
complete logical SQLite dump matched before/after first-run inspection. Stable
baseline fields also matched (free storage is volatile). A preview-only Python
audit hook recorded zero process, network or write attempts for real accelerator
requests. Preview fixtures and screenshots stay outside Git.

Real macOS/Apple Silicon, Windows ARM64/32-bit, Electron GUI, HiDPI, packaging,
inference/audio and performance verification: **NOT RUN**. The existing npm audit
reports 21 findings, and normal-app preview still reports the unavailable Windows
voice executable; both remain outside this step with dependencies unchanged.

## Rollback and stop

Revert this step's commit to remove the additive endpoint, UI and tests. There is
no data migration or personal-data cleanup. CUDA/DirectML capabilities, macOS/Linux
GPU probing, ranking/recommendations, model selection/download/install, benchmarks,
packaging and Core provider/runtime changes are excluded. Stop after the PR,
six green checks and external-review handoff. No auto-merge or YJUX-02C2B work.
