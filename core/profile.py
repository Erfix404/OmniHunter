"""Freelancer profile matrix and personalized proposal helpers."""

from __future__ import annotations

from pathlib import Path
from typing import Any

try:
    import yaml
except Exception:  # pragma: no cover - yaml is a hard dependency in practice
    yaml = None  # type: ignore[assignment]


DEFAULT_PROFILE_DATA: dict[str, Any] = {
    "identity": {
        "name": "Erfan Ashouri",
        "hourly_rate_irt": 1200000,
        "hourly_rate_usd": 25,
        "min_project_irt": 2000000,
        "min_project_usd": 30,
    },
    "skills": [
        {
            "name": "Python",
            "level": "expert",
            "tools": ["Python 3.12", "FastAPI", "SQLite", "Docker"],
            "evidence": "5+ years building production Python services with FastAPI and SQLite",
            "scopes": ["scripting", "automation", "bots", "scraping"],
        },
        {
            "name": "Telegram/Bale bots via aiogram",
            "level": "expert",
            "tools": ["aiogram 3.x", "python-telegram-bot", "Bale Bot API", "Redis", "SQLite"],
            "evidence": "Shipped Cafe Mehras cafe-ordering bot handling concurrent FSM sessions with aiogram 3.x",
            "scopes": ["bots"],
        },
        {
            "name": "Web Scraping with Playwright",
            "level": "advanced",
            "tools": ["Playwright", "BeautifulSoup4", "aiohttp", "pandas"],
            "evidence": "Built TeleRich Playwright crawler extracting 50k+ records with anti-bot and rate-limit handling",
            "scopes": ["scraping"],
        },
        {
            "name": "Process Automation with n8n/FastAPI",
            "level": "advanced",
            "tools": ["n8n", "Webhooks", "FastAPI", "REST APIs", "Cron"],
            "evidence": "Automated Tarjoman order pipeline with n8n webhooks and FastAPI, cutting manual work by 80%",
            "scopes": ["automation", "scripting"],
        },
    ],
    "portfolio": [
        {
            "title": "Cafe Mehras",
            "scope": "bots",
            "result": "Telegram ordering bot serving 2k+ monthly orders with 99% uptime on aiogram FSM",
            "url": "https://github.com/erfix/cafe-mehras-bot",
        },
        {
            "title": "Tarjoman",
            "scope": "automation",
            "result": "n8n + FastAPI order pipeline that cut manual processing time by 80%",
            "url": "https://github.com/erfix/tarjoman-pipeline",
        },
        {
            "title": "TeleRich",
            "scope": "scraping",
            "result": "Playwright crawler extracting 50k+ records into clean CSV/JSON datasets",
            "url": "https://github.com/erfix/telerich-scraper",
        },
    ],
    "tone": {
        "style": "direct, technical, Persian, no greetings; start with the solution architecture",
        "avoid": [
            "سلام و احترام",
            "امیدوارم حالتون خوب باشه",
            "با سلام و احترام",
            "امیدوارم روز خوبی داشته باشید",
            "من یک برنامه نویس با تجربه هستم",
        ],
    },
    "scopes": {
        "preferred": ["bots", "scraping", "automation", "scripting"],
        "willing": ["excel"],
        "declined": ["translation", "formatting"],
    },
}

# Fallback keywords mapping a scope to skill-text signals, used only when a
# skill entry does not declare an explicit ``scopes`` list.
_SCOPE_KEYWORDS: dict[str, list[str]] = {
    "bots": ["bot", "aiogram", "telegram", "bale", "ربات", "بله", "تلگرام", "fsm", "redis"],
    "scraping": ["scrap", "crawl", "playwright", "selenium", "beautifulsoup", "اسکرپ", "خزنده", "استخراج"],
    "automation": ["automat", "n8n", "webhook", "zapier", "وب هوک", "اتوماسیون", "pipeline", "cron"],
    "scripting": ["python", "fastapi", "api", "sqlite", "requests", "اسکریپت", "پایتون"],
    "excel": ["excel", "openpyxl", "pandas", "vba", "اکسل", "ماکرو", "فرمول"],
    "translation": ["translat", "ترجمه", "glossary"],
    "formatting": ["format", "word", "فرمت", "صفحه آرا"],
}

