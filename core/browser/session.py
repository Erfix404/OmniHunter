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
