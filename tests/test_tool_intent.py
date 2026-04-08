from datetime import datetime

from jarvis_agent.tool_intent import infer_heuristic_tool_call, parse_explicit_tool_call


def test_explicit_tool_call_parses_json_payload():
    intent = parse_explicit_tool_call('/tool file_write {"path":"/tmp/a.txt","content":"abc"}')

    assert intent is not None
    assert intent.tool_name == "file_write"
    assert intent.tool_input["content"] == "abc"


def test_heuristic_detects_open_url():
    intent = infer_heuristic_tool_call("Bitte oeffne https://example.com jetzt")

    assert intent is not None
    assert intent.tool_name == "open_url"
    assert intent.tool_input["url"] == "https://example.com"


def test_heuristic_detects_file_read():
    intent = infer_heuristic_tool_call("datei lesen /tmp/test.txt")

    assert intent is not None
    assert intent.tool_name == "file_read"
    assert intent.tool_input["path"] == "/tmp/test.txt"


def test_heuristic_reminder_reorders_content_and_due_phrase():
    intent = infer_heuristic_tool_call(
        "mach mir eine erinnerung auf morgen 10 uhr die sagt, Licht ausmachen"
    )

    assert intent is not None
    assert intent.tool_name == "reminder_create"
    assert intent.tool_input["title"].lower() == "licht ausmachen morgen 10 uhr"
    assert "due_at" in intent.tool_input

    due_at = datetime.fromisoformat(intent.tool_input["due_at"])
    assert due_at.hour == 10
    assert due_at.minute == 0


def test_heuristic_detects_erinner_mich_variant():
    intent = infer_heuristic_tool_call("erinner mich morgen 8 uhr an den muell")

    assert intent is not None
    assert intent.tool_name == "reminder_create"
    assert "muell" in intent.tool_input["title"].lower()


def test_heuristic_detects_open_app_without_app_keyword():
    intent = infer_heuristic_tool_call("öffne Safari bitte")

    assert intent is not None
    assert intent.tool_name == "open_app"
    assert intent.tool_input["app_name"] == "Safari"


def test_heuristic_clipboard_write_extracts_payload_text():
    intent = infer_heuristic_tool_call("kopiere Hallo Sir in die Zwischenablage")

    assert intent is not None
    assert intent.tool_name == "clipboard_write"
    assert intent.tool_input["text"] == "Hallo Sir"


def test_heuristic_calendar_parses_start_and_duration():
    intent = infer_heuristic_tool_call(
        "trag bitte einen termin in den kalender ein morgen 14 uhr fuer 30 minuten die sagt Team Sync"
    )

    assert intent is not None
    assert intent.tool_name == "calendar_create_event"
    assert intent.tool_input["title"].lower() == "team sync"
    assert intent.tool_input["duration_minutes"] == 30
    assert "start_at" in intent.tool_input

    start_at = datetime.fromisoformat(intent.tool_input["start_at"])
    assert start_at.hour == 14
    assert start_at.minute == 0


def test_heuristic_calendar_without_explicit_calendar_word():
    intent = infer_heuristic_tool_call("plane morgen 09:30 uhr einen termin fuer 45 minuten mit titel Daily Standup")

    assert intent is not None
    assert intent.tool_name == "calendar_create_event"
    assert intent.tool_input["duration_minutes"] == 45
    assert intent.tool_input["title"].lower() == "daily standup"
    assert "start_at" in intent.tool_input
