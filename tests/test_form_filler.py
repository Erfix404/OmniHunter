import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from core.auth_helper import (
    DEFAULT_SESSIONS_DIR,
    get_session_path,
    has_session,
    interactive_login,
    load_session_cookies,
    save_session_state,
)
from core.form_filler import (
    BaseFormFiller,
    ParscodersFormFiller,
    PonishaFormFiller,
    fill_application,
    get_form_filler,
)


def test_form_filler_validates_required_fields():
    filler = BaseFormFiller()

    # Incomplete project (only url)
    incomplete_proj = {"url": "https://ponisha.ir/test"}
    with pytest.raises(ValueError, match="Missing required bid parameters"):
        filler.validate_project(incomplete_proj)

    # Empty strings for required fields
    empty_fields_proj = {
        "url": "   ",
        "suggested_bid": 1000000,
        "delivery_days": 3,
        "proposal": "",
    }
    with pytest.raises(ValueError, match="Missing required bid parameters"):
        filler.validate_project(empty_fields_proj)

    # Non-dict input
    with pytest.raises(ValueError, match="Missing required bid parameters"):
        filler.validate_project("not a dict")  # type: ignore

    # Complete valid project
    valid_proj = {
        "url": "https://ponisha.ir/test",
        "suggested_bid": 2500000,
        "delivery_days": 4,
        "proposal": "Hello, I can implement this bot.",
    }
    filler.validate_project(valid_proj)


def test_get_form_filler_factory():
    ponisha = get_form_filler("ponisha")
    assert isinstance(ponisha, PonishaFormFiller)
    assert ponisha.platform == "ponisha"

    # Case and whitespace insensitivity
    ponisha_upper = get_form_filler("  PONISHA  ")
    assert isinstance(ponisha_upper, PonishaFormFiller)

    parscoders = get_form_filler("parscoders")
    assert isinstance(parscoders, ParscodersFormFiller)
    assert parscoders.platform == "parscoders"

    with pytest.raises(ValueError, match="Unsupported form filler platform"):
        get_form_filler("unknown_platform")


def test_auth_helper_session_paths(tmp_path: Path):
    custom_dir = tmp_path / "sessions"

    # Default path
    default_path = get_session_path("ponisha")
    assert default_path == DEFAULT_SESSIONS_DIR / "ponisha.json"

    # Custom dir and casing normalization
    p_path = get_session_path("PARSCOders", sessions_dir=custom_dir)
    assert p_path == custom_dir / "parscoders.json"

    # has_session on non-existent file
    assert has_session("parscoders", sessions_dir=custom_dir) is False

    # has_session on empty file (0 bytes)
    p_path.parent.mkdir(parents=True, exist_ok=True)
    p_path.write_text("", encoding="utf-8")
    assert has_session("parscoders", sessions_dir=custom_dir) is False

    # has_session on non-empty file
    p_path.write_text('{"cookies": []}', encoding="utf-8")
    assert has_session("parscoders", sessions_dir=custom_dir) is True


def test_auth_helper_save_and_load_cookies(tmp_path: Path):
    custom_dir = tmp_path / "sessions"

    # Non-existent session returns None
    assert load_session_cookies("ponisha", sessions_dir=custom_dir) is None

    # Playwright storage_state format
    storage_state_data = {
        "cookies": [
            {"name": "session_id", "value": "abc123xyz", "domain": "ponisha.ir"},
            {"name": "token", "value": "secret999", "domain": "ponisha.ir"},
        ],
        "origins": [{"origin": "https://ponisha.ir", "localStorage": []}],
    }
    saved_path = save_session_state(storage_state_data, "ponisha", sessions_dir=custom_dir)
    assert saved_path.exists()

    cookies = load_session_cookies("ponisha", sessions_dir=custom_dir)
    assert isinstance(cookies, list)
    assert len(cookies) == 2
    assert cookies[0]["name"] == "session_id"

    # Simple dict format
    dict_data = {"token": "xyz789"}
    save_session_state(dict_data, "parscoders", sessions_dir=custom_dir)
    loaded_dict = load_session_cookies("parscoders", sessions_dir=custom_dir)
    assert loaded_dict == {"token": "xyz789"}

    # Raw list format
    list_data = [{"name": "auth", "value": "ok"}]
    save_session_state(list_data, "freelancer", sessions_dir=custom_dir)
    loaded_list = load_session_cookies("freelancer", sessions_dir=custom_dir)
    assert loaded_list == [{"name": "auth", "value": "ok"}]

    # Malformed JSON file returns None
    corrupt_path = get_session_path("corrupt", sessions_dir=custom_dir)
    corrupt_path.write_text("{this is not valid json", encoding="utf-8")
    assert load_session_cookies("corrupt", sessions_dir=custom_dir) is None


