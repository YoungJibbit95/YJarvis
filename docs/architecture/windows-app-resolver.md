# YJW-01D: read-only Windows application resolver

`WindowsAppResolver` discovers Start Menu shortcuts and resolves a supplied display
name to an internal frozen `WindowsAppTarget(display_name: str, shortcut_path: Path)`.
It launches nothing, implements no ToolProvider and imports no Domain, Runtime,
Registry or Legacy modules. It does not change `AppOpenInput`, any of the 18 specs,
existing providers or production behavior. `apps.open` remains known in the catalog
and unavailable in a fresh registry. Package initializers remain inert.

## Source and native ownership

Discovery reads exactly `FOLDERID_Programs` (current user) and
`FOLDERID_CommonPrograms` through `SHGetKnownFolderPath`. Flags are zero (no folder
creation), the user token is NULL, and there are no environment-path fallbacks,
hard-coded installation paths, Registry scans, PATH lookups or shell queries.
DLL bindings load lazily from System32; only bindings, never inventories, are cached.

Each call initializes a NULL output pointer, checks the signed 32-bit HRESULT,
copies the returned Unicode string into Python, and calls `CoTaskMemFree` in a
`finally` block even if the API or conversion failed. Freeing NULL is valid.
No native pointer escapes. This API reports errors through HRESULT, not LastError.
Failure or an absent path raises `WindowsAppDiscoveryError`; Python/native boundary
exceptions propagate, and a cleanup exception retains its predecessor as context.

Only absolute drive paths are accepted: UNC, device paths and parent traversal are
rejected. `GetDriveTypeW` excludes mapped network/unknown drives before enumeration.
Local removable, fixed, optical and RAM drives are accepted; no assumption about
the system drive letter or Windows display language is made.

## Inventory and matching

Only regular `.lnk` files beneath those roots become targets. The display name is
the filename without its final extension. Shortcut contents are never opened,
parsed or followed; `.url`, executables, scripts and other formats are excluded.

Roots and their ancestors are checked without following their final link component.
Symlinks and Windows reparse points are skipped, including directories and shortcut
files. Each directory is checked again before enumeration; entries use
`stat(follow_symlinks=False)`. Missing/unreadable roots or enumeration/stat errors
propagate rather than returning a partial inventory that could hide ambiguity.
No directories, files or metadata are created or persisted.

Each inventory is fresh. Roots and entries are sorted explicitly, and final results
are sorted by `(display_name.casefold(), display_name, path.casefold(), path)`.
The same literal path found through repeated/overlapping roots is included once.
Distinct paths with the same normalized display name remain distinct candidates.

`resolve(name)` compares the entire supplied string using Python `str.casefold()`.
It does not trim, strip wrappers, normalize Unicode composition, append extensions,
translate aliases or use substring/fuzzy/LLM matching. Python casefold is an explicit
comparison policy, not a claim to reproduce Windows filesystem collation. For
example, `Straße` matches `STRASSE`, while composed/decomposed accents remain distinct.
Non-string input raises TypeError; there is no second Domain grammar.

- One match returns the frozen target, retaining its actual filename spelling.
- No match raises `WindowsAppNotFoundError`, without fallback.
- Multiple distinct shortcut paths raise `WindowsAppAmbiguousError`. Its internal
  `candidates` tuple is deterministic; its message reports the name/count, not paths.
  No user/system/first-result preference hides duplicates.

## Isolation, verification and limits

Import and instantiation perform no DLL load or scan. Non-Windows execution fails
before native/filesystem discovery. The existing Domain-consumer allowlist is
unchanged: the resolver needs no exception. Its own AST test restricts it to exact
stdlib/native dependencies; cold-import audit tests prohibit native calls, scans,
process/network/DB access and writes, including negative controls.

Automated tests use temporary directory trees and mocked native pointers/buffers
on all platforms. They cover both Known Folder IDs, memory ownership on success and
failure, exact matching, ambiguity, order independence, filtering, reparse/link
exclusion, read failures, fresh inventories and unchanged `apps.open` availability.

Local Windows read-only verification found **371 shortcuts** across both Known
Folder roots. Verified examples were **Git Bash, Git GUI and Microsoft Edge**, also
resolved with lowercase names. Repeated inventories were identical and all shortcut
sizes/mtime values were unchanged. A Python audit guard blocked process launches,
network/DB access and filesystem mutations. No application was opened and no
personal paths or shortcut contents were published. No macOS integration, GUI,
audio or packaging test is implied.

YJW-01D resolves applications represented by discoverable Windows Start Menu
shortcuts. It is not a complete installed-application inventory. Local Start Menu
provenance does not prove a shortcut's contents, destination or launch safety.
Redirected/network/reparse roots are deliberately unsupported in this slice.
Path-based enumeration is not an atomic filesystem snapshot: concurrent replacement
can race metadata checks, and a returned path can become stale. The internal target
is discovery data, not a tamper-proof identity or authorization to execute. This
step provides no launch-time guarantee and implements no future launch checks.

The resolver remains synchronous; a future separately reviewed provider decides
the worker boundary. No thread service, timeout, retry, availability registration,
apps.open provider or YJW-01E work is included. Rollback is a revert of this step;
there is no runtime configuration, data migration or personal data to remove.

## Official contracts checked before implementation

- [SHGetKnownFolderPath](https://learn.microsoft.com/en-us/windows/win32/api/shlobj_core/nf-shlobj_core-shgetknownfolderpath)
  and [Known Folder IDs](https://learn.microsoft.com/en-us/windows/win32/shell/knownfolderid)
- [CoTaskMemFree](https://learn.microsoft.com/en-us/windows/win32/api/combaseapi/nf-combaseapi-cotaskmemfree)
  and [GetDriveTypeW](https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-getdrivetypew)
- [Python directory enumeration and stat](https://docs.python.org/3.11/library/os.html#os.scandir)
  and [Windows reparse attributes](https://docs.python.org/3.11/library/stat.html#stat.FILE_ATTRIBUTE_REPARSE_POINT)
