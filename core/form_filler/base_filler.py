import sys
from pathlib import Path
from typing import Any

if str(Path(__file__).resolve().parent.parent.parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from core.auth_helper import get_session_path, has_session

# ponytail: sequential Playwright page automation over parallel worker pool; upgrade to Playwright BrowserContext pool if processing >5 applications/min.
# ponytail: CSS selector heuristics over accessibility-tree/AI vision locator; upgrade to visual/AI DOM parser if platforms frequently redesign.
# ponytail: terminal input inspection prompt over GUI approval popup; upgrade to webhook/dashboard approval if running as background service.


class BaseFormFiller:
    platform: str = "generic"

    def validate_project(self, project: dict[str, Any]) -> None:
        """Validate required fields for project bid submission.

        Raises ValueError if url, suggested_bid, delivery_days, or proposal is missing.
        """
        if not isinstance(project, dict):
            raise ValueError("Missing required bid parameters: url, suggested_bid, delivery_days, proposal")

        required = ["url", "suggested_bid", "delivery_days", "proposal"]
        missing = [
            field
            for field in required
            if field not in project
            or project[field] is None
            or (isinstance(project[field], str) and not project[field].strip())
        ]
        if missing:
            raise ValueError(f"Missing required bid parameters: {', '.join(missing)}")

    def _fill_first_matching(
        self,
        page: Any,
        selectors: list[str],
        value: Any,
        field_name: str,
        timeout: int = 2000,
    ) -> None:
        """Try filling each selector in order until one succeeds."""
        for sel in selectors:
            try:
                page.fill(sel, str(value), timeout=timeout)
                return
            except Exception:
                continue
        raise RuntimeError(
            f"Could not find or populate '{field_name}' on {self.platform} using selectors: {selectors}"
        )

    def _click_first_matching(
        self,
        page: Any,
        selectors: list[str],
        action_name: str,
        timeout: int = 2000,
    ) -> None:
        """Try clicking each selector in order until one succeeds."""
        for sel in selectors:
            try:
                page.click(sel, timeout=timeout)
                return
            except Exception:
                continue
        raise RuntimeError(
            f"Could not trigger '{action_name}' on {self.platform} using selectors: {selectors}"
        )

    def _fill_form(self, page: Any, project: dict[str, Any]) -> None:
        """Platform-specific form filling steps. Subclasses must implement."""
        raise NotImplementedError("Subclasses must implement _fill_form")

    def _submit_form(self, page: Any, project: dict[str, Any]) -> None:
        """Platform-specific submission step. Subclasses must implement."""
        raise NotImplementedError("Subclasses must implement _submit_form")

    def fill_application(
        self,
        project: dict[str, Any],
        session_path: str | Path | None = None,
        dry_run: bool = True,
        headless: bool = False,
        prompt_fn: Any = None,
        mode: str = "isolated",
        confirm_submit: bool = False,
        cdp_url: str | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Open project in browser, populate bid parameters, and handle dry-run or submit.

        Args:
            mode: ``"isolated"`` launches a fresh Chromium instance;
                ``"cdp"`` attaches to a running Chrome via
                :mod:`core.browser.live_cdp`.
            confirm_submit: human-in-the-loop gate for CDP mode. When
                ``False``, fields are filled and scrolled into view but
                ``_submit_form`` is never called (``ready_for_review``).
                When ``True`` (or the user confirms via ``prompt_fn``),
                the form is submitted.
        """
        result: dict[str, Any] = {
            "status": "error",
            "platform": self.platform,
            "url": str(project.get("url", "") if isinstance(project, dict) else ""),
            "bid": project.get("suggested_bid") if isinstance(project, dict) else None,
            "delivery_days": project.get("delivery_days") if isinstance(project, dict) else None,
            "submitted": False,
            "details": "",
        }

        try:
            self.validate_project(project)
        except ValueError as e:
            result["details"] = str(e)
            return result

        # Session path resolution
        resolved_session = session_path
        if resolved_session is None and has_session(self.platform):
            resolved_session = get_session_path(self.platform)

        try:
            from playwright.sync_api import sync_playwright

            with sync_playwright() as p:
                if mode == "cdp":
                    from core.browser import live_cdp as live_cdp_mod

                    context = live_cdp_mod.get_live_context(p, cdp_url=cdp_url)
                    page = live_cdp_mod.find_or_open_tab(
                        context, project["url"], project.get("id")
                    )

                    # Populate the bid form
                    self._fill_form(page, project)

                    # Scroll populated form into view (best effort)
                    try:
                        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                    except Exception:
                        pass

                    try:
                        raw_url = getattr(page, "url", project["url"])
                        page_url = raw_url if isinstance(raw_url, str) else project["url"]
                    except Exception:
                        page_url = project["url"]
                    result["url"] = page_url

                    should_submit = bool(confirm_submit)
                    if prompt_fn is not None:
                        msg = (
                            "\nForm populated in live browser. "
                            "Press [Enter] to submit, or type 'cancel' to abort: "
                        )
                        try:
                            try:
                                ans = str(prompt_fn(msg) or "").strip().lower()
                            except TypeError:
                                ans = str(prompt_fn() or "").strip().lower()
                        except (EOFError, KeyboardInterrupt):
                            ans = "cancel"
                        if ans in ("cancel", "abort", "n", "no"):
                            should_submit = False
                        else:
                            should_submit = True

                    if should_submit:
                        self._submit_form(page, project)
                        result["status"] = "success"
                        result["submitted"] = True
                        result["details"] = "Application submitted successfully"
                    else:
                        result["status"] = "ready_for_review"
                        result["submitted"] = False
                        result["details"] = (
                            "Form populated in browser. Waiting for user confirmation."
                        )
                    return result

                browser = p.chromium.launch(headless=headless)
                context_kwargs: dict[str, Any] = {}
                if resolved_session and Path(resolved_session).exists():
                    context_kwargs["storage_state"] = str(resolved_session)

                context = browser.new_context(**context_kwargs)
                page = context.new_page()

                # Navigate to project URL
                page.goto(project["url"], timeout=30000)

                # Populate the bid form
                self._fill_form(page, project)

                if dry_run:
                    result["status"] = "ready"
                    result["submitted"] = False
                    result["details"] = "Form populated in dry-run mode (review in browser; not submitted)"
                    if not headless or prompt_fn is not None:
                        msg = "\n[dry-run] Form filled! Inspect the browser window. Press [Enter] to close browser: "
                        try:
                            if prompt_fn is not None:
                                try:
                                    prompt_fn(msg)
                                except TypeError:
                                    prompt_fn()
                            else:
                                input(msg)
                        except (EOFError, KeyboardInterrupt):
                            pass
                else:
                    cancelled = False
                    if not headless or prompt_fn is not None:
                        msg = (
                            "\n⚠️ Form filled! Inspect the browser window. "
                            "Press [Enter] to submit, or type 'cancel' to abort: "
                        )
                        try:
                            if prompt_fn is not None:
                                try:
                                    ans = str(prompt_fn(msg) or "").strip().lower()
                                except TypeError:
                                    ans = str(prompt_fn() or "").strip().lower()
                            else:
                                ans = input(msg).strip().lower()

                            if ans in ("cancel", "abort", "n", "no"):
                                cancelled = True
                        except (EOFError, KeyboardInterrupt):
                            cancelled = True

                    if cancelled:
                        result["status"] = "cancelled"
                        result["submitted"] = False
                        result["details"] = "Submission cancelled by user during manual inspection"
                    else:
                        self._submit_form(page, project)
                        result["status"] = "submitted"
                        result["submitted"] = True
                        result["details"] = "Application submitted successfully"

                context.close()
                browser.close()

        except Exception as e:
            result["status"] = "error"
            result["submitted"] = False
            result["details"] = f"Automation error: {str(e)}"

        return result