def test_auth_helper_interactive_login_mocked(tmp_path: Path):
    custom_dir = tmp_path / "sessions"

    with patch("playwright.sync_api.sync_playwright") as mock_sync_pw:
        mock_p = mock_sync_pw.return_value.__enter__.return_value
        mock_browser = MagicMock()
        mock_context = MagicMock()
        mock_page = MagicMock()

        mock_p.chromium.launch.return_value = mock_browser
        mock_browser.new_context.return_value = mock_context
        mock_context.new_page.return_value = mock_page

        # Provide a dummy prompt_fn that returns immediately
        called_prompt = []

        def dummy_prompt():
            called_prompt.append(True)

        session_path = interactive_login(
            platform="ponisha",
            timeout_sec=10,
            headless=True,
            sessions_dir=custom_dir,
            prompt_fn=dummy_prompt,
        )

        assert called_prompt == [True]
        assert session_path == custom_dir / "ponisha.json"
        mock_page.goto.assert_called_once_with("https://ponisha.ir/login", timeout=10000)
        mock_context.storage_state.assert_called_once_with(path=str(session_path))
        mock_context.close.assert_called_once()
        mock_browser.close.assert_called_once()


def test_ponisha_form_filler_dry_run_mocked():
    filler = PonishaFormFiller()
    project = {
        "url": "https://ponisha.ir/project/12345/telegram-bot",
        "suggested_bid": 3000000,
        "delivery_days": 3,
        "proposal": "سلام، پروژه ربات تلگرام با aiogram در ۳ روز قابل پیاده‌سازی است.",
    }

    with patch("playwright.sync_api.sync_playwright") as mock_sync_pw:
        mock_p = mock_sync_pw.return_value.__enter__.return_value
        mock_browser = MagicMock()
        mock_context = MagicMock()
        mock_page = MagicMock()

        mock_p.chromium.launch.return_value = mock_browser
        mock_browser.new_context.return_value = mock_context
        mock_context.new_page.return_value = mock_page

        # dry_run = True (default)
        result = filler.fill_application(project, dry_run=True, headless=True)

        assert result["status"] == "ready"
        assert result["platform"] == "ponisha"
        assert result["url"] == project["url"]
        assert result["bid"] == 3000000
        assert result["delivery_days"] == 3
        assert result["submitted"] is False
        assert "dry-run" in result["details"]

        mock_page.goto.assert_called_once_with(project["url"], timeout=30000)
        assert mock_page.fill.call_count >= 3
        # In dry run, click should NEVER be called on submit button
        mock_page.click.assert_not_called()


def test_ponisha_form_filler_submission_mocked():
    filler = PonishaFormFiller()
    project = {
        "url": "https://ponisha.ir/project/12345/telegram-bot",
        "suggested_bid": 3000000,
        "delivery_days": 3,
        "proposal": "سلام، پروژه ربات تلگرام با aiogram در ۳ روز قابل پیاده‌سازی است.",
    }

    with patch("playwright.sync_api.sync_playwright") as mock_sync_pw:
        mock_p = mock_sync_pw.return_value.__enter__.return_value
        mock_browser = MagicMock()
        mock_context = MagicMock()
        mock_page = MagicMock()

        mock_p.chromium.launch.return_value = mock_browser
        mock_browser.new_context.return_value = mock_context
        mock_context.new_page.return_value = mock_page

        # dry_run = False
        result = filler.fill_application(project, dry_run=False, headless=True)

        assert result["status"] == "submitted"
        assert result["submitted"] is True
        assert "submitted successfully" in result["details"].lower()
        mock_page.click.assert_called_once()


def test_parscoders_form_filler_mocked():
    filler = ParscodersFormFiller()
    project = {
        "url": "https://parscoders.com/project/67890/web-crawler",
        "suggested_bid": 4500000,
        "delivery_days": 5,
        "proposal": "سلام، پروژه خزش وب با پایتون و سلنیوم اجرا می‌شود.",
    }

    with patch("playwright.sync_api.sync_playwright") as mock_sync_pw:
        mock_p = mock_sync_pw.return_value.__enter__.return_value
        mock_browser = MagicMock()
        mock_context = MagicMock()
        mock_page = MagicMock()

        mock_p.chromium.launch.return_value = mock_browser
        mock_browser.new_context.return_value = mock_context
        mock_context.new_page.return_value = mock_page

        # Dry run
        res_dry = filler.fill_application(project, dry_run=True, headless=True)
        assert res_dry["status"] == "ready"
        assert res_dry["submitted"] is False
        mock_page.click.assert_not_called()

        # Submit run
        res_submit = filler.fill_application(project, dry_run=False, headless=True)
        assert res_submit["status"] == "submitted"
        assert res_submit["submitted"] is True
        mock_page.click.assert_called_once()


