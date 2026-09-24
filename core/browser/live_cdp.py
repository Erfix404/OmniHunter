"""Live Chrome CDP tab attachment helpers.

Connects to a running Chrome instance (launched with remote debugging)
and finds or opens the project tab for human-in-the-loop form filling.
"""
from typing import Any


def get_live_context(
    playwright_instance: Any,
    cdp_url: str | None = None,
    timeout: int = 30000,
) -> Any:
    """Connect to running Chrome and return a browser context.

    Args:
        playwright_instance: the ``sync_playwright()`` context value.
        cdp_url: optional CDP endpoint, e.g.
            ``ws://127.0.0.1:9222/devtools/browser`` or
            ``http://127.0.0.1:9222``. When omitted, falls back to
            :func:`core.browser.connection.connect_live`.
        timeout: connection timeout in milliseconds.

    Returns:
        ``browser.contexts[0]`` if one exists, else a new context.

    Raises:
        RuntimeError: with an actionable message when Chrome is not
            reachable with remote debugging enabled.
    """
    try:
        if cdp_url:
            browser = playwright_instance.chromium.connect_over_cdp(
                cdp_url, timeout=timeout
            )
        else:
            from core.browser.connection import connect_live

            browser = connect_live(playwright_instance, timeout=timeout)
    except Exception as e:
        raise RuntimeError(
            "Chrome is not running with remote debugging. "
            "Launch Chrome with --remote-debugging-port=9222 and retry. "
            f"Details: {e}"
        ) from e

    try:
        contexts = getattr(browser, "contexts", [])
        if contexts:
            return contexts[0]
        return browser.new_context()
    except Exception as e:
        raise RuntimeError(
            "Chrome is not running with remote debugging. "
            f"Could not obtain a browser context. Details: {e}"
        ) from e


def find_or_open_tab(context: Any, url: str, project_id: Any = None) -> Any:
    """Find the project tab or open it.

    Iterates through ``context.pages``; if any page URL matches ``url``
    or contains ``project_id``, brings it to front and returns it.
    Otherwise opens a new page, navigates to ``url``, and returns it.
    """
    for page in getattr(context, "pages", []):
        try:
            page_url = str(getattr(page, "url", ""))
        except Exception:
            continue
        if page_url == url or url in page_url:
            try:
                page.bring_to_front()
            except Exception:
                pass
            return page
        if project_id is not None and str(project_id) in page_url:
            try:
                page.bring_to_front()
            except Exception:
                pass
            return page

    page = context.new_page()
    page.goto(url, timeout=30000)
    return page
