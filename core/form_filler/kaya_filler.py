import sys
from pathlib import Path
from typing import Any

if str(Path(__file__).resolve().parent.parent.parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from core.form_filler.base_filler import BaseFormFiller

# ponytail: candidate selector cascades over fixed ID lookup; upgrade to resilient Shadow-DOM/text locators if Kaya redesigns.


class KayaFormFiller(BaseFormFiller):
    platform: str = "kaya"

    BID_SELECTORS = [
        'input[name="bid"]',
        'input[name="amount"]',
        'input[placeholder*="Bid"]',
        'input[placeholder*="پیشنهاد"]',
    ]

    DAYS_SELECTORS = [
        'input[name="days"]',
        'input[name="delivery_time"]',
        'input[placeholder*="Days"]',
    ]

    PROPOSAL_SELECTORS = [
        'textarea[name="proposal"]',
        'textarea[name="description"]',
        'textarea[placeholder*="proposal"]',
    ]

    SUBMIT_SELECTORS = [
        'button[type="submit"]',
        'button:has-text("Send Proposal")',
        'button:has-text("ارسال پیشنهاد")',
    ]

    def _fill_form(self, page: Any, project: dict[str, Any]) -> None:
        """Fill bid amount, delivery days, and proposal text."""
        bid = project.get("suggested_bid")
        days = project.get("delivery_days")
        proposal = project.get("proposal", "")

        self._fill_first_matching(page, self.BID_SELECTORS, bid, "suggested_bid")
        self._fill_first_matching(page, self.DAYS_SELECTORS, days, "delivery_days")
        self._fill_first_matching(page, self.PROPOSAL_SELECTORS, proposal, "proposal")

    def _submit_form(self, page: Any, project: dict[str, Any]) -> None:
        """Trigger proposal submission on Kaya."""
        self._click_first_matching(page, self.SUBMIT_SELECTORS, "submit_bid")