def test_form_filler_validation_error_return():
    filler = BaseFormFiller()
    incomplete = {"url": "https://ponisha.ir/test"}

    result = filler.fill_application(incomplete)
    assert result["status"] == "error"
    assert result["submitted"] is False
    assert "Missing required bid parameters" in result["details"]


def test_form_filler_playwright_exception_handling():
    filler = PonishaFormFiller()
    project = {
        "url": "https://ponisha.ir/test",
        "suggested_bid": 1000000,
        "delivery_days": 2,
        "proposal": "Test proposal",
    }

    with patch("playwright.sync_api.sync_playwright") as mock_sync_pw:
        mock_p = mock_sync_pw.return_value.__enter__.return_value
        mock_browser = MagicMock()
        mock_context = MagicMock()
        mock_page = MagicMock()

        mock_p.chromium.launch.return_value = mock_browser
        mock_browser.new_context.return_value = mock_context
        mock_context.new_page.return_value = mock_page
        mock_page.goto.side_effect = RuntimeError("Navigation timeout 30000ms")

        result = filler.fill_application(project, headless=True)
        assert result["status"] == "error"
        assert result["submitted"] is False
        assert "Navigation timeout" in result["details"]


def test_form_filler_loads_existing_session(tmp_path: Path):
    custom_dir = tmp_path / "sessions"
    session_file = custom_dir / "ponisha.json"
    session_file.parent.mkdir(parents=True, exist_ok=True)
    session_file.write_text('{"cookies": []}', encoding="utf-8")

    filler = PonishaFormFiller()
    project = {
        "url": "https://ponisha.ir/test",
        "suggested_bid": 2000000,
        "delivery_days": 2,
        "proposal": "Test proposal",
    }

    with patch("playwright.sync_api.sync_playwright") as mock_sync_pw:
        mock_p = mock_sync_pw.return_value.__enter__.return_value
        mock_browser = MagicMock()
        mock_p.chromium.launch.return_value = mock_browser

        filler.fill_application(project, session_path=session_file, headless=True)
        mock_browser.new_context.assert_called_once_with(storage_state=str(session_file))


def test_form_filler_selector_fallback_and_exhaustion():
    filler = PonishaFormFiller()
    mock_page = MagicMock()

    # First selector fails, second succeeds
    calls = []

    def fake_fill(sel, val, **kwargs):
        calls.append((sel, val, kwargs))
        if len(calls) == 1:
            raise Exception("First selector failed")
        return None

    mock_page.fill.side_effect = fake_fill

    filler._fill_first_matching(
        mock_page, ['input[name="first"]', 'input[name="second"]'], "test_val", "field"
    )
    assert len(calls) == 2
    # Verify fast timeout is passed
    assert calls[0][2].get("timeout") == 2000
    assert calls[1][2].get("timeout") == 2000

    # All selectors fail -> raises RuntimeError
    mock_page.fill.side_effect = Exception("Not found")
    with pytest.raises(RuntimeError, match="Could not find or populate 'missing_field'"):
        filler._fill_first_matching(mock_page, ["sel1", "sel2"], "val", "missing_field")


def test_form_filler_click_fallback_and_exhaustion():
    filler = PonishaFormFiller()
    mock_page = MagicMock()

    # First click fails, second succeeds
    clicks = []

    def fake_click(sel, **kwargs):
        clicks.append((sel, kwargs))
        if len(clicks) == 1:
            raise Exception("First click failed")
        return None

    mock_page.click.side_effect = fake_click
    filler._click_first_matching(mock_page, ["btn1", "btn2"], "submit")
    assert len(clicks) == 2
    # Verify fast timeout is passed
    assert clicks[0][1].get("timeout") == 2000
    assert clicks[1][1].get("timeout") == 2000

    # All clicks fail -> raises RuntimeError
    mock_page.click.side_effect = Exception("Click error")
    with pytest.raises(RuntimeError, match="Could not trigger 'submit'"):
        filler._click_first_matching(mock_page, ["b1", "b2"], "submit")


