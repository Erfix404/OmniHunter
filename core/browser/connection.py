"""Low-level Playwright connection mechanics."""
import os
from typing import Any

def get_active_port() -> tuple[int, str] | None:
    """Read Chrome's DevToolsActivePort file.

    Returns (port, ws_path) or None if unavailable.
    """
    if os.name != "nt":
        return None

    user_data = os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\User Data")
    port_file = os.path.join(user_data, "DevToolsActivePort")

    try:
        with open(port_file, "r", encoding="utf-8") as f:
            lines = [ln.strip() for ln in f if ln.strip()]
        if len(lines) >= 2:
            return int(lines[0]), lines[1]
    except (OSError, ValueError):
        pass
    return None

def connect_live(playwright_instance: Any, timeout: int = 90000) -> Any:
    """Connect to a running Chrome instance via CDP approval mode.

    playwright_instance is the sync_playwright() context manager yield value.
    """
    pf = get_active_port()
    if not pf:
        raise RuntimeError(
            "Chrome is not running in approval mode. No DevToolsActivePort found."
        )

    port, _ = pf
    # Approval mode drops the GUID suffix
    ws_url = f"ws://127.0.0.1:{port}/devtools/browser"

    return playwright_instance.chromium.connect_over_cdp(ws_url, timeout=timeout)
