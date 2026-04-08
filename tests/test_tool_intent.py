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


def test_heuristic_detects_open_app_with_infinitive_form():
    intent = infer_heuristic_tool_call("kannst du bitte Safari öffnen")

    assert intent is not None
    assert intent.tool_name == "open_app"
    assert intent.tool_input["app_name"] == "Safari"


def test_heuristic_normalizes_notiz_app_to_notes():
    intent = infer_heuristic_tool_call("oeffne die notiz app")

    assert intent is not None
    assert intent.tool_name == "open_app"
    assert intent.tool_input["app_name"] == "Notes"


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


def test_heuristic_notes_create_detected():
    intent = infer_heuristic_tool_call("erstelle bitte eine Notiz mit Titel Einkaufsliste die sagt Milch und Brot")

    assert intent is not None
    assert intent.tool_name == "notes_create"
    assert "einkaufsliste" in intent.tool_input["title"].lower()


def test_heuristic_notes_search_detected():
    intent = infer_heuristic_tool_call("suche in notizen nach projekt phoenix 5")

    assert intent is not None
    assert intent.tool_name == "notes_search"
    assert "projekt phoenix" in intent.tool_input["query"].lower()


def test_heuristic_contacts_search_detected():
    intent = infer_heuristic_tool_call("suche kontakt Max Mustermann")

    assert intent is not None
    assert intent.tool_name == "contacts_search"
    assert "max mustermann" in intent.tool_input["query"].lower()


def test_heuristic_mail_draft_detected():
    intent = infer_heuristic_tool_call(
        "mail entwurf an test@example.com betreff Projekt Update: Hallo Team bitte final prüfen"
    )

    assert intent is not None
    assert intent.tool_name == "mail_create_draft"
    assert intent.tool_input["to"] == "test@example.com"
    assert "projekt update" in intent.tool_input["subject"].lower()


def test_heuristic_messages_send_detected():
    intent = infer_heuristic_tool_call("sende nachricht an +49123456789: Bitte Licht ausmachen")

    assert intent is not None
    assert intent.tool_name == "messages_send"
    assert intent.tool_input["to"] == "+49123456789"


def test_heuristic_music_control_detected():
    intent = infer_heuristic_tool_call("musik pausieren")

    assert intent is not None
    assert intent.tool_name == "music_control"
    assert intent.tool_input["action"] == "pause"


def test_heuristic_reminder_list_detected():
    intent = infer_heuristic_tool_call("zeige erinnerungen 6")

    assert intent is not None
    assert intent.tool_name == "reminder_list"
    assert intent.tool_input["limit"] == 6


def test_heuristic_calendar_list_detected():
    intent = infer_heuristic_tool_call("zeige termine 14")

    assert intent is not None
    assert intent.tool_name == "calendar_list_events"


def test_heuristic_raycast_open_detected():
    intent = infer_heuristic_tool_call("oeffne raycast mit suche projekt status")

    assert intent is not None
    assert intent.tool_name == "raycast_open"
    assert "projekt status" in intent.tool_input["fallback_text"].lower()


def test_heuristic_raycast_command_detected():
    intent = infer_heuristic_tool_call("raycast befehl raycast/file-search/search-files mit text ~/Desktop")

    assert intent is not None
    assert intent.tool_name == "raycast_run_command"
    assert intent.tool_input["owner"] == "raycast"
    assert intent.tool_input["extension"] == "file-search"
    assert intent.tool_input["command"] == "search-files"
