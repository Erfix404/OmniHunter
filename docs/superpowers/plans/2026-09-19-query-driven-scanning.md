# Query-Driven Scanning Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make OmniHunter search each platform with its configured scope keywords instead of fetching a generic unfiltered project list.

**Architecture:** A new pure module `core/scrapers/query_builder.py` derives a language-filtered, deduplicated query list from `config.yaml` scopes for a given platform. `interfaces/cli.py` `run_scan` then issues one targeted request per query per scraper, bounded by `--max-queries`, and optionally narrowed by `--scope`.

**Tech Stack:** Python 3.10+, stdlib `re`, argparse, pytest.

**Spec:** [docs/superpowers/specs/2026-09-11-job-hunter-design.md](../../superpowers/specs/2026-09-11-job-hunter-design.md) (section 2 scopes, section 3 platforms)

## Global Constraints

- Iranian platforms (`ponisha`, `parscoders`) receive **Persian-only** keywords; foreign platform (`freelancer`) receives **English-only** keywords.
- Persian detection is `re.search(r"[؀-ۿ]", keyword)`.
- Only scopes with `enabled: true` contribute keywords. `formatting` is `enabled: false` and must never contribute.
- Duplicate keywords collapse to a single query, preserving first-seen order.
- `build_search_queries` is a **pure function**: no network, no I/O, no global state. It must accept `None` or a malformed config without raising.
- Default `--max-queries` is **0** (unlimited). `--max-queries 0` means unlimited.
- The existing scraper signatures are unchanged: `fetch_projects(query: str = "")` / `fetch_projects(search_query: str = "")` already accept the keyword. The existing passing 113-test suite must still pass.

---

### Task 8: Query Builder Module

**Files:**
- Create: `core/scrapers/query_builder.py`
- Test: `tests/test_query_builder.py`

**Interfaces:**

- Consumes: the parsed `config.yaml` dict (`{"scopes": {key: {"enabled": bool, "keywords": [str]}}}`) and a platform name string.
- Produces:
  ```python
  IRANIAN_PLATFORMS: frozenset[str]  # {"ponisha", "parscoders"}
  def build_search_queries(
      config: dict[str, Any] | None,
      platform: str,
      only_scopes: list[str] | None = None,
      limit: int = 0,
  ) -> list[str]
  ```

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_query_builder.py
import pytest

from core.scrapers.query_builder import build_search_queries


def test_iranian_platform_receives_persian_keywords_only():
    config = {"scopes": {"bots": {"enabled": True, "keywords": ["ربات تلگرام", "telegram bot"]}}}
    assert build_search_queries(config, "ponisha") == ["ربات تلگرام"]


def test_foreign_platform_receives_english_keywords_only():
    config = {"scopes": {"bots": {"enabled": True, "keywords": ["ربات تلگرام", "telegram bot"]}}}
    assert build_search_queries(config, "freelancer") == ["telegram bot"]


def test_disabled_scopes_are_skipped():
    config = {
        "scopes": {
            "bots": {"enabled": True, "keywords": ["telegram bot"]},
            "formatting": {"enabled": False, "keywords": ["convert docx"]},
        }
    }
    assert build_search_queries(config, "freelancer") == ["telegram bot"]


def test_duplicate_keywords_collapse_preserving_order():
    config = {
        "scopes": {
            "bots": {"enabled": True, "keywords": ["telegram bot", "aiogram"]},
            "automation": {"enabled": True, "keywords": ["aiogram", "n8n"]},
        }
    }
    assert build_search_queries(config, "freelancer") == ["telegram bot", "aiogram", "n8n"]


def test_only_scopes_narrows_the_selection():
    config = {
        "scopes": {
            "bots": {"enabled": True, "keywords": ["telegram bot"]},
            "excel": {"enabled": True, "keywords": ["excel"]},
        }
    }
    assert build_search_queries(config, "freelancer", only_scopes=["excel"]) == ["excel"]
    assert build_search_queries(config, "freelancer", only_scopes=[]) == []


