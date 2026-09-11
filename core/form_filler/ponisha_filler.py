import sys
from pathlib import Path
from typing import Any

if str(Path(__file__).resolve().parent.parent.parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from core.form_filler.base_filler import BaseFormFiller

# ponytail: candidate selector cascades over fixed ID lookup; upgrade to resilient Shadow-DOM/text locators if Ponisha moves to Web Components.


class PonishaFormFiller(BaseFormFiller):
    platform: str = "ponisha"

    BID_SELECTORS = [
        'input[name="amount"]',
        'input[name="price"]',
        'input[name="bid"]',
        'input[id="amount"]',
        'input[id="price"]',
        'input[placeholder*="مبلغ"]',
        'input[placeholder*="پیشنهاد"]',
        'input[type="number"]',
    ]

    DAYS_SELECTORS = [
        'input[name="delivery_days"]',
        'input[name="days"]',
        'input[name="duration"]',
        'input[id="delivery_days"]',
        'input[id="days"]',
        'input[placeholder*="روز"]',
        'input[placeholder*="مدت"]',
    ]

    PROPOSAL_SELECTORS = [
        'textarea[name="proposal"]',
        'textarea[name="description"]',
        'textarea[name="content"]',
        'textarea[name="cover_letter"]',
        'textarea[id="proposal"]',
        'textarea[id="description"]',
        'textarea[placeholder*="پیشنهاد"]',
        'textarea[placeholder*="توضیح"]',
        "textarea",
    ]

    SUBMIT_SELECTORS = [
        'button[type="submit"]',
        'button:has-text("ارسال پیشنهاد")',
        'button:has-text("ثبت پیشنهاد")',
        'button:has-text("ارسال")',
        'input[type="submit"]',
    ]

    def _fill_form(self, page: Any, project: dict[str, Any]) -> None:
        """Fill bid amount, delivery days, and proposal description."""
        bid = project.get("suggested_bid")
        days = project.get("delivery_days")
        proposal = project.get("proposal", "")

        self._fill_first_matching(page, self.BID_SELECTORS, bid, "suggested_bid")
        self._fill_first_matching(page, self.DAYS_SELECTORS, days, "delivery_days")
        self._fill_first_matching(page, self.PROPOSAL_SELECTORS, proposal, "proposal")

    def _submit_form(self, page: Any, project: dict[str, Any]) -> None:
        """Trigger proposal submission on Ponisha."""
        self._click_first_matching(page, self.SUBMIT_SELECTORS, "submit_bid")
