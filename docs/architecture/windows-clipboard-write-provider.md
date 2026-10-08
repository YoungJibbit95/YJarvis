# YJW-01C: isolated Windows semantic clipboard writing

`WindowsClipboardWriteProvider` handles exactly `clipboard.write`. It composes
explicitly with the unchanged C1 ToolRuntime and C2 CapabilityProviderRegistry.
The accepted `ClipboardWriteInput(text: StrictStr)` and `NoDataOutput` contracts,
all 18 specs, existing providers and legacy production execution remain unchanged.
Import and instantiation grant no availability; only explicit registry registration
does. There is no production wiring, auto-discovery, adapter, policy or approval work.

## Native boundary and ownership

Capability identity, Windows platform and the existing input model are checked
before entering `asyncio.to_thread`. One worker performs the entire synchronous
transaction, including encoding, window creation and every cleanup call. Package
initializers stay inert; System32 DLL bindings load lazily, with explicit pointer-sized
signatures and thread-local LastError handling. Only bindings are cached, never
clipboard data, allocations or windows.

The owner is a fresh, invisible message-only HWND created using the predefined
`STATIC` system class and `HWND_MESSAGE`. It belongs to this process and worker,
not Electron, the desktop or another application. No custom window procedure,
permanent window service or thread infrastructure is introduced. Data is rendered
immediately in an HGLOBAL; delayed rendering is never requested. Consequently no
application render-message handler is needed for this transaction. This design is
based on the immediate versus delayed rendering contracts linked below.

The acquisition order is:

1. Create owner HWND, then `OpenClipboard(owner)`.
2. `EmptyClipboard()` assigns clipboard ownership to that window.
3. `GlobalAlloc(GMEM_MOVEABLE, size)` creates storage owned by the provider.
4. `GlobalLock`, copy exact UTF-16LE bytes plus a terminating UTF-16 NUL, then unlock.
5. `SetClipboardData(CF_UNICODETEXT, handle)` transfers the HGLOBAL to Windows on success.
6. Close the clipboard and destroy the owner on the same worker thread.

Before step 5 succeeds, every path with an acquired allocation attempts `GlobalFree`.
After it succeeds, the provider never frees or modifies that allocation, including
when closing the clipboard or destroying the owner fails. Destroying the window
ends window ownership; it does not give the provider ownership of the transferred
memory again. `NoDataOutput()` is returned only after the full transaction and
cleanup succeed. There are no success flags, messages or Observations.

## Text and failure semantics

The payload is exactly `text.encode("utf-16-le") + b"\x00\x00"`. Spaces, tabs,
CR/LF, emoji, combining characters and a BOM supplied as text remain unchanged.
An empty string writes just the terminator. There is no length limit, coercion,
normalization or additional input grammar. Embedded NULs are copied exactly, but
CF_UNICODETEXT consumers can interpret the first NUL as the end of text. A lone
surrogate raises Python's encoding error before loading DLLs or acquiring resources.

Windows clipboard writing is **not transactional**. After successful
`EmptyClipboard`, the previous contents may already be lost. Later allocation,
copy or transfer failure does not restore them. Conversely, failure during cleanup
after a successful transfer can report an error even though the new data was written.
There is no clipboard snapshot, restore, retry, backoff or timeout.

Each acquired resource has a nested `try/finally` boundary:

| Failure | Cleanup attempted |
| --- | --- |
| Window creation | None; no window was acquired |
| OpenClipboard | Destroy owner |
| EmptyClipboard / allocation | Close clipboard, destroy owner |
| GlobalLock | Free provider-owned allocation, close, destroy |
| Copy / unlock | Unlock after an acquired lock; free before transfer, close, destroy |
| SetClipboardData | Free provider-owned allocation, close, destroy |
| CloseClipboard after transfer | Destroy owner; never free Windows-owned storage |
| GlobalFree / DestroyWindow | Propagate the cleanup error; no silent recovery |

Native return values follow their individual contracts: `GlobalFree == NULL` is
success, and `GlobalUnlock == 0` with zero LastError means the final lock was released.
LastError is cleared before each checked API call. A nonzero unlock result means
the allocation remains locked; this fresh allocation should have only our one lock,
so that unexpected state fails before transfer and attempts free without another
unlock. Other BOOL/handle failures raise even if LastError is zero. Cleanup errors
remain visible, with earlier exceptions preserved in Python `__context__` chains.
An OS cleanup failure can leave a resource outstanding; it is reported, not retried.

Contention is an immediate native error. Cancelling an awaiting coroutine cannot
stop an already running `to_thread` transaction; its worker still executes cleanup
and may complete the write. Cancellation enforcement is outside this step.
Non-Windows execution fails before DLL loading or native operations. Unknown
semantic IDs and legacy aliases raise `KeyError` without native calls.

## Verification and isolation

Provider tests replace DLL loading and every native entry point on all hosts,
including real Windows Python. They use high-valued test handles and owned test
buffers; they never read or mutate the host clipboard. Tests cover exact bytes,
invalid/forged models, all other IDs, allocation transfer, the complete failure and
cleanup chain matrix, and event-synchronized worker responsiveness. Explicit
registration of URL open, clipboard read and clipboard write exposes exactly those
three IDs; a fresh registry remains empty.

The AST/cold-import gate adds only `providers/windows/clipboard_write.py` alongside
the four previously accepted V2 consumers. It forbids eager provider imports,
legacy imports, DB, network, subprocess, file writes and native calls during
import/instantiation/registration. No directory-wide exception is added.

Local verification additionally created and destroyed the real message-only owner
on one worker, checking process/thread ownership and invisibility while all
clipboard entry points were guarded against calls. This does **not** establish
end-to-end native clipboard behavior. No real host clipboard, macOS integration,
GUI, audio or packaged application test was performed.

Rollback is a revert of this isolated step; no data migration or runtime
configuration is required. Reverting code cannot undo a clipboard write performed
by an explicitly composed caller. YJW-01D, apps.open, YJ2-05C3, production wiring,
retry/timeout and additional providers remain blocked pending separate approval.

## Contract references

Microsoft sources checked before implementation:

- [OpenClipboard](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-openclipboard),
  [EmptyClipboard](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-emptyclipboard),
  [SetClipboardData](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-setclipboarddata)
- [GlobalAlloc](https://learn.microsoft.com/en-us/windows/win32/api/winbase/nf-winbase-globalalloc),
  [GlobalLock](https://learn.microsoft.com/en-us/windows/win32/api/winbase/nf-winbase-globallock),
  [GlobalUnlock](https://learn.microsoft.com/en-us/windows/win32/api/winbase/nf-winbase-globalunlock),
  [GlobalFree](https://learn.microsoft.com/en-us/windows/win32/api/winbase/nf-winbase-globalfree)
- [CreateWindowExW](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-createwindowexw),
  [DestroyWindow](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-destroywindow),
  [message-only windows](https://learn.microsoft.com/en-us/windows/win32/winmsg/window-features#message-only-windows),
  [WM_RENDERALLFORMATS](https://learn.microsoft.com/en-us/windows/win32/dataxchg/wm-renderallformats)