def test_base_filler_not_implemented_hooks():
    filler = BaseFormFiller()
    mock_page = MagicMock()
    with pytest.raises(NotImplementedError):
        filler._fill_form(mock_page, {})
    with pytest.raises(NotImplementedError):
        filler._submit_form(mock_page, {})


def test_interactive_login_with_existing_session_and_eof(tmp_path: Path):
    custom_dir = tmp_path / "sessions"
    sess_file = custom_dir / "freelancer.json"
    sess_file.parent.mkdir(parents=True, exist_ok=True)
    sess_file.write_text('{"cookies": []}', encoding="utf-8")

    with patch("playwright.sync_api.sync_playwright") as mock_sync_pw:
        mock_p = mock_sync_pw.return_value.__enter__.return_value
        mock_browser = MagicMock()
        mock_context = MagicMock()
        mock_page = MagicMock()

        mock_p.chromium.launch.return_value = mock_browser
        mock_browser.new_context.return_value = mock_context
        mock_context.new_page.return_value = mock_page

        def eof_prompt():
            raise EOFError()

        out_path = interactive_login(
            platform="freelancer",
            sessions_dir=custom_dir,
            prompt_fn=eof_prompt,
        )
        assert out_path == sess_file
        # Storage state should have been loaded into context
        mock_browser.new_context.assert_called_once_with(storage_state=str(sess_file))
        mock_context.storage_state.assert_called_once_with(path=str(sess_file))


def test_form_filler_auto_detects_default_session(tmp_path: Path):
    filler = PonishaFormFiller()
    project = {
        "url": "https://ponisha.ir/test",
        "suggested_bid": 1500000,
        "delivery_days": 2,
        "proposal": "Proposal text",
    }

    mock_sess = tmp_path / "ponisha.json"
    mock_sess.write_text('{"cookies": []}', encoding="utf-8")

    with patch("core.form_filler.base_filler.has_session", return_value=True), \
         patch("core.form_filler.base_filler.get_session_path", return_value=mock_sess), \
         patch("playwright.sync_api.sync_playwright") as mock_sync_pw:
        mock_p = mock_sync_pw.return_value.__enter__.return_value
        mock_browser = MagicMock()
        mock_p.chromium.launch.return_value = mock_browser

        filler.fill_application(project, headless=True)
        mock_browser.new_context.assert_called_once_with(storage_state=str(mock_sess))


def test_top_level_fill_application_wrapper():
    # Test validation on invalid inputs
    assert fill_application(None)["status"] == "error"
    assert fill_application({})["status"] == "error"
    assert fill_application({"platform": "unknown"})["status"] == "error"

    # Test successful delegation
    valid_proj = {
        "platform": "ponisha",
        "url": "https://ponisha.ir/test",
        "suggested_bid": 1500000,
        "delivery_days": 2,
        "proposal": "Clean proposal",
    }
    with patch.object(PonishaFormFiller, "fill_application", return_value={"status": "ready"}) as mock_fill:
        res = fill_application(valid_proj, dry_run=True)
        assert res["status"] == "ready"
        mock_fill.assert_called_once()


def test_form_filler_manual_inspection_cancel_and_confirm():
    filler = PonishaFormFiller()
    project = {
        "url": "https://ponisha.ir/test",
        "suggested_bid": 1500000,
        "delivery_days": 2,
        "proposal": "Proposal text",
    }

    with patch("playwright.sync_api.sync_playwright") as mock_sync_pw:
        mock_p = mock_sync_pw.return_value.__enter__.return_value
        mock_browser = MagicMock()
        mock_context = MagicMock()
        mock_page = MagicMock()
        mock_p.chromium.launch.return_value = mock_browser
        mock_browser.new_context.return_value = mock_context
        mock_context.new_page.return_value = mock_page

        # 1. User cancels during inspection
        res_cancel = filler.fill_application(
            project,
            dry_run=False,
            headless=False,
            prompt_fn=lambda msg: "cancel",
        )
        assert res_cancel["status"] == "cancelled"
        assert res_cancel["submitted"] is False
        assert "cancelled by user" in res_cancel["details"]

        # 2. User confirms submission by pressing enter
        res_confirm = filler.fill_application(
            project,
            dry_run=False,
            headless=False,
            prompt_fn=lambda msg: "",
        )
        assert res_confirm["status"] == "submitted"
        assert res_confirm["submitted"] is True


