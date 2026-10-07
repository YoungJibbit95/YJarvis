"""Successful semantic data is neither legacy prose nor an Observation."""

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from jarvis_agent.domain import tool_outputs
from jarvis_agent.domain.capability_catalog import LEGACY_TOOL_CATALOG


EXAMPLES = json.loads((Path(__file__).parents[1] / "fixtures" / "tool_outputs.json").read_text(encoding="utf-8"))
MODELS = [
    (tool_outputs.NoDataOutput, {}),
    (tool_outputs.ClipboardReadOutput, {"text": "clipboard"}),
    (tool_outputs.FileReadOutput, {"content": "file"}),
    (tool_outputs.ReminderListOutput, {"titles": ["Review"]}),
    (tool_outputs.CalendarListEventsOutput, {"titles": ["Review"]}),
    (tool_outputs.NotesSearchOutput, {"titles": ["Project"]}),
    (tool_outputs.ContactsSearchOutput, {"names": ["Ada"]}),
]
SEQUENCES = [(model, next(iter(data))) for model, data in MODELS if any(isinstance(v, list) for v in data.values())]
TEXTS = [(tool_outputs.ClipboardReadOutput, "text"), (tool_outputs.FileReadOutput, "content")]


def test_all_eighteen_capabilities_have_explicit_outputs_and_inputs():
    assert len(EXAMPLES) == len(LEGACY_TOOL_CATALOG) == 18
    assert EXAMPLES.keys() == LEGACY_TOOL_CATALOG.keys()
    for name, example in EXAMPLES.items():
        spec = LEGACY_TOOL_CATALOG[name]
        assert spec.input_model is not None
        assert spec.output_model is getattr(tool_outputs, example["model"])
        payload = spec.output_model.model_validate(example["data"])
        assert payload.model_dump(mode="json") == example["data"]
    assert sum(s.output_model is tool_outputs.NoDataOutput for s in LEGACY_TOOL_CATALOG.values()) == 12


@pytest.mark.parametrize("model, data", MODELS)
def test_fields_are_required_frozen_and_round_trip_without_coercion(model, data):
    result = model.model_validate(data)
    assert set(model.model_fields) == set(data)
    assert all(field.is_required() for field in model.model_fields.values())
    assert model.model_validate(result) == result
    assert model.model_validate_json(result.model_dump_json()) == result
    assert model.model_json_schema()["additionalProperties"] is False
    for field in data:
        with pytest.raises(ValidationError, match="Field required"):
            model.model_validate({})
        with pytest.raises(ValidationError):
            model.model_validate({field: None})
        with pytest.raises(ValidationError):
            model.model_validate(model.model_construct(**{field: 123}))
    with pytest.raises(ValidationError, match="frozen"):
        setattr(result, next(iter(data), "unexpected"), "changed")


@pytest.mark.parametrize("model, data", MODELS)
def test_outputs_reject_non_objects_and_execution_policy_provider_or_rendering_fields(model, data):
    for bad in (None, True, 1, "App geoeffnet: Safari", [], [data]):
        with pytest.raises(ValidationError):
            model.model_validate(bad)
    for field in ("success", "error", "error_code", "error_detail", "duration_ms", "summary",
                  "occurred_at", "action_id", "verdict", "approval", "policy", "provider", "platform",
                  "message", "output", "unexpected"):
        assert field not in model.model_fields
        with pytest.raises(ValidationError, match="Extra inputs"):
            model.model_validate(data | {field: "not capability data"})
    assert not any(hasattr(model, name) for name in ("execute", "authorize", "approve"))


@pytest.mark.parametrize("model, field", TEXTS)
def test_text_is_strict_and_preserves_empty_whitespace_unicode_and_long_content(model, field):
    for text in ("", " \n\t", "Grüße 🌍", "x" * 7000, "literal | separator\n...[gekürzt]"):
        assert getattr(model.model_validate({field: text}), field) == text
    for value in (123, True, b"bytes", [], {}, None):
        with pytest.raises(ValidationError):
            model.model_validate({field: value})


@pytest.mark.parametrize("model, field", SEQUENCES)
def test_ordered_collections_preserve_duplicates_empty_titles_and_detach_from_caller(model, field):
    source = ["same", "", "same", "  title\nwith | separator  "]
    result = model.model_validate({field: source})
    assert getattr(result, field) == tuple(source)
    source.append("later mutation")
    assert "later mutation" not in getattr(result, field)
    assert model.model_validate({field: ()}) == model.model_validate({field: []})
    assert model.model_validate({field: ()}).model_dump(mode="json") == {field: []}
    assert model.model_validate({field: ("Title",)}).model_dump(mode="json") == {field: ["Title"]}
    with pytest.raises(TypeError):
        getattr(result, field)[0] = "mutation"


@pytest.mark.parametrize("model, field", SEQUENCES)
def test_collections_reject_prose_unordered_lazy_and_untyped_data(model, field):
    for value in ("first\nsecond", b"first", {"first"}, frozenset({"first"}),
                  iter(["first"]), {"title": "first"}, 123, None,
                  [123], [True], [None], [b"bytes"], [["nested"]], [{"title": "first"}]):
        with pytest.raises(ValidationError):
            model.model_validate({field: value})
