# YJW-01B: isolated Windows semantic clipboard reading

Initial main: `bd1f92d671ec43957e52c51ea3b673ea53ed549d`, the squash of accepted
PR #23 / YJW-01A. Its tree equals accepted head `5de1b0e`; post-merge CI
[37761568768](https://github.com/YoungJibbit95/YJarvis/actions/runs/37761568768)
passed all six checks before this branch started. Relative to architecture
baseline `dea0e9e`, it includes accepted Core 00 through 05C2, Windows
00A/B/B.1/01A and separate Product 00A/B/01A/02A/02B/02C1 work.
Parallel Product PR #24 at `f3af9b7` was open and mergeable; its 13-file
accelerator-profile delta did not overlap this provider, isolation tests or scope
documents. That Product work is not part of this PR.

During implementation, #24 was separately squash-merged as
`da5bd07a9836b53461161bb7747fa26ed83fc32a`. Its tree matches tested head `68ed8af`;
[post-merge CI 37762472306](https://github.com/YoungJibbit95/YJarvis/actions/runs/37762472306)
passed 6/6. This branch then fast-forwarded to that final base, adding exactly
the 13 non-overlapping Product files; all checks were rerun on the shared state.
No Product changes are included in this PR's own diff.

## One read-only native boundary

`WindowsClipboardReadProvider` structurally implements the unchanged `ToolProvider`.
It accepts exactly `clipboard.read`, rejects other semantic/legacy names with
`KeyError`, rejects non-Windows execution with `OSError`, and defensively reuses
the existing empty `ClipboardReadInput` model before native access. C1 still
validates input first and output last; all Domain contracts and C1/C2 stay unchanged.

One awaited `asyncio.to_thread` call keeps the entire synchronous read, lock and
cleanup sequence on one worker thread. ctypes and system DLLs are loaded lazily
there, never during provider import or instantiation. Explicit Win32 argument and
return types preserve pointer-sized handles on x64; DLL lookup is restricted to
System32. Bindings are lazily cached for process lifetime to avoid repeated DLL
loads; clipboard text is never cached. No dependency, shell, subprocess, GUI,
fallback or custom executor is added.

The sequence is OpenClipboard, check CF_UNICODETEXT (13), GetClipboardData,
GlobalLock, GlobalSize, copy bounded bytes, GlobalUnlock, CloseClipboard. Only
CF_UNICODETEXT is requested. The provider does not read or convert images, HTML,
files, RTF or custom formats. Windows itself may synthesize standard Unicode text
from its supported text formats; availability means what its Unicode API exposes,
not the original application's exact storage format. No alternate-format probing
or provider conversion is implemented.

If the Unicode-format check returns false with no fresh LastError, return
`ClipboardReadOutput(text="")`; an actually empty text has that same small semantic
result. A reported API failure raises `OSError` using Windows LastError, including
format-query errors. Required BOOL/NULL/size failures never become empty text even
when LastError is zero. LastError is cleared before each checked call.

Every successful OpenClipboard is paired with one CloseClipboard attempt in
`finally`, including absence/error paths. Every successful GlobalLock gets one
GlobalUnlock attempt in a nested `finally`. A zero unlock return with NO_ERROR is
success; nonzero means a remaining lock and is also success. The borrowed handle
is never freed or used after close. Cleanup failures propagate; if multiple calls
fail, Python exception context preserves the earlier failures. No retry is made.

Clipboard memory is untrusted. Copy no more than GlobalSize bytes, then release
resources before decoding. Find the first aligned UTF-16 NUL within that copy;
allocation padding after it is not text. Decode strictly as UTF-16LE. Missing
termination or malformed Unicode raises an explicit error, never a partial or
replacement string. Spaces, tabs, CR/LF, combining marks, BOMs and emoji remain
unchanged. There is no strip, normalization, newline conversion or length cap.

## Composition and isolation

Only `registry.register("clipboard.read", WindowsClipboardReadProvider())` grants
availability in that registry. Explicit URL plus clipboard registration yields
exactly `("clipboard.read", "url.open")`. Neither package initializer imports
providers. There is no Windows bootstrap, discovery, Legacy tool import or
application/planner wiring; the current product clipboard path stays unchanged.

The isolation exception adds exactly `providers/windows/clipboard_read.py` beside
the accepted C1, C2 and URL module. Its imports and native API attributes have
explicit allowlists. A cold-import/registration probe forbids ctypes native
access as well as the existing file-write, process, socket and DB side effects.

Tests use mocked DLL functions and test-owned byte buffers only, including on
real Windows Python. They cover exact text, empty/missing format, input/capability
rejection, ABI declarations, errors, cleanup/context, bounded reads, explicit
registration, non-Windows rejection and an actual responsive worker-thread path.
No host clipboard contents are read or written, locally or in CI.

## Limits and rollback

There is no retry/backoff, timeout or cancellation policy. Contention surfaces as
an error; cancelling the await cannot stop an already-running native read, whose
worker still owns its cleanup. Large text is not truncated and may require a large
in-memory copy. Real clipboard integration, delayed rendering, macOS, GUI, audio
and packaging are not verified by mocked tests. No policy/authorization is added.
Rollback: revert this PR; no data/configuration migration is needed. Stop after
PR/CI/handoff; do not merge or start YJW-01C, apps.open or YJ2-05C3.

## Native contract sources

Official sources checked 2026-10-08:

- [OpenClipboard](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-openclipboard) and [CloseClipboard](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-closeclipboard).
- [Format availability](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-isclipboardformatavailable), [GetClipboardData ownership/conversion](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-getclipboarddata) and [standard formats](https://learn.microsoft.com/en-us/windows/win32/dataxchg/standard-clipboard-formats).
- [GlobalLock](https://learn.microsoft.com/en-us/windows/win32/api/winbase/nf-winbase-globallock), [GlobalSize](https://learn.microsoft.com/en-us/windows/win32/api/winbase/nf-winbase-globalsize) and [GlobalUnlock](https://learn.microsoft.com/en-us/windows/win32/api/winbase/nf-winbase-globalunlock).
- [ctypes signatures, LastError and DLL loading](https://docs.python.org/3.11/library/ctypes.html).
