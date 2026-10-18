"""NXB-0 corpus parity is structural evidence, never evidence of execution."""

import copy
import hashlib
from pathlib import Path
from typing import get_args

import pytest

from jarvis_agent.nexus_contracts.canonical import (
    canonical_bytes, canonical_json, parse_canonical_file, parse_json,
)
from jarvis_agent.nexus_contracts.constants import (
    CAPABILITY_MAPPING, FIXTURE_VERSION, MAX_DOCUMENT_BYTES, METHODS, Method,
    SCHEMA_ID, SCHEMA_VERSION,
)
from jarvis_agent.nexus_contracts.validation import (
    CONTRACT_TYPES, parse_contract, validate_contract,
)
from jarvis_agent.nexus_contracts.types import NoteMetadata

DIRECTORY = Path(__file__).resolve().parents[1] / "fixtures" / "local-integration-v1"
CORPUS_SHA256 = "8bb75002fcf8af4f1be76b3043aa868168bea2eee40dad2870f6140f03d5185f"
FILE_HASHES = {
    "canonicalization.json": "1c71cda918199b86a8aa265089c53fa9fdcf4cba8f95032d1af2b3de932c916e",
    "conformance.json": "006a2e5d78d14355ef0de53cbae004dc4f231aac4b9fafd4e3554121da67d46a",
    "manifest.json": "fd3d98628bb0676f6b1521f979bd819b8825addb47387cc5bb3e59cd2c2bf442",
    "scenarios.json": "bd470c052e28d430a05651c184c5dee02d9c553769479584951f054dd2eb5ddf",
    "wire-v1.schema.json": "65822eb37fffd728c6fb4e8d835ab7d5d9f93ad41365ab694adb11166ff43a2d",
}


def corpus(name):
    return parse_canonical_file((DIRECTORY / name).read_bytes())


CASES = corpus("conformance.json")["cases"]
CANONICAL_CASES = corpus("canonicalization.json")["cases"]
SCENARIOS = corpus("scenarios.json")["scenarios"]


def request(method):
    return copy.deepcopy(next(case["document"] for case in CASES if case["id"] == f"request:{method}"))


def test_exact_unmodified_file_bytes_manifest_and_corpus_hash():
    assert {path.name for path in DIRECTORY.iterdir()} == set(FILE_HASHES)
    for name, expected_hash in FILE_HASHES.items():
        raw = (DIRECTORY / name).read_bytes()
        assert hashlib.sha256(raw).hexdigest() == expected_hash
        parse_canonical_file(raw)
    manifest = corpus("manifest.json")
    assert manifest["fixtureVersion"] == FIXTURE_VERSION == "2.0.0"
    assert manifest["schemaVersion"] == SCHEMA_VERSION == "2.0.0"
    assert manifest["schemaId"] == SCHEMA_ID
    assert manifest["canonicalization"] == "RFC8785"
    assert manifest["fileEncoding"] == "UTF-8-no-BOM"
    assert manifest["fileFinalNewline"] == "LF"
    entries = manifest["entries"]
    assert [entry["path"] for entry in entries] == sorted(set(FILE_HASHES) - {"manifest.json"})
    for entry in entries:
        assert entry["bytes"] == len((DIRECTORY / entry["path"]).read_bytes())
        assert entry["sha256"] == FILE_HASHES[entry["path"]]
    inventory = "".join(f"{entry['sha256']}  {entry['path']}\n" for entry in entries).encode("utf-8")
    assert hashlib.sha256(inventory).hexdigest() == manifest["corpusSha256"] == CORPUS_SHA256


