# YJNX-01A: inert Python Nexus Local Protocol contracts

## Authorization, baseline and normative reference

The user explicitly authorized only YJNX-01A on 2026-10-18. This supersedes
historical current-step labels for this isolated contract package, not the
remaining architecture, review or runtime gates.

YJarvis base main: 68fa1df76e096dce45ee0c42f39012df0efe27a3. No drift from
the RFC's YJarvis baseline. Relative to the original V2 baseline dea0e9e,
main already contains the accepted domain/input/output/kernel/registry work,
Windows foundations/providers/resolver, persistence and routing extractions,
and separate product/setup/voice/communication changes through YJCORE-01.
This step starts from that inspected main, not from a concurrent approval-claim
worktree. No changes from another branch are included.

Normative authority:

- [Nexus PR #454](https://github.com/YoungJibbit95/Nexus-Ecosystem/pull/454),
  externally accepted head e52f536c1f431dbae676e7d81c99aadb5f135630.
- Nexus merged main reference 7721614732ce11042a67f5a44438457286fa8b32.
  Both commits have tree e12f3571e867167e54c8f45ab29629d78912e0aa.
- [Accepted TS contract and semantics](https://github.com/YoungJibbit95/Nexus-Ecosystem/tree/7721614732ce11042a67f5a44438457286fa8b32/packages/nexus-core/src/local-integration).
- [Unmodified five-file corpus](https://github.com/YoungJibbit95/Nexus-Ecosystem/tree/7721614732ce11042a67f5a44438457286fa8b32/packages/nexus-core/test/fixtures/local-integration-v1),
  copied byte-for-byte to tests/fixtures/local-integration-v1/.
- YJNX-01 RFC v0.2.1 SHA-256
  b64c3c4483435f06f7af7c5dd126d49c4e937eeb8bdcea6b23a4097680b59c74,
  synthesis SHA-256
  0948e8219ef1d8a160f2d9eba37231df7b7486e4dfd9005f5d9947b16074c018,
  and the supplied G0-A decision/work packet. G0-A is architecture-only.

Protocol: nexus.local.v1. Schema/fixture version: **2.0.0**.
Schema ID: urn:nexus:local:wire:2.0.0. MagicDescriptorV1 remains version 1.
The corpus directory's v1 denotes the protocol, not the schema major.

## Isolated package and exact catalog

The jarvis_agent.nexus_contracts package has an inert initializer and explicit
submodules:

| Module | Responsibility |
| --- | --- |
| constants.py | Ten fixed method/capability pairs and closed wire enums |
| primitives.py | Scalar bounds, Gregorian dates/instants, JSON integers, uniqueness |
| types.py | Context, scope/account, entity references, snapshots, descriptors, receipts |
| messages.py | Closed, method-correlated request/response models |
| canonical.py | JCS UTF-8 bytes and strict canonical-corpus decoding |
| validation.py | Stateless named-contract TypeAdapters and document byte limit |

No existing Domain, ToolSpec, input/output, wire/DB or legacy model changes.
No import from production code. No capability registration, client, socket,
discovery, Vault, pairing, approval, policy, persistence, LLM, UI or audio work.
The package does not read corpus files on import. Tests read synthetic fixtures.
Static import gates and an audited cold-process test with negative controls
supplement the existing unchanged architecture gates.

The mapping is explicit immutable data, not an executable registry:

| Method | Future capability |
| --- | --- |
| system.hello | nexus.system.hello |
| capabilities.list | nexus.capabilities.list |
| mutation.status | nexus.mutation.status |
| notes.query | nexus.notes.query |
| tasks.query | nexus.tasks.query |
| reminders.query | nexus.reminders.query |
| planning.queryRange | nexus.planning.queryRange |
| flux.getAttention | nexus.flux.getAttention |
| notes.create | nexus.notes.create |
| tasks.create | nexus.tasks.create |

All 49 named definitions in the accepted JSON Schema have counterparts.
parse_contract(name, raw_json_value) returns validated typed data or raises
ContractValidationError; unknown schema names raise KeyError.
validate_contract(...).valid reports structure/format validity only.
Pydantic models reject extra fields and coercion. They retain the original
timestamp strings, fractional precision, offsets and content newlines.
to_wire()/model serialization omit absent optional fields without inserting
defaults. Explicit null is accepted only where the Nexus schema allows it.
Models are frozen, and model instances are revalidated. Contained arrays remain
ordinary JSON lists; the models are neither permission tokens nor signed records.

## Semantics preserved, with no runtime claim

- runtimeGeneration is independent of explicit Library/Workspace scope.
  Missing scope, implicit null selection and extra identity fields are rejected.
  Well-formed context/profile/account values do not authenticate a caller.
- Capability nexusState is exclusively Nexus-owned
  known/offered/ready/authorized. No Jarvis verdict/approval is inferred.
- Reads use status=accepted, consistency=current and separate durability.
  Snapshot/cursor bindings describe data; validation cannot prove current drafts,
  unchanged membership, cursor signatures, expiry or authorization.
- Flux permits a **nonempty** bounded prefix with truncated=true and
  nextCursor=null; complete/empty snapshots use false/null. No Flux paging.
- Receipt.revision is {source:"planning-document",value:<safe integer>},
  tied semantically to the original command receipt and origin dataset.
  It is not a note ETag or a sampled current planning counter.
- Status queries retain the original action/key/digest/origin while the request
  carries the current context after restart. not_found, unknown_outcome,
  expired_or_unknown and recovery_pending remain distinct uncertain states.
  Nothing retries, reconciles, deduplicates, persists or executes here.
- A correctly typed receipt is not proof of a durable write, retention,
  authoritative revision lookup, exactly-once effects or crash recovery.
- Timezone existence/DST/offset agreement, receipt-time ordering, actual schema
  compatibility for a well-formed peer hash and cross-message equality are future
  boundary/domain checks. They are not extra schema rules invented by Python.

No contract deviations are intended. Shared fixtures compare validity/case IDs,
not language-specific error text or diagnostic ordering.

## JCS and exact hashes

New runtime dependency: **rfc8785==0.1.4**, pinned in both existing Python
manifests. This is a small pure-Python, dependency-free
[RFC 8785 implementation](https://github.com/trailofbits/rfc8785.py).
It avoids an independently invented ECMAScript number formatter; the stdlib
JSON encoder alone does not supply JCS spelling/key order.
Only the isolated contract package imports it.

The wrapper rejects non-JSON types, cycles, lone surrogates, non-string keys,
nonfinite numbers and depth greater than 64. Binary64 parsing matches
ECMAScript JSON numbers; integer schema fields separately enforce the safe range.
Direct Python integers outside the safe range must be exactly binary64
representable. UTF-16 key order and ECMAScript number formatting come from JCS.
No Unicode or content-newline normalization takes place.

canonical_bytes has no terminal LF. Corpus files have exactly one terminal LF.
The decoder rejects BOM, malformed UTF-8, duplicate keys, CRLF, alternate number
spellings and extra whitespace. The .gitattributes rule pins these files to LF.
The 128 KiB wire limit applies to canonical document bytes, not fixture files.

| File | Bytes | SHA-256 |
| --- | ---: | --- |
| canonicalization.json | 1847 | 1c71cda918199b86a8aa265089c53fa9fdcf4cba8f95032d1af2b3de932c916e |
| conformance.json | 161840 | 006a2e5d78d14355ef0de53cbae004dc4f231aac4b9fafd4e3554121da67d46a |
| scenarios.json | 65574 | bd470c052e28d430a05651c184c5dee02d9c553769479584951f054dd2eb5ddf |
| wire-v1.schema.json | 51611 | 65822eb37fffd728c6fb4e8d835ab7d5d9f93ad41365ab694adb11166ff43a2d |
| manifest.json | 746 | fd3d98628bb0676f6b1521f979bd819b8825addb47387cc5bb3e59cd2c2bf442 |

Corpus SHA-256:
8bb75002fcf8af4f1be76b3043aa868168bea2eee40dad2870f6140f03d5185f.
Sort the four payload filenames in ASCII order. Hash their exact bytes including
the final LF, then concatenate lowercase SHA-256, two spaces, filename and LF
per entry and hash those UTF-8 bytes. The manifest excludes itself; its separate
file hash above pins the fifth file without a circular digest.

## Conformance and reproducible verification

| Evidence | Python | Accepted TypeScript reference | Meaning |
| --- | ---: | ---: | --- |
| Shared schema cases | 203/203 | 203/203 | Same case IDs and validity |
| Shared canonicalization vectors | 7/7 | 7/7 | Same text, UTF-8 hex and SHA-256 |
| Original corpus files | 5/5 | Same immutable source | Byte/hash parity including manifest |
| Deterministic schema mutations | 26,195 | Compared directly | Zero validity mismatches |
| Seeded finite Binary64 samples | 10,000 | Compared directly | Zero spelling mismatches |
| Descriptive runtime requirements | 44 fixture shapes | Same corpus | **Runtime not executed or proven** |

Run the committed Python checks from the root:

~~~powershell
.\.venv\Scripts\python.exe -m pytest -q tests/nexus_contracts
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m ruff check apps/agent/jarvis_agent tests
~~~

The optional offline comparison script accepts an existing copy of the three
normative TS source files. It verifies their Git blob hashes before compiling,
uses the installed TypeScript compiler and Node, compares the same corpus,
then derives deterministic mutations/numbers in a disposable directory.
It never downloads, changes goldens or connects to Nexus:

~~~powershell
.\.venv\Scripts\python.exe tests/nexus_contracts/compare_reference.py --reference-source '<pinned Nexus local-integration source directory>' --node '<Node 22 executable>'
~~~

Implementation verification used native Windows, Python 3.11 and Node 22.23.3.
Desktop checks are npm ci, npm run typecheck, npm run build,
node --test tests/desktop/*.test.cjs tests/packaging/*.test.cjs,
npm run test:startup and the existing Electron syntax checks. On this host,
the default nested npm/cmd shell could not resolve tsc although its shim existed;
the same scripts passed with process-local npm_config_script_shell set to
PowerShell. No project scripts/configuration were changed. CI uses its normal
Node 22 environment. Exact final test and CI results belong in the PR handoff.

No native macOS integration, installed Nexus bridge, transport, audio or actual
runtime scenario was exercised. npm reported existing dependency advisories;
dependency remediation is outside this inert contract step.

## Rollback and stop

Revert this isolated PR, including its new dependency pins and LF rule. There
is no database/user-data migration or cleanup. Keep all legacy behavior and
other worktrees untouched.

This is not G0-B approval. Independent TS/Python contract review and explicit
joint acceptance remain required. No self-merge, auto-merge, D01-E, G1A,
YJNX-01B, D13-D16 implementation or productive Nexus read/write is authorized.
After PR/CI/external handoff: STOP.
