import time
from typing import Any
import requests


class BaseScraper:
    # ponytail: requests.Session with single-threaded pacing; upgrade to httpx/asyncio if crawling >10 req/sec.
    DEFAULT_USER_AGENT = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/128.0.0.0 Safari/537.36"
    )

    def __init__(
        self,
        session_cookie: Any = None,
        rate_limit_delay_sec: float = 1.0,
        user_agent: str | None = None,
    ):
        self.rate_limit_delay_sec = float(rate_limit_delay_sec)
        self.last_request_time = 0.0
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": user_agent or self.DEFAULT_USER_AGENT,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8,application/json",
                "Accept-Language": "fa,en-US;q=0.9,en;q=0.8",
            }
        )
        if session_cookie:
            self._inject_cookies(session_cookie)

    def _inject_cookies(self, session_cookie: Any) -> None:
        """Inject session cookies provided as string, dict, or list of dicts."""
        if isinstance(session_cookie, str):
            for part in session_cookie.split(";"):
                part = part.strip()
                if "=" in part:
                    k, v = part.split("=", 1)
                    self.session.cookies.set(k.strip(), v.strip())
        elif isinstance(session_cookie, dict):
            for k, v in session_cookie.items():
                self.session.cookies.set(str(k), str(v))
        elif isinstance(session_cookie, list):
            for item in session_cookie:
                if isinstance(item, dict) and "name" in item and "value" in item:
                    self.session.cookies.set(item["name"], item["value"])

    def get(self, url: str, **kwargs: Any) -> requests.Response:
        """Perform a rate-limited GET request."""
        elapsed = time.time() - self.last_request_time
        if elapsed < self.rate_limit_delay_sec:
            time.sleep(self.rate_limit_delay_sec - elapsed)

        kwargs.setdefault("timeout", 15)
        response = self.session.get(url, **kwargs)
        self.last_request_time = time.time()
        return response

    def normalize_project(
        self,
        platform: str,
        platform_id: str | int,
        title: str,
        url: str,
        budget_min: float | int | None = None,
        budget_max: float | int | None = None,
        currency: str = "IRT",
        description: str = "",
        skills: list[str] | None = None,
    ) -> dict[str, Any]:
        """Produce the standard normalized project dictionary."""
        p_id = str(platform_id).strip()
        b_min = float(budget_min) if budget_min is not None else None
        b_max = float(budget_max) if budget_max is not None else None

        return {
            "platform": str(platform).strip().lower(),
            "platform_id": p_id,
            "job_hash": f"{platform}_{p_id}",
            "title": str(title).strip(),
            "url": str(url).strip(),
            "budget_min": b_min,
            "budget_max": b_max,
            "currency": str(currency).strip().upper(),
            "description": str(description).strip(),
            "skills": [str(s).strip() for s in (skills or []) if str(s).strip()],
        }


if __name__ == "__main__":
    scraper = BaseScraper()
    item = scraper.normalize_project(
        platform="test",
        platform_id="1",
        title="Title",
        url="https://example.com/1",
        budget_min=100,
        budget_max=200,
    )
    assert item["platform"] == "test"
    assert item["budget_min"] == 100.0
    print("BaseScraper self-checks passed.")