def test_exact_named_schema_inventory_and_ten_method_mapping():
    assert set(CONTRACT_TYPES) == set(corpus("wire-v1.schema.json")["$defs"])
    assert METHODS == (
        "system.hello", "capabilities.list", "mutation.status", "notes.query",
        "tasks.query", "reminders.query", "planning.queryRange", "flux.getAttention",
        "notes.create", "tasks.create",
    )
    assert get_args(Method) == METHODS
    assert dict(CAPABILITY_MAPPING) == {
        "system.hello": "nexus.system.hello", "capabilities.list": "nexus.capabilities.list",
        "mutation.status": "nexus.mutation.status", "notes.query": "nexus.notes.query",
        "tasks.query": "nexus.tasks.query", "reminders.query": "nexus.reminders.query",
        "planning.queryRange": "nexus.planning.queryRange", "flux.getAttention": "nexus.flux.getAttention",
        "notes.create": "nexus.notes.create", "tasks.create": "nexus.tasks.create",
    }
    with pytest.raises(TypeError):
        CAPABILITY_MAPPING["other"] = "nexus.other"
    with pytest.raises(KeyError):
        validate_contract("arbitrary.method", {})
    assert len(CASES) == 203 and len({case["id"] for case in CASES}) == 203
    assert len(CANONICAL_CASES) == 7


@pytest.mark.parametrize("case", CASES, ids=lambda case: case["id"])
def test_schema_conformance_same_nexus_case_ids_and_expected_validity(case):
    assert validate_contract(case["schema"], case["document"]).valid is case["valid"]
    if case["valid"]:
        typed = parse_contract(case["schema"], case["document"])
        assert canonical_bytes(typed.to_wire()) == canonical_bytes(case["document"])


@pytest.mark.parametrize("case", CANONICAL_CASES, ids=lambda case: case["id"])
def test_canonicalization_same_nexus_utf8_bytes_and_digest(case):
    raw = canonical_bytes(parse_json(case["input"]))
    assert raw.decode("utf-8") == case["canonical"]
    assert raw.hex() == case["utf8Hex"]
    assert hashlib.sha256(raw).hexdigest() == case["sha256"]


@pytest.mark.parametrize("scenario", SCENARIOS, ids=lambda case: "requirement-only:" + case["id"])
def test_future_runtime_requirements_only_validate_message_shapes(scenario):
    assert len(SCENARIOS) == 44
    assert scenario["runtimeEvidenceRequired"] is True
    for document in scenario["requests"]:
        assert validate_contract("Request", document).valid is scenario["requestValid"]
    assert validate_contract("Response", scenario["expectedResponse"]).valid


def test_restart_fixture_preserves_original_identity_without_reusing_current_authority():
    scenario = next(item for item in SCENARIOS if item["id"] == "new-session-reconciles-original-action-and-key")
    original, query = scenario["requests"]
    action = query["params"]["action"]
    assert query["context"]["sessionId"] != original["context"]["sessionId"]
    assert action["origin"] == original["context"]
    for field in ("actionId", "clientId", "idempotencyKey", "argumentsDigest"):
        assert action[field] == original["mutation"][field]
    assert scenario["expectedResponse"]["data"]["receipt"]["action"] == action
    # These are fixture relations, not a running server or a deduplication test.


@pytest.mark.parametrize("field", ["query", "tags", "priority", "durationMinutes"])
def test_omitted_is_not_explicit_null_for_nonnullable_optional_fields(field):
    document = request("notes.query" if field == "query" else "tasks.create")
    document["params"].pop(field, None)
    assert validate_contract("Request", document).valid
    assert field not in parse_contract("Request", document).to_wire()["params"]
    document["params"][field] = None
    assert not validate_contract("Request", document).valid


def test_model_revalidation_preserves_omission_and_rejects_unvalidated_values():
    model = NoteMetadata.model_validate({"id": "n1"})
    assert NoteMetadata.model_validate(model).to_wire() == {"id": "n1"}
    with pytest.raises(ValueError), pytest.warns(UserWarning, match="Pydantic serializer warnings"):
        NoteMetadata.model_validate(NoteMetadata.model_construct(id=42))
    with pytest.raises(ValueError):
        NoteMetadata.model_validate(NoteMetadata.model_construct(id="n1", title=None))


@pytest.mark.parametrize("value", [True, "1", 0, -1, 101, 2**53, 1.1])
def test_page_limits_reject_coercion_nonintegral_and_out_of_bounds(value):
    document = request("notes.query")
    document["params"]["limit"] = value
    assert not validate_contract("Request", document).valid


