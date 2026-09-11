import json
import sys
from pathlib import Path
from typing import Any, Callable

if str(Path(__file__).resolve().parent.parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# ponytail: synchronous Playwright session helper over async/daemon process; upgrade to persistent browser daemon if auth sessions need auto-refresh.
# ponytail: JSON storage_state file over encrypted credential vault; upgrade to keyring/OS keychain if storing production payment tokens.

DEFAULT_SESSIONS_DIR = Path("data/sessions")

PLATFORM_LOGIN_URLS: dict[str, str] = {
    "ponisha": "https://ponisha.ir/login",
    "parscoders": "https://parscoders.com/login",
    "freelancer": "https://www.freelancer.com/login",
}


def get_session_path(platform: str, sessions_dir: Path | str | None = None) -> Path:
    """Return the absolute or relative Path to a platform's session JSON file."""
    base_dir = Path(sessions_dir or DEFAULT_SESSIONS_DIR)
    safe_platform = platform.strip().lower()
    return base_dir / f"{safe_platform}.json"


def has_session(platform: str, sessions_dir: Path | str | None = None) -> bool:
    """Check whether a non-empty session file exists for the given platform."""
    path = get_session_path(platform, sessions_dir)
    try:
        return path.exists() and path.is_file() and path.stat().st_size > 0
    except OSError:
        return False


def load_session_cookies(
    platform: str, sessions_dir: Path | str | None = None
) -> dict[str, Any] | list[Any] | None:
    """Load session cookies from disk.

    Supports Playwright storage_state format (dict with 'cookies' list),
    raw cookie list, or cookie name-value dict.
    Returns None if no session exists or file is invalid.
    """
    path = get_session_path(platform, sessions_dir)
    if not has_session(platform, sessions_dir):
        return None

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return None

    if isinstance(data, dict):
        if "cookies" in data and isinstance(data["cookies"], list):
            return data["cookies"]
        return data
    elif isinstance(data, list):
        return data

    return None


def save_session_state(
    data: dict[str, Any] | list[Any],
    platform: str,
    sessions_dir: Path | str | None = None,
) -> Path:
    """Save session data (Playwright storage_state or cookie dict/list) to disk."""
    path = get_session_path(platform, sessions_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    return path


def interactive_login(
    platform: str,
    timeout_sec: int = 300,
    headless: bool = False,
    sessions_dir: Path | str | None = None,
    prompt_fn: Callable[[], Any] | None = None,
) -> Path:
    """Launch Chromium for user interactive login and save storage state."""
    from playwright.sync_api import sync_playwright

    norm_platform = platform.strip().lower()
    login_url = PLATFORM_LOGIN_URLS.get(
        norm_platform, f"https://{norm_platform}.com/login"
    )
    session_path = get_session_path(norm_platform, sessions_dir)
    session_path.parent.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        context_kwargs: dict[str, Any] = {}
        if session_path.exists() and session_path.stat().st_size > 0:
            try:
                context_kwargs["storage_state"] = str(session_path)
            except Exception:
                pass

        context = browser.new_context(**context_kwargs)
        page = context.new_page()
        page.goto(login_url, timeout=timeout_sec * 1000)

        prompt = prompt_fn if prompt_fn is not None else input
        print(f"[{norm_platform}] Browser launched. Please log in to your account.")
        print("Once logged in, press [Enter] here in terminal to save session...")
        try:
            prompt()
        except (EOFError, KeyboardInterrupt):
            pass

        context.storage_state(path=str(session_path))
        context.close()
        browser.close()

    return session_path


login_interactive = interactive_login
