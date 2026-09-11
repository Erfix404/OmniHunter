import json
import re
from typing import Any
from core.scrapers.base import BaseScraper


class PonishaScraper(BaseScraper):
    # ponytail: parse embedded Next.js JSON state via regex; upgrade to headless browser if hydration moves fully client-side.
    def __init__(
        self,
        session_cookie: Any = None,
        base_url: str = "https://ponisha.ir",
        rate_limit_delay_sec: float = 2.0,
    ):
        super().__init__(
            session_cookie=session_cookie,
            rate_limit_delay_sec=rate_limit_delay_sec,
        )
        self.base_url = base_url.rstrip("/")

    def parse_html(self, html: str) -> list[dict[str, Any]]:
        """Extract project listings from Ponisha HTML __NEXT_DATA__ JSON script."""
        if not html:
            return []

        match = re.search(
            r'<script\s+id="__NEXT_DATA__"[^>]*>(.*?)</script>',
            html,
            re.DOTALL | re.IGNORECASE,
        )
        if not match:
            return []

        try:
            payload = json.loads(match.group(1))
        except (json.JSONDecodeError, TypeError):
            return []

        raw_projects = self._extract_projects_from_payload(payload)
        normalized: list[dict[str, Any]] = []

        for p in raw_projects:
            if not isinstance(p, dict):
                continue
            p_id = p.get("id")
            title = p.get("title")
            if not p_id or not title:
                continue

            slug = p.get("slug", "")
            url = (
                f"{self.base_url}/project/{p_id}/{slug}"
                if slug
                else f"{self.base_url}/project/{p_id}"
            )

            raw_skills = p.get("skills", [])
            skills: list[str] = []
            if isinstance(raw_skills, list):
                for s in raw_skills:
                    if isinstance(s, dict):
                        name = s.get("name") or s.get("title")
                        if name:
                            skills.append(str(name))
                    elif isinstance(s, str) and s.strip():
                        skills.append(s.strip())

            normalized.append(
                self.normalize_project(
                    platform="ponisha",
                    platform_id=p_id,
                    title=title,
                    url=url,
                    budget_min=p.get("amount_min"),
                    budget_max=p.get("amount_max"),
                    currency="IRT",
                    description=p.get("description", "") or "",
                    skills=skills,
                )
            )

        return normalized

    def _extract_projects_from_payload(
        self, payload: Any
    ) -> list[dict[str, Any]]:
        """Recursively locate project list in Next.js payload."""
        # 1. Standard dehydratedState.queries path
        try:
            queries = (
                payload.get("props", {})
                .get("pageProps", {})
                .get("dehydratedState", {})
                .get("queries", [])
            )
            for q in queries:
                data = q.get("state", {}).get("data", {})
                if isinstance(data, dict):
                    candidate = data.get("data") or data.get("projects")
                    if isinstance(candidate, list) and candidate:
                        return candidate
        except (AttributeError, KeyError):
            pass

        # 2. General fallback: inspect pageProps
        page_props = payload.get("props", {}).get("pageProps", {})
        if isinstance(page_props.get("projects"), list):
            return page_props["projects"]

        # 3. Recursive search for list containing items with "amount_min" and "title"
        return self._search_dict_for_projects(payload)

    def _search_dict_for_projects(self, obj: Any) -> list[dict[str, Any]]:
        if isinstance(obj, list):
            if (
                obj
                and isinstance(obj[0], dict)
                and "title" in obj[0]
                and ("amount_min" in obj[0] or "id" in obj[0])
            ):
                return obj
            for item in obj:
                found = self._search_dict_for_projects(item)
                if found:
                    return found
        elif isinstance(obj, dict):
            for v in obj.values():
                found = self._search_dict_for_projects(v)
                if found:
                    return found
        return []

    def fetch_projects(self, search_query: str = "") -> list[dict[str, Any]]:
        """Fetch and parse live projects from Ponisha."""
        url = f"{self.base_url}/search/projects"
        params = {"q": search_query} if search_query else None
        try:
            resp = self.get(url, params=params)
            if resp.status_code == 200:
                return self.parse_html(resp.text)
        except Exception:
            pass
        return []


if __name__ == "__main__":
    scraper = PonishaScraper()
    sample = '<script id="__NEXT_DATA__">{"props":{"pageProps":{"dehydratedState":{"queries":[{"state":{"data":{"data":[{"id":1,"title":"T","amount_min":10}]}}}]}}}}</script>'
    res = scraper.parse_html(sample)
    assert len(res) == 1
    assert res[0]["title"] == "T"
    print("PonishaScraper self-checks passed.")

