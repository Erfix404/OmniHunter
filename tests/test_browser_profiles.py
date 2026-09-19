import os
import json
import pytest
from core.browser.profiles import get_chrome_profiles

def test_get_chrome_profiles_parses_local_state(tmp_path, monkeypatch):
    monkeypatch.setattr("os.name", "nt")
    local_state_data = {
        "profile": {
            "info_cache": {
                "Default": {"name": "Person 1", "user_name": "test1@gmail.com"},
                "Profile 1": {"name": "erfan", "user_name": "test2@gmail.com"}
            },
            "last_used": "Profile 1"
        }
    }

    mock_local_state = tmp_path / "Local State"
    mock_local_state.write_text(json.dumps(local_state_data))

    # Mock os.path.expandvars to point to our tmp directory
    monkeypatch.setattr("os.path.expandvars", lambda x: str(mock_local_state))

    profiles = get_chrome_profiles()

    assert len(profiles) == 2
    assert profiles["Default"]["email"] == "test1@gmail.com"
    assert profiles["Profile 1"]["is_last_used"] is True
    assert profiles["Default"]["is_last_used"] is False

def test_get_chrome_profiles_handles_missing_file(monkeypatch):
    monkeypatch.setattr("os.name", "nt")
    monkeypatch.setattr("os.path.expandvars", lambda x: "C:/non/existent/path/Local State")
    profiles = get_chrome_profiles()
    assert profiles == {}
