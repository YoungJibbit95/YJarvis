"""Typed future inputs, deliberately stricter than unmodified legacy inputs."""

import json
from datetime import date, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from jarvis_agent.domain import tool_inputs
from jarvis_agent.domain.capability_catalog import LEGACY_TOOL_CATALOG


VALID = json.loads((Path(__file__).parents[1] / "fixtures" / "tool_inputs.json").read_text(encoding="utf-8"))
# Expected model, required fields and defaults are explicit contract decisions.
CONTRACTS = [
    ("open_url", "UrlOpenInput", {"url"}, {}),
    ("open_app", "AppOpenInput", {"app_name"}, {}),
    ("raycast_open", "RaycastOpenInput", set(), {"fallback_text": None}),
    ("raycast_run_command", "RaycastCommandRunInput", {"owner", "extension", "command"}, {"fallback_text": None, "background": True}),
    ("clipboard_read", "ClipboardReadInput", set(), {}),
    ("clipboard_write", "ClipboardWriteInput", {"text"}, {}),
    ("reminder_create", "ReminderCreateInput", {"title"}, {"notes": None, "due_at": None}),
    ("reminder_list", "ReminderListInput", set(), {"limit": 8, "list_name": None}),
    ("calendar_create_event", "CalendarCreateEventInput", {"title"}, {"start_at": None, "start_offset_minutes": 5, "duration_minutes": 60}),
    ("calendar_list_events", "CalendarListEventsInput", set(), {"days_ahead": 7, "limit": 10}),
    ("notes_create", "NotesCreateInput", {"title", "content"}, {"folder": None}),
    ("notes_search", "NotesSearchInput", set(), {"query": "", "folder": None, "limit": 8}),
    ("mail_create_draft", "MailCreateDraftInput", {"subject", "content"}, {"recipient": None}),
    ("messages_send", "MessagesSendInput", {"recipient", "text"}, {}),
    ("contacts_search", "ContactsSearchInput", set(), {"query": "", "limit": 6}),
    ("music_control", "MusicControlInput", {"action"}, {}),
    ("file_read", "FileReadInput", {"path"}, {}),
    ("file_write", "FileWriteInput", {"path", "content"}, {"mode": "overwrite"}),
]


def validate(name, **updates):
    return LEGACY_TOOL_CATALOG[name].input_model.model_validate(VALID[name] | updates)


def test_all_eighteen_models_have_complete_contract_examples():
    assert len(CONTRACTS) == len(VALID) == len(LEGACY_TOOL_CATALOG) == 18
    assert set(VALID) == set(LEGACY_TOOL_CATALOG) == {c[0] for c in CONTRACTS}


@pytest.mark.parametrize("name, model_name, required, defaults", CONTRACTS)
def test_valid_required_optional_defaults_and_frozen_round_trip(name, model_name, required, defaults):
    model = LEGACY_TOOL_CATALOG[name].input_model
    assert model is getattr(tool_inputs, model_name)
    assert set(model.model_fields) == required | defaults.keys() == VALID[name].keys()
    assert {key for key, field in model.model_fields.items() if field.is_required()} == required
    instance = validate(name)
    assert model.model_validate(instance) == instance
    assert model.model_validate_json(instance.model_dump_json()) == instance
    assert model.model_json_schema()["additionalProperties"] is False
    minimal = model.model_validate({key: VALID[name][key] for key in required})
    assert {key: getattr(minimal, key) for key in defaults} == defaults
    assert not set(model.model_fields) & {"platform", "provider", "macos", "windows", "powershell", "applescript", "executable"}
    for field in required:
        with pytest.raises(ValidationError, match="Field required"):
            model.model_validate({key: value for key, value in VALID[name].items() if key != field})
    for field in model.model_fields:
        with pytest.raises(ValidationError, match="frozen"):
            setattr(instance, field, getattr(instance, field))
        if field in defaults and defaults[field] is None:
            assert getattr(validate(name, **{field: None}), field) is None
        else:
            with pytest.raises(ValidationError):
                validate(name, **{field: None})


@pytest.mark.parametrize("name", VALID)
def test_every_model_forbids_unknown_fields_and_non_object_inputs(name):
    with pytest.raises(ValidationError, match="Extra inputs"):
        validate(name, provider="never resolve this")
    for bad in (None, "{}", [], 1):
        with pytest.raises(ValidationError):
            LEGACY_TOOL_CATALOG[name].input_model.model_validate(bad)


@pytest.mark.parametrize("name, field, value", [(n, k, v) for n, fields in VALID.items() for k, v in fields.items()])
def test_no_scalar_coercion_for_any_field(name, field, value):
    wrong = (["false", 0, 1] if type(value) is bool else
             [str(value), float(value), True] if type(value) is int else
             [123, True, value.encode()])
    for bad in [*wrong, [], {}]:
        with pytest.raises(ValidationError):
            validate(name, **{field: bad})


@pytest.mark.parametrize("name, field, maximum", [
    ("reminder_list", "limit", 30), ("notes_search", "limit", 30),
    ("contacts_search", "limit", 30), ("calendar_list_events", "limit", 40),
    ("calendar_list_events", "days_ahead", 90), ("calendar_create_event", "duration_minutes", 1440),
])
def test_numeric_bounds_are_rejected_not_clamped(name, field, maximum):
    for value in (1, maximum):
        assert getattr(validate(name, **{field: value}), field) == value
    for value in (0, -1, maximum + 1):
        with pytest.raises(ValidationError):
            validate(name, **{field: value})


