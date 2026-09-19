"""Derive per-platform search queries from the configured scopes.

Iranian marketplaces are queried with Persian keywords and the foreign one
with non-Persian keywords, so a request never burns rate limit on a term the
portal's audience does not write in.
"""
import re
from typing import Any

IRANIAN_PLATFORMS = frozenset({"ponisha", "parscoders"})

_PERSIAN_RE = re.compile(r"[؀-ۿ]")


def _is_persian(text: str) -> bool:
    return bool(_PERSIAN_RE.search(text))


def build_search_queries(
    config: dict[str, Any] | None,
    platform: str,
    only_scopes: list[str] | None = None,
    limit: int = 0,
) -> list[str]:
    """Return deduplicated search queries for a platform, filtered by language.

    only_scopes, when given, restricts the contributing scopes to that exact set.
    limit of 0 or less means no truncation.
    """
    if not isinstance(config, dict):
        return []
    scopes = config.get("scopes")
    if not isinstance(scopes, dict):
        return []

    wants_persian = str(platform or "").strip().lower() in IRANIAN_PLATFORMS
    allowed = set(only_scopes) if only_scopes is not None else None

    queries: list[str] = []
    seen: set[str] = set()

    for scope_key, scope_cfg in scopes.items():
        if not isinstance(scope_cfg, dict):
            continue
        if not scope_cfg.get("enabled"):
            continue
        if allowed is not None and scope_key not in allowed:
            continue

        keywords = scope_cfg.get("keywords")
        if not isinstance(keywords, list):
            continue

        for raw in keywords:
            if not isinstance(raw, str):
                continue
            keyword = raw.strip()
            if not keyword:
                continue
            if _is_persian(keyword) is not wants_persian:
                continue
            if keyword in seen:
                continue
            seen.add(keyword)
            queries.append(keyword)

    if limit and limit > 0:
        queries = queries[:limit]
    return queries
