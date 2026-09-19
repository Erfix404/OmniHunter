# OmniHunter: Browser Layer Architecture (Phase 1)

> **Date:** 2026-09-19
> **Component:** Core Browser & Session Management
> **Status:** Architectural Design

## 1. Goal
Replace the simplistic, single-mode `auth_helper.py` with a robust `SessionManager` that prioritizes connecting to the user's *already-running* Chrome (via Approval Mode CDP) to utilize live, authentic sessions. It provides an isolated Playwright profile as a fallback, and includes a profile-discovery tool to navigate multi-profile Chrome installations.

## 2. Context & Constraints
1. **Chrome 136+ Security:** Chrome ignores `--remote-debugging-port` when using the default user data directory.
2. **Approval Mode:** Chrome 153 allows CDP connections on an ephemeral port written to `DevToolsActivePort` if the user enabled remote debugging in `chrome://inspect`. This requires a WebSocket connection and triggers an "Allow" popup in the UI. HTTP endpoints (like `/json/version`) explicitly return 404 in this mode.
3. **Multi-Profile Chaos:** The user has 11 profiles with overlapping display names (e.g., two "Person 1"s). We must identify profiles by their directory name (e.g., `Profile 11`) and expose the associated email address from `Local State` for clarity.

## 3. Architecture

### 3.1. `core/browser/profiles.py` (Profile Discovery)
A stateless module to read Chrome's `Local State` JSON file.
- **Function:** `get_chrome_profiles() -> dict`
- **Output:** Returns a mapping of directory names (e.g., `Profile 11`) to `{ "name": "hermes", "email": "hermes77pro@...", "is_last_used": True/False }`.
- **Purpose:** Feeds the CLI `--list` command and determines the default profile if the user omits the `--profile` flag.

### 3.2. `core/browser/connection.py` (Connection Logic)
Handles the low-level Playwright connection mechanics.
- **Function `connect_live()`:**
  1. Reads `%LOCALAPPDATA%\Google\Chrome\User Data\DevToolsActivePort`.
  2. Extracts the port and WebSocket path.
  3. Uses Playwright's `chromium.connect_over_cdp("ws://127.0.0.1:PORT/PATH")` with a long timeout (~90s) to allow the user to click "Allow" in Chrome.
- **Function `connect_isolated(platform, headless)`:**
  1. Launches a bundled Chromium instance using a specific `storage_state` JSON from `data/sessions/`.
  2. Used when the user explicitly requests an isolated, non-interfering session.

### 3.3. `core/browser/session.py` (The SessionManager)
The unified interface consumed by `form_filler` and future SPA scrapers.
- **Class `SessionManager`:**
  - Configured with `mode` (`"live"` or `"isolated"`).
  - Manages the Playwright lifecycle (`with sync_playwright() as p:`).
  - Handles cleanup: crucially, calling `browser.close()` on a CDP-connected browser *disconnects* it without killing the user's Chrome process.
  - Exposes `.get_page()` to provide a ready-to-use Playwright Page object.

### 3.4. `interfaces/cli.py` Updates
Adds a `browser` subcommand with three operations:
- `python run.py browser --list`: Pretty-prints the discovered Chrome profiles and emails.
- `python run.py browser --test`: Attempts a `connect_live()` and prints the browser version to verify the CDP handshake and user "Allow" click.
- `python run.py browser --status`: Checks if Chrome is running and if `DevToolsActivePort` exists.

## 4. Integration with Existing Code
- `core/form_filler/base_filler.py` will be updated to instantiate `SessionManager(mode="live")` by default, falling back gracefully with a clear error message if Chrome is closed, prompting the user to either open Chrome or use `--isolated`.
- `auth_helper.py` becomes a thin wrapper around `connect_isolated()` purely for generating the initial `storage_state` files if the user chooses the isolated route.

## 5. Security & Safety
- **No Force-Kill:** The tool will *never* attempt to kill or restart the user's `chrome.exe` process. If the port isn't available, it fails loud.
- **No Secret Extraction:** The tool does not attempt to decrypt Chrome's SQLite cookie databases; it relies entirely on CDP/Playwright to drive the session from the inside.
