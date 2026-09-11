import sys
from pathlib import Path
from typing import Any

if str(Path(__file__).resolve().parent.parent.parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from core.form_filler.base_filler import BaseFormFiller

# ponytail: candidate selector cascades over fixed ID lookup; upgrade to resilient Shadow-DOM/text locators if Parscoders redesigns.


class ParscodersFormFiller(BaseFormFiller):
    platform: str = "parscoders"

    BID_SELECTORS = [
        'input[name="bid_price"]',
        'input[name="price"]',
        'input[name="amount"]',
        'input[id="bid_price"]',
        'input[id="price"]',
        'input[placeholder*="مبلغ"]',
        'input[placeholder*="قیمت"]',
        'input[type="number"]',
    ]

    DAYS_SELECTORS = [
        'input[name="duration"]',
        'input[name="days"]',
        'input[name="delivery_days"]',
        'input[id="duration"]',
        'input[id="days"]',
        'input[placeholder*="مدت"]',
        'input[placeholder*="روز"]',
    ]

    PROPOSAL_SELECTORS = [
        'textarea[name="comment"]',
        'textarea[name="proposal"]',
        'textarea[name="description"]',
        'textarea[id="comment"]',
        'textarea[id="description"]',
        'textarea[placeholder*="پیشنهاد"]',
        'textarea[placeholder*="توضیح"]',
        "textarea",
    ]

    SUBMIT_SELECTORS = [
        'button[type="submit"]',
        'input[type="submit"]',
        'button:has-text("ارسال پیشنهاد")',
        'button:has-text("ثبت پیشنهاد")',
        'button:has-text("ارسال")',
    ]

    def _fill_form(self, page: Any, project: dict[str, Any]) -> None:
        """Fill bid amount, duration days, and proposal comment."""
        bid = project.get("suggested_bid")
        days = project.get("delivery_days")
        proposal = project.get("proposal", "")

        self._fill_first_matching(page, self.BID_SELECTORS, bid, "suggested_bid")
        self._fill_first_matching(page, self.DAYS_SELECTORS, days, "delivery_days")
        self._fill_first_matching(page, self.PROPOSAL_SELECTORS, proposal, "proposal")

    def _submit_form(self, page: Any, project: dict[str, Any]) -> None:
        """Trigger proposal submission on Parscoders."""
        self._click_first_matching(page, self.SUBMIT_SELECTORS, "submit_bid")
