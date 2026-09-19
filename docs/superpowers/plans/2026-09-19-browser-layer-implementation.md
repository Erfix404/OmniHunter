# Browser Layer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the unified `SessionManager` that powers both live CDP connections to the user's running Chrome (Approval Mode) and isolated headless profiles.

**Architecture:** A new module `core/browser/profiles.py` discovers Chrome profiles from `Local State`. `core/browser/connection.py` handles the low-level Playwright CDP/launch mechanics. `core/browser/session.py` exposes `SessionManager` which ties these together and manages the context lifecycle. Finally, `interfaces/cli.py` exposes `browser` subcommands for testing and discovery.

**Tech Stack:** Python 3.10+, Playwright, JSON, os/sys.

**Spec:** [docs/superpowers/specs/2026-09-19-browser-layer-design.md](../../superpowers/specs/2026-09-19-browser-layer-design.md)

## Global Constraints

- Never attempt to kill or restart `chrome.exe`. If the debug port is unavailable, fail loud.
- Support multi-profile Chrome installations by returning the directory name (e.g. `Profile 11`) and matching email.
- Preserve all existing tests; do not break `run_apply`'s current API signature yet, but rather adapt `auth_helper.py` to use the new `SessionManager` under the hood if needed, or replace its logic cleanly.

---

### Task 10: Chrome Profile Discovery

**Files:**
- Create: `core/browser/profiles.py`
- Create: `tests/test_browser_profiles.py`

**Interfaces:**
- Consumes: Nothing
- Produces: `get_chrome_profiles() -> dict[str, dict[str, Any]]`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_browser_profiles.py
import json
import pytest
from core.browser.profiles import get_chrome_profiles

def test_get_chrome_profiles_parses_local_state(tmp_path, monkeypatch):
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
    monkeypatch.setattr("os.path.expandvars", lambda x: "C:/non/existent/path/Local State")
    profiles = get_chrome_profiles()
    assert profiles == {}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_browser_profiles.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'core.browser'`

- [ ] **Step 3: Implement `core/browser/profiles.py`**

```python
"""Discover Chrome profiles from the local system."""
import json
import os
from typing import Any

def get_chrome_profiles() -> dict[str, dict[str, Any]]:
    """Parse Chrome's Local State to return available profiles.
    
    Returns a dict mapping directory names (e.g. 'Profile 1') to profile info.
    """
    if os.name != "nt":
        return {}
        
    local_state_path = os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\User Data\Local State")
    
    try:
        with open(local_state_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except OSError:
        return {}
        
    profile_data = data.get("profile", {})
    info_cache = profile_data.get("info_cache", {})
    last_used = profile_data.get("last_used", "")
    
    result = {}
    for dir_name, info in info_cache.items():
        result[dir_name] = {
            "name": info.get("name", "Unknown"),
            "email": info.get("user_name", ""),
            "is_last_used": (dir_name == last_used)
        }
        
    return result
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_browser_profiles.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add core/browser/profiles.py tests/test_browser_profiles.py
git commit -m "feat(browser): add chrome profile discovery from local state"
```

---

### Task 11: CDP Connection Mechanics

**Files:**
- Create: `core/browser/connection.py`
- Test: `tests/test_browser_connection.py`

**Interfaces:**
- Consumes: Nothing
- Produces: 
  - `get_active_port() -> tuple[int, str] | None`
  - `connect_live(playwright_instance, timeout: int) -> Browser`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_browser_connection.py
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_browser_connection.py -v`
Expected: FAIL

- [ ] **Step 3: Implement `core/browser/connection.py`**

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_browser_connection.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add core/browser/connection.py tests/test_browser_connection.py
git commit -m "feat(browser): add CDP connection logic"
```

---

### Task 12: SessionManager & CLI Integration

**Files:**
- Create: `core/browser/session.py`
- Modify: `interfaces/cli.py`
- Create: `tests/test_browser_session.py`

**Interfaces:**
- Consumes: `connect_live`, `get_chrome_profiles`
- Produces: `SessionManager` class, `run_browser` CLI command.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_browser_session.py
import pytest
from unittest.mock import MagicMock, patch
from core.browser.session import SessionManager

def test_session_manager_live_mode():
    with patch("playwright.sync_api.sync_playwright") as mock_pw, \
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_browser_session.py -v`
Expected: FAIL

- [ ] **Step 3: Implement `core/browser/session.py`**

```python
"""High-level SessionManager to coordinate browser connections."""
from typing import Any, Literal
from playwright.sync_api import sync_playwright

from core.browser.connection import connect_live

class SessionManager:
    """Manages the Playwright connection lifecycle."""
    
    def __init__(self, mode: Literal["live", "isolated"] = "live", timeout: int = 90000):
        self.mode = mode
        self.timeout = timeout
        self._pw_context = None
        self._browser = None
        self._playwright = None
        self._page = None

    def __enter__(self) -> Any:
        self._pw_context = sync_playwright()
        self._playwright = self._pw_context.__enter__()
        
        if self.mode == "live":
            self._browser = connect_live(self._playwright, timeout=self.timeout)
            contexts = self._browser.contexts
            ctx = contexts[0] if contexts else self._browser.new_context()
            self._page = ctx.new_page()
            return self._page
        else:
            raise NotImplementedError("Isolated mode pending")

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        if self._page:
            try:
                self._page.close()
            except Exception:
                pass
        if self._browser:
            try:
                self._browser.close()  # Detaches without killing Chrome
            except Exception:
                pass
        if self._pw_context:
            self._pw_context.__exit__(exc_type, exc_val, exc_tb)
```

- [ ] **Step 4: Wire CLI command in `interfaces/cli.py`**

Add to `build_parser`:
```python
    # browser
    browser_parser = subparsers.add_parser("browser", help="Manage browser profiles and connections")
    browser_parser.add_argument("--list", action="store_true", help="List Chrome profiles")
    browser_parser.add_argument("--status", action="store_true", help="Check CDP port status")
```

Add `run_browser`:
```python
def run_browser(args: argparse.Namespace) -> None:
    if getattr(args, "list", False):
        from core.browser.profiles import get_chrome_profiles
        profiles = get_chrome_profiles()
        print(f"{'DIR NAME':<14} {'DISPLAY NAME':<20} EMAIL")
        print("-" * 60)
        for k, v in sorted(profiles.items()):
            email = v.get("email") or "-"
            marker = " *" if v.get("is_last_used") else ""
            print(f"{k:<14} {v.get('name'):<20} {email}{marker}")
    elif getattr(args, "status", False):
        from core.browser.connection import get_active_port
        port_info = get_active_port()
        if port_info:
            print(f"Approval Mode Active. Listening on port: {port_info[0]}")
        else:
            print("Approval Mode NOT Active. No DevToolsActivePort found.")
```

Add to `main` dispatch block:
```python
    elif args.command == "browser":
        run_browser(args)
```

- [ ] **Step 5: Run tests and Commit**

Run: `python -m pytest tests/test_browser_session.py -v`
Run: `python run.py browser --status` (manual check)
Commit: `git commit -m "feat(browser): add SessionManager and CLI integration"`
