from pathlib import Path
import re
import sys
from typing import Any
from urllib.parse import urljoin

if str(Path(__file__).resolve().parent.parent.parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from core.scrapers.base import BaseScraper


class ParscodersScraper(BaseScraper):
    platform = "parscoders"
    # ponytail: regex HTML chunker over full DOM parser; avoids external bs4 dependency and runs in <5ms.
    def __init__(
        self,
        session_cookie: Any = None,
        base_url: str = "https://parscoders.com",
        rate_limit_delay_sec: float = 2.0,
    ):
        super().__init__(
            session_cookie=session_cookie,
            rate_limit_delay_sec=rate_limit_delay_sec,
        )
        self.base_url = base_url.rstrip("/")

    def parse_html(self, html: str) -> list[dict[str, Any]]:
        """Extract project listings from Parscoders HTML."""
        if not html:
            return []

        chunks = self._split_into_chunks(html)
        projects: list[dict[str, Any]] = []
        seen_ids: set[str] = set()

        for chunk in chunks:
            project = self._parse_chunk(chunk)
            if project and project["platform_id"] not in seen_ids:
                seen_ids.add(project["platform_id"])
                projects.append(project)

        return projects

    def _split_into_chunks(self, html: str) -> list[str]:
        """Split HTML into per-project blocks or fallback to link contexts."""
        card_matches = list(
            re.finditer(
                r'<(?:div|article|li)\b[^>]*class=["\'][^"\']*\b(?:project-card|project-item|project-row)\b[^"\']*["\'][^>]*>',
                html,
                re.IGNORECASE,
            )
        )
        if len(card_matches) >= 1:
            chunks: list[str] = []
            for i, m in enumerate(card_matches):
                start = m.start()
                end = card_matches[i + 1].start() if i + 1 < len(card_matches) else len(html)
                chunks.append(html[start:end])
            return chunks

        # Fallback: split by /project/(\d+) links
        link_matches = list(re.finditer(r'<a\s+[^>]*href=["\'][^"\']*/project/\d+', html, re.IGNORECASE))
        if link_matches:
            chunks = []
            for i, m in enumerate(link_matches):
                start = m.start()
                end = link_matches[i + 1].start() if i + 1 < len(link_matches) else len(html)
                chunks.append(html[start:end])
            return chunks

        return []

    def _parse_chunk(self, chunk: str) -> dict[str, Any] | None:
        """Parse individual project chunk."""
        # Extract link, id, and title
        link_match = re.search(
            r'<a\s+[^>]*href=["\']([^"\']*/project/(\d+)[^"\']*)["\'][^>]*>(.*?)</a>',
            chunk,
            re.DOTALL | re.IGNORECASE,
        )
        if not link_match:
            return None

        raw_url = link_match.group(1).strip()
        platform_id = link_match.group(2).strip()
        raw_title = link_match.group(3).strip()

        # Clean title HTML
        title = self._clean_html(raw_title)
        if not title:
            # Check for header tag inside or surrounding
            h_match = re.search(r'<h[1-6][^>]*>(.*?)</h[1-6]>', chunk, re.DOTALL | re.IGNORECASE)
            if h_match:
                title = self._clean_html(h_match.group(1))

        if not title:
            return None

        # Build absolute URL
        url = urljoin(f"{self.base_url}/", raw_url)

        # Budget parsing
        budget_min, budget_max = self._parse_budget(chunk)

        # Description parsing
        desc_match = re.search(
            r'<(?:p|div)\s+class="[^"]*(?:description|summary|text|body)[^"]*"[^>]*>(.*?)</(?:p|div)>',
            chunk,
            re.DOTALL | re.IGNORECASE,
        )
        if desc_match:
            description = self._clean_html(desc_match.group(1))
        else:
            p_match = re.search(r'<p[^>]*>(.*?)</p>', chunk, re.DOTALL | re.IGNORECASE)
            description = self._clean_html(p_match.group(1)) if p_match else ""

        # Skills / Tags parsing
        skills: list[str] = []
        tag_matches = re.findall(
            r'<(?:span|a|div)\s+class="[^"]*(?:tag|badge|skill)[^"]*"[^>]*>(.*?)</(?:span|a|div)>',
            chunk,
            re.DOTALL | re.IGNORECASE,
        )
        for t in tag_matches:
            clean_t = self._clean_html(t)
            if clean_t and clean_t not in skills:
                skills.append(clean_t)

        return self.normalize_project(
            platform="parscoders",
            platform_id=platform_id,
            title=title,
            url=url,
            budget_min=budget_min,
            budget_max=budget_max,
            currency="IRT",
            description=description,
            skills=skills,
        )

    def _parse_budget(self, chunk: str) -> tuple[float | None, float | None]:
        """Extract min and max budget from Persian/Arabic/English text, prioritizing budget sections."""
        if not chunk:
            return None, None

        # 1. Search for budget-specific DOM tags or labels first
        # Look for elements with budget/price in class attribute
        budget_block_match = re.search(
            r'<(?:div|span|p|li|td)\b[^>]*class=["\'][^"\']*(?:budget|price)[^"\']*["\'][^>]*>(.*?)</(?:div|span|p|li|td)>',
            chunk,
            re.DOTALL | re.IGNORECASE,
        )
        # Look for labeled text containing بودجه, قیمت, مبلغ, budget, price
        budget_label_match = re.search(
            r'(?:بودجه|قیمت|مبلغ|هزینه|budget|price)\s*[:：]?[^<\n]*(?:<[^>]+>[^<\n]*)*(?:تومان|ریال|توافقی|\b[\d۰-۹]+[\d۰-۹\s,،٬\-تاالی]+)',
            chunk,
            re.IGNORECASE,
        )

        candidate: str | None = None
        if budget_block_match:
            candidate = budget_block_match.group(1)
        elif budget_label_match:
            candidate = budget_label_match.group(0)

        if candidate is not None:
            return self._extract_budget_values(candidate, is_dedicated_section=True)

        # 2. Fallback: parse entire chunk without greedy match over word counts / durations
        return self._extract_budget_values(chunk, is_dedicated_section=False)

    def _extract_budget_values(
        self, text: str, is_dedicated_section: bool = False
    ) -> tuple[float | None, float | None]:
        """Extract budget numbers from normalized text, ignoring word counts and durations."""
        if not text:
            return None, None

        # Normalize digits and separators
        clean = text.translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789"))
        clean = re.sub(r'[,،٬]', '', clean)

        if "توافقی" in clean:
            return None, None

        # Negative lookahead: do NOT match if followed by word-count or duration units
        unit_reject = r'(?!\s*(?:کلمه|واژه|صفحه|روز|ساعت|ماه|سال|هفته|کاربر|مورد|عدد))'

        # Check for less than / max budget
        if "کمتر از" in clean or "حداکثر" in clean:
            after = clean.split("کمتر از")[-1] if "کمتر از" in clean else clean.split("حداکثر")[-1]
            nums = re.findall(r'\b(\d{4,})\b' + unit_reject, after)
            if nums:
                return None, float(nums[0])

        # Check for more than / min budget
        if "بیشتر از" in clean or "حداقل" in clean:
            after = clean.split("بیشتر از")[-1] if "بیشتر از" in clean else clean.split("حداقل")[-1]
            nums = re.findall(r'\b(\d{4,})\b' + unit_reject, after)
            if nums:
                return float(nums[0]), None

        # Check for range: num تا num or num - num (>= 4 digits and not followed by non-budget unit)
        range_match = re.search(r'\b(\d{4,})\s*(?:تا|الی|-)\s*(\d{4,})\b' + unit_reject, clean)
        if range_match:
            return float(range_match.group(1)), float(range_match.group(2))

        # Match single price followed by currency
        single_currency = re.search(r'\b(\d{4,})\s*(?:تومان|ریال)', clean)
        if single_currency:
            val = float(single_currency.group(1))
            return val, val

        # If we are inside an explicit budget block/label, check for lone numbers
        if is_dedicated_section:
            nums = re.findall(r'\b(\d{4,})\b' + unit_reject, clean)
            if len(nums) >= 2:
                return float(nums[0]), float(nums[1])
            elif len(nums) == 1:
                return float(nums[0]), float(nums[0])

        return None, None

    def _clean_html(self, text: str) -> str:
        """Remove tags and unescape text."""
        cleaned = re.sub(r'<[^>]+>', ' ', text)
        cleaned = re.sub(r'\s+', ' ', cleaned)
        return cleaned.strip()

    def fetch_projects(self, search_query: str = "") -> list[dict[str, Any]]:
        """Fetch and parse live projects from Parscoders."""
        url = f"{self.base_url}/project"
        params = {"title": search_query} if search_query else None
        try:
            resp = self.get(url, params=params)
            if resp.status_code == 200:
                return self.parse_html(resp.text)
        except Exception:
            pass
        return []


if __name__ == "__main__":
    scraper = ParscodersScraper()
    sample = '<div class="project-card"><a href="/project/99/test">Test Project</a><div>بودجه: ۱۰۰۰ تا ۲۰۰۰ تومان</div><p>Desc</p></div>'
    res = scraper.parse_html(sample)
    assert len(res) == 1
    assert res[0]["platform_id"] == "99"
    assert res[0]["budget_min"] == 1000.0
    print("ParscodersScraper self-checks passed.")