def test_limit_truncates():
    config = {"scopes": {"bots": {"enabled": True, "keywords": ["a", "b", "c"]}}}
    assert build_search_queries(config, "freelancer", limit=2) == ["a", "b"]
    assert build_search_queries(config, "freelancer", limit=0) == ["a", "b", "c"]


def test_malformed_config_returns_empty_list():
    assert build_search_queries(None, "ponisha") == []
    assert build_search_queries({}, "ponisha") == []
    assert build_search_queries({"scopes": None}, "ponisha") == []
    assert build_search_queries({"scopes": []}, "ponisha") == []


def test_blank_and_non_string_keywords_are_ignored():
    config = {"scopes": {"bots": {"enabled": True, "keywords": ["  ", "", None, "excel"]}}}
    assert build_search_queries(config, "freelancer") == ["excel"]


def test_unknown_platform_treated_as_foreign():
    config = {"scopes": {"bots": {"enabled": True, "keywords": ["telegram bot"]}}}
    assert build_search_queries(config, "newportal") == ["telegram bot"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_query_builder.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'core.scrapers.query_builder'`

- [ ] **Step 3: Implement `core/scrapers/query_builder.py`**

```python
"""Derive per-platform search queries from the configured scopes.

Iranian marketplaces are queried with Persian keywords and the foreign one
with English keywords, so a request never burns rate limit on a term the
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_query_builder.py -v`
Expected: PASS (9 passed)

- [ ] **Step 5: Commit**

```bash
git add core/scrapers/query_builder.py tests/test_query_builder.py
git commit -m "feat(scrapers): add language-filtered query builder for scoped search"
```

---

### Task 9: Wire Query Builder into CLI Scan

**Files:**
- Modify: `interfaces/cli.py` (`build_parser`, `run_scan`)
- Test: `tests/test_cli.py` (append tests)

**Interfaces:**

- Consumes: `build_search_queries` from Task 8, `platform` attribute on each scraper instance.
- Produces: CLI flags `--max-queries N` (int, default 0) and `--scope KEY[,KEY...]` (comma-separated string, default None) on the `scan` subcommand.

- [ ] **Step 1: Write the failing tests**

```python
# append to tests/test_cli.py

def test_scan_parser_has_query_flags():
    parser = build_parser()
    args = parser.parse_args(["scan", "--mock", "--max-queries", "3", "--scope", "bots,excel"])
    assert args.max_queries == 3
    assert args.scope == "bots,excel"


def test_scan_parser_query_flag_defaults():
    parser = build_parser()
    args = parser.parse_args(["scan"])
    assert args.max_queries == 0
    assert args.scope is None


def test_run_scan_queries_each_scraper_per_keyword(monkeypatch, tmp_path):
    """Each scraper must be called once per keyword, not once total."""
    from interfaces import cli

    calls = []

    class FakeScraper:
        platform = "freelancer"

        def __init__(self, *a, **kw):
            pass

        def fetch_projects(self, query=""):
            calls.append(query)
            return []

    monkeypatch.setattr(cli, "FreelancerScraper", FakeScraper)
    monkeypatch.setattr(cli, "PonishaScraper", FakeScraper)
    monkeypatch.setattr(cli, "ParscodersScraper", FakeScraper)

    cfg = {
        "database": {"path": str(tmp_path / "t.db")},
        "platforms": {"freelancer": {"enabled": True, "rate_limit_delay_sec": 0}},
        "scopes": {"bots": {"enabled": True, "keywords": ["telegram bot", "aiogram"]}},
    }

    args = cli.build_parser().parse_args(["scan", "--platform", "freelancer"])
    cli.run_scan(args, config=cfg)

    assert calls == ["telegram bot", "aiogram"]


def test_run_scan_max_queries_truncates(monkeypatch, tmp_path):
    from interfaces import cli

    calls = []

    class FakeScraper:
        platform = "freelancer"

        def __init__(self, *a, **kw):
            pass

        def fetch_projects(self, query=""):
            calls.append(query)
            return []

    monkeypatch.setattr(cli, "FreelancerScraper", FakeScraper)
    monkeypatch.setattr(cli, "PonishaScraper", FakeScraper)
    monkeypatch.setattr(cli, "ParscodersScraper", FakeScraper)

    cfg = {
        "database": {"path": str(tmp_path / "t.db")},
        "platforms": {"freelancer": {"enabled": True, "rate_limit_delay_sec": 0}},
        "scopes": {"bots": {"enabled": True, "keywords": ["a", "b", "c"]}},
    }

    args = cli.build_parser().parse_args(
        ["scan", "--platform", "freelancer", "--max-queries", "2"]
    )
    cli.run_scan(args, config=cfg)

    assert calls == ["a", "b"]


def test_run_scan_scope_flag_narrows_scopes(monkeypatch, tmp_path):
    from interfaces import cli

    calls = []

    class FakeScraper:
        platform = "freelancer"

        def __init__(self, *a, **kw):
            pass

        def fetch_projects(self, query=""):
            calls.append(query)
            return []

    monkeypatch.setattr(cli, "FreelancerScraper", FakeScraper)
    monkeypatch.setattr(cli, "PonishaScraper", FakeScraper)
    monkeypatch.setattr(cli, "ParscodersScraper", FakeScraper)

    cfg = {
        "database": {"path": str(tmp_path / "t.db")},
        "platforms": {"freelancer": {"enabled": True, "rate_limit_delay_sec": 0}},
        "scopes": {
            "bots": {"enabled": True, "keywords": ["telegram bot"]},
            "excel": {"enabled": True, "keywords": ["excel"]},
        },
    }

    args = cli.build_parser().parse_args(
        ["scan", "--platform", "freelancer", "--scope", "excel"]
    )
    cli.run_scan(args, config=cfg)

    assert calls == ["excel"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_cli.py -v -k "query_flags or per_keyword or max_queries or scope_flag"`
Expected: FAIL — `AttributeError: 'Namespace' object has no attribute 'max_queries'` and assertion failures on the call lists.

- [ ] **Step 3: Add CLI flags in `build_parser`**

Add to the `scan` subparser, immediately after the existing `--notify` argument:

```python
    scan_parser.add_argument(
        "--max-queries",
        type=int,
        default=8,
        help="Maximum search queries per platform (0 = unlimited)",
    )
    scan_parser.add_argument(
        "--scope",
        type=str,
        default=None,
        help="Comma-separated scope keys to scan (e.g. bots,excel)",
    )
```

- [ ] **Step 4: Replace the scrape loop in `run_scan`**

Replace the existing `for scraper in scrapers_to_run:` block with:

```python
            only_scopes = None
            raw_scope_arg = getattr(args, "scope", None)
            if raw_scope_arg:
                only_scopes = [s.strip() for s in raw_scope_arg.split(",") if s.strip()]

            max_queries = getattr(args, "max_queries", 0)

            for scraper in scrapers_to_run:
                platform = getattr(scraper, "platform", "")
                queries = build_search_queries(
                    cfg,
                    platform,
                    only_scopes=only_scopes,
                    limit=max_queries,
                )
                if not queries:
                    logger.warning(
                        "No search queries for platform '%s'; skipping.", platform
                    )
                    continue
                for query in queries:
                    try:
                        fetched = scraper.fetch_projects(query)
                        raw_projects.extend(fetched)
                    except Exception as e:
                        logger.error("Scraper error on '%s' query '%s': %s", platform, query, e)
```

Add the import beside the other `from core...` imports at the top of `interfaces/cli.py`:

```python
from core.scrapers.query_builder import build_search_queries
```

- [ ] **Step 5: Run the full suite**

Run: `python -m pytest -v`
Expected: PASS — the 9 new query-builder tests, the 5 new CLI tests, and all 113 pre-existing tests.

- [ ] **Step 6: Commit**

```bash
git add interfaces/cli.py tests/test_cli.py
git commit -m "feat(cli): drive scan with per-scope search queries"
```

---

## Verification

- [ ] `python -m pytest -v` — full suite green, no regressions in the 113 existing tests
- [ ] `python run.py scan --mock` — mock path still exits 0
- [ ] `python run.py scan --platform freelancer --max-queries 2` — issues exactly 2 Persian-excluded English queries and logs no traceback
