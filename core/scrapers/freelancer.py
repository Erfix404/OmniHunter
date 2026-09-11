from typing import Any
from urllib.parse import urljoin
from core.scrapers.base import BaseScraper


class FreelancerScraper(BaseScraper):
    # ponytail: public REST endpoint without OAuth; upgrade to authenticated Freelancer API v1 if rate limit tightens.
    def __init__(
        self,
        session_cookie: Any = None,
        base_url: str = "https://www.freelancer.com",
        api_url: str = "https://www.freelancer.com/api/projects/0.1/projects/active",
        rate_limit_delay_sec: float = 3.0,
    ):
        super().__init__(
            session_cookie=session_cookie,
            rate_limit_delay_sec=rate_limit_delay_sec,
        )
        self.base_url = base_url.rstrip("/")
        self.api_url = api_url

    def parse_api_response(self, data: dict[str, Any]) -> list[dict[str, Any]]:
        """Parse Freelancer active projects API JSON response into normalized project dicts."""
        if not data or not isinstance(data, dict):
            return []

        # Freelancer structure: {"status": "success", "result": {"projects": [...]}}
        result = data.get("result")
        if isinstance(result, dict):
            raw_projects = result.get("projects", [])
        elif isinstance(result, list):
            raw_projects = result
        else:
            raw_projects = data.get("projects", [])

        if not isinstance(raw_projects, list):
            return []

        normalized: list[dict[str, Any]] = []

        for p in raw_projects:
            if not isinstance(p, dict):
                continue

            p_id = p.get("id")
            title = p.get("title")
            if not p_id or not title:
                continue

            seo_url = p.get("seo_url")
            if seo_url:
                url = f"{self.base_url}/projects/{seo_url.lstrip('/')}"
            else:
                url = f"{self.base_url}/projects/{p_id}"

            budget = p.get("budget", {}) if isinstance(p.get("budget"), dict) else {}
            b_min = budget.get("minimum")
            b_max = budget.get("maximum")

            curr = p.get("currency")
            if isinstance(curr, dict):
                currency_code = curr.get("code", "USD")
            elif isinstance(curr, str) and curr.strip():
                currency_code = curr.strip()
            else:
                currency_code = "USD"

            skills: list[str] = []
            for j in p.get("jobs", []):
                if isinstance(j, dict) and j.get("name"):
                    skills.append(str(j["name"]).strip())
                elif isinstance(j, str) and j.strip():
                    skills.append(j.strip())

            normalized.append(
                self.normalize_project(
                    platform="freelancer",
                    platform_id=str(p_id),
                    title=str(title),
                    url=url,
                    budget_min=b_min,
                    budget_max=b_max,
                    currency=currency_code,
                    description=str(p.get("description", "") or "").strip(),
                    skills=skills,
                )
            )

        return normalized

    def fetch_projects(self, query: str = "", limit: int = 20) -> list[dict[str, Any]]:
        """Query public active projects API with optional keyword and limit."""
        params: dict[str, Any] = {
            "compact": "true",
            "job_details": "true",
            "limit": limit,
        }
        if query:
            params["query"] = query

        try:
            resp = self.get(self.api_url, params=params)
            if resp.status_code == 200:
                return self.parse_api_response(resp.json())
        except Exception:
            pass
        return []


if __name__ == "__main__":
    scraper = FreelancerScraper()
    sample = {
        "result": {
            "projects": [
                {
                    "id": 5,
                    "title": "Job",
                    "budget": {"minimum": 10, "maximum": 20},
                }
            ]
        }
    }
    res = scraper.parse_api_response(sample)
    assert len(res) == 1
    assert res[0]["platform_id"] == "5"
    assert res[0]["budget_min"] == 10.0
    print("FreelancerScraper self-checks passed.")

