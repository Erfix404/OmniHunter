from typing import Any
import re
from core.scrapers.base import BrowserScraperBase

class KarlancerScraper(BrowserScraperBase):
    platform = "karlancer"

    def __init__(self, base_url: str = "https://karlancer.com", **kwargs):
        super().__init__(**kwargs)
        self.base_url = base_url.rstrip("/")

    def fetch_projects(self, search_query: str = "") -> list[dict[str, Any]]:
        url = f"{self.base_url}/projects"
        html = self.fetch_via_browser(url, wait_selector=".project-card")
        return self.parse_html(html)

    def parse_html(self, html: str) -> list[dict[str, Any]]:
        if not html:
            return []

        projects = []
        card_pattern = re.compile(r'<div class="project-card">.*?</div>', re.DOTALL | re.IGNORECASE)
        for card in card_pattern.findall(html):
            id_match = re.search(r'href="[^"]*?/project/(\d+)"', card)
            if not id_match:
                continue
            
            platform_id = id_match.group(1)
            
            title = "Unknown"
            title_match = re.search(r'<a href="[^"]*?/project/\d+">(.*?)</a>', card)
            if title_match:
                title = title_match.group(1).strip()
                
            projects.append(self.normalize_project(
                platform=self.platform,
                platform_id=platform_id,
                title=title,
                url=f"{self.base_url}/project/{platform_id}",
                budget_min=None,
                budget_max=None,
                currency="IRT",
                description="",
                skills=[]
            ))
            
        return projects