_DEFAULT_PATH_CANDIDATES = ("freelancer_profile.yaml",)


def _deep_copy(data: Any) -> Any:
    if isinstance(data, dict):
        return {k: _deep_copy(v) for k, v in data.items()}
    if isinstance(data, list):
        return [_deep_copy(v) for v in data]
    return data


def _as_float(val: Any) -> float | None:
    if val is None or val == "":
        return None
    try:
        num = float(val)
    except (ValueError, TypeError):
        return None
    return num


def _norm_scope(scope: Any) -> str:
    if not isinstance(scope, str):
        return ""
    return scope.strip().lower()


class FreelancerProfile:
    """Personal profile matrix used to personalize triage and proposals.

    Loads YAML from ``freelancer_profile.yaml`` (or a custom path).  When the
    file is missing or invalid, falls back to a robust built-in default so
    callers never crash.
    """

    def __init__(
        self,
        path: str | Path | None = None,
        data: dict[str, Any] | None = None,
    ) -> None:
        if data is not None and isinstance(data, dict):
            raw = _deep_copy(data)
        else:
            raw = self._load_file(path)
            if raw is None:
                raw = _deep_copy(DEFAULT_PROFILE_DATA)
        if not isinstance(raw, dict):
            raw = _deep_copy(DEFAULT_PROFILE_DATA)
        self._data: dict[str, Any] = raw

    @staticmethod
    def _load_file(path: str | Path | None) -> dict[str, Any] | None:
        candidates: list[Path] = []
        if path is not None:
            candidates.append(Path(path))
        else:
            candidates.extend(Path(p) for p in _DEFAULT_PATH_CANDIDATES)
        for cand in candidates:
            try:
                if not cand.exists() or not cand.is_file():
                    continue
                if yaml is None:
                    return None
                with open(cand, "r", encoding="utf-8") as f:
                    loaded = yaml.safe_load(f)
                if isinstance(loaded, dict):
                    return loaded
                return None
            except Exception:
                return None
        return None

    @property
    def identity(self) -> dict[str, Any]:
        base = _deep_copy(DEFAULT_PROFILE_DATA["identity"])
        custom = self._data.get("identity")
        if isinstance(custom, dict):
            for key in ("name", "hourly_rate_irt", "hourly_rate_usd", "min_project_irt", "min_project_usd"):
                if key in custom and custom[key] is not None:
                    base[key] = custom[key]
        return base

    @property
    def skills(self) -> list[dict[str, Any]]:
        raw = self._data.get("skills")
        if not isinstance(raw, list) or not raw:
            return _deep_copy(DEFAULT_PROFILE_DATA["skills"])
        out: list[dict[str, Any]] = []
        for item in raw:
            if not isinstance(item, dict):
                continue
            out.append(
                {
                    "name": item.get("name", ""),
                    "level": item.get("level", ""),
                    "tools": item.get("tools", []) if isinstance(item.get("tools"), list) else [],
                    "evidence": item.get("evidence", ""),
                    **({"scopes": item["scopes"]} if isinstance(item.get("scopes"), list) else {}),
                }
            )
        return out if out else _deep_copy(DEFAULT_PROFILE_DATA["skills"])

    @property
    def portfolio(self) -> list[dict[str, Any]]:
        raw = self._data.get("portfolio")
        if not isinstance(raw, list) or not raw:
            return _deep_copy(DEFAULT_PROFILE_DATA["portfolio"])
        out: list[dict[str, Any]] = []
        for item in raw:
            if not isinstance(item, dict):
                continue
            out.append(
                {
                    "title": item.get("title", ""),
                    "scope": item.get("scope", ""),
                    "result": item.get("result", ""),
                    "url": item.get("url", ""),
                }
            )
        return out if out else _deep_copy(DEFAULT_PROFILE_DATA["portfolio"])

    @property
    def tone(self) -> dict[str, Any]:
        base = _deep_copy(DEFAULT_PROFILE_DATA["tone"])
        custom = self._data.get("tone")
        if isinstance(custom, dict):
            if isinstance(custom.get("style"), str) and custom.get("style"):
                base["style"] = custom["style"]
            if isinstance(custom.get("avoid"), list):
                base["avoid"] = [str(x) for x in custom["avoid"] if str(x).strip()]
        if not isinstance(base.get("avoid"), list):
            base["avoid"] = list(DEFAULT_PROFILE_DATA["tone"]["avoid"])
        return base

    @property
    def scopes(self) -> dict[str, list[str]]:
        base = _deep_copy(DEFAULT_PROFILE_DATA["scopes"])
        custom = self._data.get("scopes")
        if isinstance(custom, dict):
            for key in ("preferred", "willing", "declined"):
                if isinstance(custom.get(key), list):
                    base[key] = [str(x) for x in custom[key]]
        return base

    def get_relevant_portfolio(self, scope: str) -> list[dict]:
        """Return portfolio items whose ``scope`` matches (case-insensitive)."""
        want = _norm_scope(scope)
        if not want:
            return []
        return [p for p in self.portfolio if _norm_scope(p.get("scope")) == want]

    def get_relevant_evidence(self, scope: str) -> list[str]:
        """Return skill evidence strings relevant to ``scope``."""
        want = _norm_scope(scope)
        if not want:
            return []
        keywords = _SCOPE_KEYWORDS.get(want, [want])
        matched: list[str] = []
        for skill in self.skills:
            declared = skill.get("scopes")
            if isinstance(declared, list) and declared:
                if want in {_norm_scope(s) for s in declared}:
                    ev = skill.get("evidence")
                    if isinstance(ev, str) and ev.strip():
                        matched.append(ev.strip())
                    elif isinstance(ev, list):
                        matched.extend(str(x).strip() for x in ev if str(x).strip())
                    continue
            haystack = " ".join(
                [
                    str(skill.get("name", "")),
                    " ".join(str(t) for t in skill.get("tools", [])),
                    str(skill.get("evidence", "")),
                ]
            ).lower()
            if any(kw in haystack for kw in keywords):
                ev = skill.get("evidence")
                if isinstance(ev, str) and ev.strip():
                    matched.append(ev.strip())
                elif isinstance(ev, list):
                    matched.extend(str(x).strip() for x in ev if str(x).strip())
        # De-duplicate while preserving order
        seen: set[str] = set()
        unique: list[str] = []
        for item in matched:
            if item not in seen:
                seen.add(item)
                unique.append(item)
        return unique

    def is_scope_declined(self, scope: str) -> bool:
        """Return True when ``scope`` is in the declined list."""
        want = _norm_scope(scope)
        if not want:
            return False
        declined = self.scopes.get("declined", [])
        return want in {_norm_scope(s) for s in declined}

    def get_min_budget(self, currency: str) -> float | None:
        """Return the profile's minimum project budget for ``currency``."""
        cur = str(currency or "IRT").strip().upper()
        ident = self.identity
        if cur in ("USD", "$"):
            return _as_float(ident.get("min_project_usd"))
        if cur in ("IRR", "RIAL", "RIALS"):
            val = _as_float(ident.get("min_project_irt"))
            return val * 10 if val is not None else None
        return _as_float(ident.get("min_project_irt"))


def resolve_profile(profile: FreelancerProfile | dict[str, Any] | None) -> FreelancerProfile | None:
    """Coerce ``profile`` into a :class:`FreelancerProfile` or return None.

    Accepts an existing instance (returned as-is), a raw dict (wrapped with
    per-property fallbacks to the built-in defaults), or None (no profile).
    Any other type yields None so callers stay backward compatible.
    """
    if profile is None:
        return None
    if isinstance(profile, FreelancerProfile):
        return profile
    if isinstance(profile, dict):
        try:
            return FreelancerProfile(data=profile)
        except Exception:
            return None
    return None
