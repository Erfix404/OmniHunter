from typing import Any
import re
from core.scrapers.base import BaseScraper

class LaborXScraper(BaseScraper):
    platform = "laborx"

    def __init__(self, base_url: str = "https://laborx.com", **kwargs):
        super().__init__(**kwargs)
        self.base_url = base_url.rstrip("/")

    def fetch_projects(self, search_query: str = "") -> list[dict[str, Any]]:
        url = f"{self.base_url}/jobs"
        if search_query:
            url += f"?q={search_query}"
        resp = self.get(url)
        if resp and resp.status_code == 200:
            return self.parse_html(resp.text)
        return []

    def parse_html(self, html: str) -> list[dict[str, Any]]:
        if not html:
            return []

        projects = []
        card_pattern = re.compile(r'<div class="job-card">.*?</div>', re.DOTALL | re.IGNORECASE)
        for card in card_pattern.findall(html):
            id_match = re.search(r'href="[^"]*?/job/(\d+)"', card)
            if not id_match:
                continue
            
            platform_id = id_match.group(1)
            
            title = "Unknown"
            title_match = re.search(r'<a href="[^"]*?/job/\d+">(.*?)</a>', card)
            if title_match:
                title = title_match.group(1).strip()
                
            projects.append(self.normalize_project(
                platform=self.platform,
                platform_id=platform_id,
                title=title,
                url=f"{self.base_url}/job/{platform_id}",
                budget_min=None,
                budget_max=None,
                currency="USD",
                description="",
                skills=[]
            ))
            
        return projects