def test_json_integer_semantics_accept_integral_binary64_but_not_bool_literals():
    document = request("notes.query")
    document["params"]["limit"] = 1.0
    assert validate_contract("Request", document).valid
    snapshot = next(
        copy.deepcopy(case["document"]) for case in CASES
        if case["id"] == "response:notes.query"
    )
    snapshot["data"]["truncated"] = 0
    assert not validate_contract("Response", snapshot).valid


@pytest.mark.parametrize("value", [
    "2026-02-29T10:00:00Z", "0000-01-01T00:00:00Z",
    "2026-01-01T24:00:00Z", "2026-01-01T00:00:60Z",
    "2026-01-01T00:00:00-00:00", "2026-01-01T00:00:00Z\n",
    "2026-01-01t00:00:00z", "2026-01-01T00:00:00.1234567890Z",
])
def test_wire_instant_profile(value):
    assert not validate_contract("Instant", value).valid


def test_wire_does_not_invent_timezone_or_peer_hash_validation():
    # Nexus specifies syntactic IANA-style zones; existence/DST/offset agreement
    # and compatibility of well-formed peer hashes are later boundary checks.
    assert validate_contract("TimeZone", "Not/A_Real_Zone").valid
    capability = {
        "method": "notes.query", "capability": "nexus.notes.query",
        "schemaId": SCHEMA_ID, "schemaVersion": SCHEMA_VERSION,
        "schemaHash": "f" * 64, "nexusState": "authorized",
    }
    assert validate_contract("Capability", capability).valid
    capability["jarvisPolicyVerdict"] = "allow"
    assert not validate_contract("Capability", capability).valid


def test_codepoint_length_utf8_wire_budget_and_invalid_unicode_are_distinct():
    document = request("notes.create")
    document["params"]["content"] = "x" * 65_536
    assert validate_contract("Request", document).valid
    document["params"]["content"] += "x"
    assert not validate_contract("Request", document).valid
    document["params"]["content"] = "\U0001f9e0" * 33_000
    assert len(canonical_bytes(document)) > MAX_DOCUMENT_BYTES
    assert not validate_contract("Request", document).valid
    document["params"]["content"] = "\ud800"
    assert not validate_contract("Request", document).valid


@pytest.mark.parametrize("raw", [
    b"\xef\xbb\xbf{}\n", b"{}\r\n", b'{"a":1,"a":1}\n',
    b'{ "a":1}\n', b"{}", b"{}\n\n", b"\xff\n", b'{"x":1.0}\n',
])
def test_corpus_decoder_rejects_reformatted_or_invalid_bytes(raw):
    with pytest.raises(ValueError):
        parse_canonical_file(raw)


def test_non_json_cycles_depth_keys_and_unicode_cannot_be_canonicalized():
    cyclic = {}
    cyclic["self"] = cyclic
    deep = None
    for _ in range(65):
        deep = [deep]
    for value in [float("nan"), float("inf"), (1, 2), {1: "key"}, {"bad": object()}, cyclic, deep, "\udfff"]:
        with pytest.raises((ValueError, OverflowError)):
            canonical_bytes(value)
    assert canonical_json({"__proto__": 1, "a": 2}) == '{"__proto__":1,"a":2}'
    assert canonical_bytes("\u00e9") != canonical_bytes("e\u0301")
    assert canonical_bytes(parse_json("100000000000000000000")) == b"100000000000000000000"
    assert canonical_bytes(-0.0) == b"0"


@pytest.mark.parametrize("value, expected", [
    (1e-7, b"1e-7"), (1e-6, b"0.000001"), (1e20, b"100000000000000000000"),
    (1e21, b"1e+21"), (5e-324, b"5e-324"),
    (1.7976931348623157e308, b"1.7976931348623157e+308"),
])
def test_additional_binary64_spelling_boundaries(value, expected):
    assert canonical_bytes(value) == expected
