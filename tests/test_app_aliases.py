from jarvis_agent.app_aliases import normalize_app_name


def test_normalize_app_name_maps_german_note_alias():
    assert normalize_app_name("notiz app") == "Notes"


def test_normalize_app_name_removes_wrapper_words():
    assert normalize_app_name("die Safari app") == "Safari"


def test_normalize_app_name_keeps_unknown_name_clean():
    assert normalize_app_name("die FooBar app") == "FooBar"

