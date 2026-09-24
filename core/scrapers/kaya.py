"""Scraper for Kaya.ir — an Iranian marketplace mirroring Freelancer.com projects."""

import re
from typing import Any

from core.scrapers.base import BaseScraper

# Currency symbols/codes recognized in Kaya budget strings.
_CURRENCY_MAP = {
    "EUR": "EUR", "€": "EUR",
    "USD": "USD", "$": "USD",
    "GBP": "GBP", "£": "GBP",
    "INR": "INR", "₹": "INR",
    "IRT": "IRT",
}


class KayaScraper(BaseScraper):
    platform = "kaya"

    def __init__(self, base_url: str = "https://kaya.ir", **kwargs: Any):
        super().__init__(**kwargs)
        self.base_url = base_url.rstrip("/")

    # ------------------------------------------------------------------
    # Fetching
    # ------------------------------------------------------------------

    def fetch_projects(self, search_query: str = "") -> list[dict[str, Any]]:
        url = f"{self.base_url}/jobs"
        if search_query:
            url += f"?q={search_query}"
        resp = self.get(url)
        if resp and resp.status_code == 200:
            return self.parse_html(resp.text)
        return []

    # ------------------------------------------------------------------
    # Parsing
    # ------------------------------------------------------------------

    def parse_html(self, html: str) -> list[dict[str, Any]]:
        if not html:
            return []

        projects: list[dict[str, Any]] = []

        # Kaya renders job cards inside <section class="group font-IranSansX ...">
        # or as generic containers with links to /jobs/{id}.
        # We split by section tags first; fall back to link-based extraction.
        card_pattern = re.compile(
            r'<section\b[^>]*class="[^"]*group\s+font-IranSansX[^"]*"[^>]*>.*?</section>',
            re.DOTALL | re.IGNORECASE,
        )
        cards = card_pattern.findall(html)

        if not cards:
            # Fallback: extract per-job chunks anchored on each /jobs/{id} link.
            # We capture the smallest enclosing <div|article|li|section> whose
            # closing tag follows the link, including any surrounding content.
            link_pattern = re.compile(
                r'<(?:div|article|li|section)\b[^>]*>'
                r'(?:(?!<(?:div|article|li|section)\b)[\s\S])*?'
                r'href="[^"]*?/jobs/\d+[^"]*"[\s\S]*?</(?:div|article|li|section)>',
                re.IGNORECASE,
            )
            cards = link_pattern.findall(html)

        for card in cards:
            project = self._parse_card(card)
            if project:
                projects.append(project)

        return projects

    def _parse_card(self, card: str) -> dict[str, Any] | None:
        # Extract job id from /jobs/{id} link
        id_match = re.search(r'/jobs/(\d+)', card)
        if not id_match:
            return None

        platform_id = id_match.group(1)

        # Title: first anchor text pointing to /jobs/{id}, or first heading text.
        title = "Unknown"
        title_match = re.search(
            r'<a\s[^>]*href="[^"]*?/jobs/' + re.escape(platform_id) + r'[^"]*"[^>]*>(.*?)</a>',
            card, re.DOTALL | re.IGNORECASE,
        )
        if title_match:
            title = re.sub(r'<[^>]+>', '', title_match.group(1)).strip()
        if title == "Unknown":
            heading_match = re.search(r'<h[1-6][^>]*>(.*?)</h[1-6]>', card, re.DOTALL | re.IGNORECASE)
            if heading_match:
                title = re.sub(r'<[^>]+>', '', heading_match.group(1)).strip()

        # Description
        desc = ""
        desc_match = re.search(r'<p[^>]*>(.*?)</p>', card, re.DOTALL | re.IGNORECASE)
        if desc_match:
            desc = re.sub(r'<[^>]+>', '', desc_match.group(1)).strip()

        # Skills — typically rendered as <span> or <a> tags inside a skills/tags container.
        skills: list[str] = []
        skills_container = re.search(
            r'<(?:div|ul)[^>]*class="[^"]*(?:skills|tags|badges)[^"]*"[^>]*>(.*?)</(?:div|ul)>',
            card, re.DOTALL | re.IGNORECASE,
        )
        if skills_container:
            skills = [
                re.sub(r'<[^>]+>', '', s).strip()
                for s in re.findall(r'<(?:span|a|li)[^>]*>(.*?)</(?:span|a|li)>', skills_container.group(1), re.DOTALL)
                if re.sub(r'<[^>]+>', '', s).strip()
            ]

        # Budget — patterns like "30 - 250 (EUR)Fixed" or "8 - 15 (USD)Hourly"
        budget_min, budget_max, currency, payment_type = self._parse_budget(card)

        # Competition level
        proposals_count = self._parse_competition(card)

        project = self.normalize_project(
            platform=self.platform,
            platform_id=platform_id,
            title=title,
            url=f"{self.base_url}/jobs/{platform_id}",
            budget_min=budget_min,
            budget_max=budget_max,
            currency=currency,
            description=desc,
            skills=skills,
        )
        project["proposals_count"] = proposals_count
        project["payment_type"] = payment_type
        return project

    # ------------------------------------------------------------------
    # Budget parsing
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_budget(text: str) -> tuple[float | None, float | None, str, str]:
        """Extract budget range, currency and payment type from card text.

        Handles formats like:
          "30 - 250 (EUR)Fixed"
          "8 - 15 (USD)Hourly"
          "$250 - $750 Fixed"
          "€30 - €250"
        """
        # Strip HTML tags for cleaner matching.
        clean = re.sub(r'<[^>]+>', ' ', text)

        currency = "USD"
        payment_type = "fixed"

        # Pattern: number - number (CURRENCY)PaymentType
        budget_match = re.search(
            r'([\d,.]+)\s*-\s*([\d,.]+)\s*\((\w+)\)\s*(Fixed|Hourly)',
            clean, re.IGNORECASE,
        )
        if budget_match:
            bmin = float(budget_match.group(1).replace(',', ''))
            bmax = float(budget_match.group(2).replace(',', ''))
            raw_cur = budget_match.group(3).upper()
            currency = _CURRENCY_MAP.get(raw_cur, raw_cur)
            payment_type = budget_match.group(4).lower()
            return bmin, bmax, currency, payment_type

        # Pattern without parenthesised currency: "$30 - $250 Fixed"
        budget_match2 = re.search(
            r'([€$£₹])\s*([\d,.]+)\s*-\s*[€$£₹]?\s*([\d,.]+)\s*(Fixed|Hourly)?',
            clean, re.IGNORECASE,
        )
        if budget_match2:
            symbol = budget_match2.group(1)
            currency = _CURRENCY_MAP.get(symbol, "USD")
            bmin = float(budget_match2.group(2).replace(',', ''))
            bmax = float(budget_match2.group(3).replace(',', ''))
            if budget_match2.group(4):
                payment_type = budget_match2.group(4).lower()
            return bmin, bmax, currency, payment_type

        return None, None, currency, payment_type

    # ------------------------------------------------------------------
    # Competition parsing
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_competition(text: str) -> int:
        """Derive proposals_count from competition level text."""
        clean = re.sub(r'<[^>]+>', ' ', text)
        low_pattern = re.compile(r'Low\s+Competetion|کم\s*رقابت', re.IGNORECASE)
        high_pattern = re.compile(r'High\s+Competetion|پر\s*رقابت', re.IGNORECASE)

        if low_pattern.search(clean):
            return 3
        if high_pattern.search(clean):
            return 25
        return 10
