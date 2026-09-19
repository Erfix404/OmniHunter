import pytest
from unittest.mock import MagicMock
from core.browser.connection import get_active_port, connect_live

def test_get_active_port_parses_file(tmp_path, monkeypatch):
    port_file = tmp_path / "DevToolsActivePort"
    port_file.write_text("1031\n/devtools/browser/xyz123\n")

    monkeypatch.setattr("os.path.expandvars", lambda x: str(tmp_path))

    port, path = get_active_port()
    assert port == 1031
    assert path == "/devtools/browser/xyz123"

def test_get_active_port_handles_missing_file(monkeypatch):
    monkeypatch.setattr("os.path.expandvars", lambda x: "C:/non/existent")
    assert get_active_port() is None

def test_connect_live_calls_cdp_with_ws_url():
    mock_pw = MagicMock()
    mock_browser = MagicMock()
    mock_pw.chromium.connect_over_cdp.return_value = mock_browser

    # Fake the port
    import core.browser.connection as conn
    conn.get_active_port = lambda: (1031, "/devtools/browser/xyz")

    res = connect_live(mock_pw, timeout=1000)
    assert res == mock_browser
    mock_pw.chromium.connect_over_cdp.assert_called_once_with(
        "ws://127.0.0.1:1031/devtools/browser", timeout=1000
    )

def test_connect_live_fails_if_no_port():
    import core.browser.connection as conn
    conn.get_active_port = lambda: None
    with pytest.raises(RuntimeError, match="Chrome is not running in approval mode"):
        connect_live(MagicMock())
