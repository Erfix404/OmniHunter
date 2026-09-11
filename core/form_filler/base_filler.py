import sys
from pathlib import Path
from typing import Any

if str(Path(__file__).resolve().parent.parent.parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from core.auth_helper import get_session_path, has_session

# ponytail: sequential Playwright page automation over parallel worker pool; upgrade to Playwright BrowserContext pool if processing >5 applications/min.
# ponytail: CSS selector heuristics over accessibility-tree/AI vision locator; upgrade to visual/AI DOM parser if platforms frequently redesign.


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
        self, page: Any, selectors: list[str], value: Any, field_name: str
    ) -> None:
        """Try filling each selector in order until one succeeds."""
        for sel in selectors:
            try:
                page.fill(sel, str(value))
                return
            except Exception:
                continue
        raise RuntimeError(
            f"Could not find or populate '{field_name}' on {self.platform} using selectors: {selectors}"
        )

    def _click_first_matching(
        self, page: Any, selectors: list[str], action_name: str
    ) -> None:
        """Try clicking each selector in order until one succeeds."""
        for sel in selectors:
            try:
                page.click(sel)
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
    ) -> dict[str, Any]:
        """Open project in browser, populate bid parameters, and handle dry-run or submit."""
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
                    if not headless:
                        try:
                            page.wait_for_timeout(3000)
                        except Exception:
                            pass
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
