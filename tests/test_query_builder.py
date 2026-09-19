from core.scrapers.query_builder import build_search_queries


def test_iranian_platform_receives_persian_keywords_only():
    config = {"scopes": {"bots": {"enabled": True, "keywords": ["ربات تلگرام", "telegram bot"]}}}
    assert build_search_queries(config, "ponisha") == ["ربات تلگرام"]


def test_foreign_platform_receives_english_keywords_only():
    config = {"scopes": {"bots": {"enabled": True, "keywords": ["ربات تلگرام", "telegram bot"]}}}
    assert build_search_queries(config, "freelancer") == ["telegram bot"]


def test_disabled_scopes_are_skipped():
    config = {
        "scopes": {
            "bots": {"enabled": True, "keywords": ["telegram bot"]},
            "formatting": {"enabled": False, "keywords": ["convert docx"]},
        }
    }
    assert build_search_queries(config, "freelancer") == ["telegram bot"]


def test_duplicate_keywords_collapse_preserving_order():
    config = {
        "scopes": {
            "bots": {"enabled": True, "keywords": ["telegram bot", "aiogram"]},
            "automation": {"enabled": True, "keywords": ["aiogram", "n8n"]},
        }
    }
    assert build_search_queries(config, "freelancer") == ["telegram bot", "aiogram", "n8n"]


def test_only_scopes_narrows_the_selection():
    config = {
        "scopes": {
            "bots": {"enabled": True, "keywords": ["telegram bot"]},
            "excel": {"enabled": True, "keywords": ["excel"]},
        }
    }
    assert build_search_queries(config, "freelancer", only_scopes=["excel"]) == ["excel"]
    assert build_search_queries(config, "freelancer", only_scopes=[]) == []


def test_limit_truncates():
    config = {"scopes": {"bots": {"enabled": True, "keywords": ["a", "b", "c"]}}}
    assert build_search_queries(config, "freelancer", limit=2) == ["a", "b"]
    assert build_search_queries(config, "freelancer", limit=0) == ["a", "b", "c"]


def test_malformed_config_returns_empty_list():
    assert build_search_queries(None, "ponisha") == []
    assert build_search_queries({}, "ponisha") == []
    assert build_search_queries({"scopes": None}, "ponisha") == []
    assert build_search_queries({"scopes": []}, "ponisha") == []


def test_blank_and_non_string_keywords_are_ignored():
    config = {"scopes": {"bots": {"enabled": True, "keywords": ["  ", "", None, "excel"]}}}
    assert build_search_queries(config, "freelancer") == ["excel"]


def test_unknown_platform_treated_as_foreign():
    config = {"scopes": {"bots": {"enabled": True, "keywords": ["telegram bot"]}}}
    assert build_search_queries(config, "newportal") == ["telegram bot"]
