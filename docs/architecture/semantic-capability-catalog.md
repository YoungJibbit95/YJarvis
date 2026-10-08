# YJ2-05B3: semantic catalog ownership

Base main: `b553e44a52d37d37ec6a2bb0baae64f366c0ee44`. The user accepted Core
PR #16 and Product PR #15 and required their integration before 05B3. PR #16
was squash-merged as `eab13268f3358576741115a97b310be6b277d415`; main CI
`37743515227` passed 6/6. Product work synchronized #15 with that main without
changing its accepted patch; CI `37743787858` passed 6/6 before its squash merge.
The final joint main CI `37744058908` passed 6/6 and main was reread before this
branch was created. Compared with architecture baseline
`dea0e9e6a266584e9c8efaf53dd82138aecbd662`, this includes accepted YJ2-00 through
05B2, YJW-00A/B/B.1 and separate YJUX-00A/B/01A Product work.

## One inventory, two exact lookup views

`domain/capability_catalog.py` now constructs the 18 existing specs exclusively
in `CAPABILITY_CATALOG`, keyed by their accepted semantic `CapabilityName`:

```python
CAPABILITY_CATALOG["apps.open"]  # ToolSpecV2 for apps.open
```

`LEGACY_TOOL_TO_CAPABILITY` is a separate, explicit read-only bijection containing
18 legacy-name/semantic-name pairs. It is compatibility knowledge, not a tool
registry, provider resolver or name-conversion algorithm. The semantic inventory
does not derive from or resolve through this map.

`LEGACY_TOOL_CATALOG` remains as a read-only compatibility view for existing tests
and utilities. It indexes the semantic inventory through the explicit mapping;
it does not construct, copy or revalidate specs:

```python
LEGACY_TOOL_TO_CAPABILITY["open_app"] == "apps.open"
LEGACY_TOOL_CATALOG["open_app"] is CAPABILITY_CATALOG["apps.open"]
```

All three mappings use `MappingProxyType`. Both spec views reference exactly the
same 18 frozen objects. Model class references retain the existing Python class
semantics; this change does not freeze class definitions themselves. Unknown keys
raise `KeyError` on direct lookup. Semantic lookup does not accept legacy aliases,
and legacy lookup does not accept semantic aliases. No trimming, case folding,
underscore/dot substitution, fuzzy match or fallback is performed.

**Future ToolRuntime consumes the semantic catalog, never the legacy-name view.**
The co-located compatibility data must never pull legacy tools/providers into
domain. Membership still means known, not available or authorized.

## Preserved boundary and evidence

Capability IDs, descriptions, mode/risk, reversible/idempotent/dry-run flags,
timeout and all input/output classes are unchanged. No model, registry, planner,
approval, wire/DB, Product or provider behavior changes. No production runtime
imports the domain catalog. There is no input/output adapter, ToolRuntime,
Provider Protocol, timeout enforcement, Observation normalization or policy work.

Tests reuse the accepted metadata snapshot and input/output fixtures unchanged.
They check exact classes and metadata through semantic lookup, complete unique
key sets, the explicit bijection, object identity, read-only mappings and rejected
unknown/alias-like keys. The existing isolated process now traverses semantic
lookup and checks identity with the legacy view before validating every input and
output, under the unchanged process/network/DB/file-write audit guard. Existing
legacy planner, ToolResult, learned-command and approval regressions remain active.

Rollback: revert this PR. No data/configuration migration is required; the original
legacy-keyed inventory is restored. Stop after external-review handoff; adapters,
YJ2-05C1 and YJW-01 remain separate, explicitly blocked steps.
