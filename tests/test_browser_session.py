import pytest
from unittest.mock import MagicMock, patch
from core.browser.session import SessionManager

def test_session_manager_live_mode():
    with patch("core.browser.session.sync_playwright") as mock_pw, \
         patch("core.browser.session.connect_live") as mock_connect:

        mock_p = mock_pw.return_value.__enter__.return_value
        mock_browser = MagicMock()
        mock_context = MagicMock()
        mock_page = MagicMock()

        mock_connect.return_value = mock_browser
        mock_browser.contexts = [mock_context]
        mock_context.new_page.return_value = mock_page

        with SessionManager(mode="live") as page:
            assert page == mock_page

        mock_connect.assert_called_once_with(mock_p, timeout=90000)
        # Should close the browser connection to detach
        mock_browser.close.assert_called_once()