@pytest.mark.parametrize("name, field, maximum", [
    ("open_app", "app_name", 200), ("reminder_list", "list_name", 120),
    ("notes_create", "title", 180), ("notes_create", "content", 8000),
    ("notes_create", "folder", 120), ("notes_search", "query", 200),
    ("notes_search", "folder", 120), ("mail_create_draft", "subject", 220),
    ("mail_create_draft", "content", 12000), ("mail_create_draft", "recipient", 220),
    ("messages_send", "recipient", 220), ("messages_send", "text", 4000),
    ("contacts_search", "query", 180),
])
def test_text_bounds_reject_instead_of_truncating(name, field, maximum):
    assert getattr(validate(name, **{field: "x" * maximum}), field) == "x" * maximum
    with pytest.raises(ValidationError):
        validate(name, **{field: "x" * (maximum + 1)})


@pytest.mark.parametrize("name, field", [
    ("open_app", "app_name"), ("reminder_create", "title"), ("reminder_list", "list_name"),
    ("calendar_create_event", "title"), ("notes_create", "title"), ("notes_create", "folder"),
    ("notes_search", "folder"), ("mail_create_draft", "subject"), ("mail_create_draft", "recipient"),
    ("messages_send", "recipient"), ("messages_send", "text"), ("file_read", "path"), ("file_write", "path"),
])
def test_nonblank_fields(name, field):
    for value in ("", " \n\t"):
        with pytest.raises(ValidationError):
            validate(name, **{field: value})


@pytest.mark.parametrize("name, field", [
    ("clipboard_write", "text"), ("file_write", "content"), ("notes_create", "content"),
    ("mail_create_draft", "content"), ("notes_search", "query"), ("contacts_search", "query"),
    ("reminder_create", "notes"), ("raycast_open", "fallback_text"), ("raycast_run_command", "fallback_text"),
])
def test_empty_text_is_intentional_and_text_is_not_cleaned(name, field):
    for text in ("", "  first\nsecond  "):
        assert getattr(validate(name, **{field: text}), field) == text


@pytest.mark.parametrize("url", ["http://localhost:8787/health", "https://example.test/"])
def test_only_http_urls_are_accepted(url):
    assert str(validate("open_url", url=url).url) == url


@pytest.mark.parametrize("url", ["file:///tmp/a", "javascript:alert(1)", "shell:AppsFolder", "ftp://example.test", "raycast://x", "example.test", "https://", ""])
def test_non_http_or_incomplete_urls_are_rejected(url):
    with pytest.raises(ValidationError):
        validate("open_url", url=url)


@pytest.mark.parametrize("app_name", ["Safari", "Visual Studio Code", "7-Zip", "paint.net", "Übungs App (Beta)", "PowerShell"])
def test_app_display_names(app_name):
    assert validate("open_app", app_name=app_name).app_name == app_name


@pytest.mark.parametrize("app_name", [r"C:\Apps\app.exe", "/Applications/Safari.app", "Safari.app", "app.exe", "com.apple.Safari", 'application id "com.apple.Safari"', "powershell -Command Get-Date", "App; reboot", "App\nName", " App "])
def test_app_paths_identifiers_and_command_syntax_are_not_display_names(app_name):
    with pytest.raises(ValidationError):
        validate("open_app", app_name=app_name)


@pytest.mark.parametrize("field", ["owner", "extension", "command"])
def test_raycast_segments(field):
    for value in ("a", "Owner_Name.v2-1", "a" * 121):
        assert getattr(validate("raycast_run_command", **{field: value}), field) == value
    for value in ("", "_owner", "a/b", "a?x", "two words", "a\n", "a" * 122):
        with pytest.raises(ValidationError):
            validate("raycast_run_command", **{field: value})


@pytest.mark.parametrize("name, field, allowed", [("music_control", "action", ("play", "pause", "next", "previous")), ("file_write", "mode", ("overwrite", "append"))])
def test_exact_enums(name, field, allowed):
    for value in allowed:
        assert getattr(validate(name, **{field: value}), field) == value
    for value in ("", "command", allowed[0].upper(), " " + allowed[0]):
        with pytest.raises(ValidationError):
            validate(name, **{field: value})


@pytest.mark.parametrize("name, field", [("reminder_create", "due_at"), ("calendar_create_event", "start_at")])
def test_datetime_boundary_preserves_naive_and_aware_without_epoch_or_date_coercion(name, field):
    for text in ("2026-10-08T10:00:00", "2026-10-08T10:00:00Z", "2026-10-08T10:00:00-04:00"):
        expected = datetime.fromisoformat(text)
        assert getattr(validate(name, **{field: text}), field) == expected
        assert getattr(validate(name, **{field: expected}), field) == expected
    assert getattr(validate(name, **{field: None}), field) is None
    for value in (1234567890, "1234567890", "2026-10-08", date(2026, 10, 8), "tomorrow", "2026-02-30T10:00:00"):
        with pytest.raises(ValidationError):
            validate(name, **{field: value})


def test_absolute_start_and_relative_offset_remain_descriptive_and_no_path_policy_is_added():
    event = validate("calendar_create_event", start_offset_minutes=-10)
    assert event.start_at == datetime(2026, 10, 8, 10)
    assert event.start_offset_minutes == -10
    for path in ("../outside.txt", "C:\\", r"\\server\share\file.txt", "/tmp/example"):
        assert validate("file_read", path=path).path == path
        assert validate("file_write", path=path).path == path


@pytest.mark.parametrize("name", ["mail_create_draft", "messages_send"])
def test_legacy_to_key_is_not_a_semantic_recipient_alias(name):
    with pytest.raises(ValidationError, match="Extra inputs"):
        validate(name, to="person@example.test")
