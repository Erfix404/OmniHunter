# Phase 2: Four New Scrapers (SPA & HTML) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expand OmniHunter by introducing a Playwright-backed scraper base class for SPA sites and adding four new marketplace scrapers (Bitjob, Karlancer, Guru, LaborX).

**Architecture:** We introduce `BrowserScraperBase` in `core/scrapers/base.py` which uses `SessionManager` to fetch fully rendered HTML. We then implement the four new scrapers. Finally, we wire them into `config.yaml`, `query_builder.py`, and `cli.py`.

**Tech Stack:** Python 3.10+, Playwright, BeautifulSoup/Regex.

**Spec:** [docs/superpowers/specs/2026-09-19-phase2-new-scrapers.md](../../superpowers/specs/2026-09-19-phase2-new-scrapers.md)

## Global Constraints

- Never break existing tests.
- `BrowserScraperBase` must securely handle Playwright lifecycle without leaking resources.
- `bitjob` and `karlancer` are Iranian platforms (must be added to `IRANIAN_PLATFORMS` in `query_builder.py` to receive Persian keywords).
- `guru` and `laborx` are foreign platforms (handled implicitly by existing logic to receive English keywords).

---

### Task 13: BrowserScraperBase Implementation

**Files:**
- Modify: `core/scrapers/base.py`
- Modify: `tests/test_scrapers.py`

**Interfaces:**
- Produces: `BrowserScraperBase` class inheriting from `BaseScraper`. It provides `fetch_via_browser(url: str, wait_selector: str) -> str`.

- [ ] **Step 1: Write the failing test**

```python
# Append to tests/test_scrapers.py
from core.scrapers.base import BrowserScraperBase
from unittest.mock import patch, MagicMock

def test_browser_scraper_base_fetch():
    class DummyBrowserScraper(BrowserScraperBase):
        platform = "dummy"
        def fetch_projects(self, query=""):
            return []
            
    scraper = DummyBrowserScraper()
    
    # We mock SessionManager to avoid actually launching Playwright in tests
    with patch("core.scrapers.base.SessionManager") as mock_sm_cls:
        mock_sm = mock_sm_cls.return_value.__enter__.return_value
        mock_sm.goto.return_value = None
        mock_sm.wait_for_selector.return_value = None
        mock_sm.content.return_value = "<html>Dummy Content</html>"
        
        content = scraper.fetch_via_browser("http://dummy.com", ".card")
        
        assert content == "<html>Dummy Content</html>"
        mock_sm.goto.assert_called_once_with("http://dummy.com", timeout=30000)
        mock_sm.wait_for_selector.assert_called_once_with(".card", timeout=15000)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_scrapers.py -v -k "test_browser_scraper_base_fetch"`
Expected: FAIL — `ImportError: cannot import name 'BrowserScraperBase'`

- [ ] **Step 3: Implement `BrowserScraperBase`**

In `core/scrapers/base.py`, import `SessionManager` and add the new class:
```python
from core.browser.session import SessionManager

class BrowserScraperBase(BaseScraper):
    """Base class for scrapers that require JavaScript rendering via Playwright."""
    
    def fetch_via_browser(self, url: str, wait_selector: str, timeout: int = 30000) -> str:
        """Fetch fully rendered HTML using an isolated headless browser session."""
        try:
            with SessionManager(mode="isolated", timeout=timeout) as page:
                page.goto(url, timeout=timeout)
                if wait_selector:
                    try:
                        page.wait_for_selector(wait_selector, timeout=15000)
                    except Exception:
                        pass # Continue even if selector fails, maybe content loaded differently
                return page.content()
        except NotImplementedError:
            # Fallback if isolated mode isn't fully implemented yet, use live mode but headless isn't supported there easily without new context.
            # We'll use live mode as a safe fallback for the MVP.
            with SessionManager(mode="live", timeout=timeout) as page:
                page.goto(url, timeout=timeout)
                if wait_selector:
                    try:
                        page.wait_for_selector(wait_selector, timeout=15000)
                    except Exception:
                        pass
                return page.content()
        except Exception as e:
            print(f"Browser fetch failed: {e}")
            return ""
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_scrapers.py -v -k "test_browser_scraper_base_fetch"`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add core/scrapers/base.py tests/test_scrapers.py
git commit -m "feat(scrapers): add BrowserScraperBase for SPA scraping"
```

---

### Task 14: Four New Scrapers

**Files:**
- Create: `core/scrapers/bitjob.py`
- Create: `core/scrapers/karlancer.py`
- Create: `core/scrapers/guru.py`
- Create: `core/scrapers/laborx.py`
- Modify: `tests/test_scrapers.py`

**Interfaces:**
- Produces: `BitjobScraper`, `KarlancerScraper`, `GuruScraper`, `LaborXScraper`

- [ ] **Step 1: Write the failing tests**

```python
# Append to tests/test_scrapers.py
from core.scrapers.bitjob import BitjobScraper
from core.scrapers.karlancer import KarlancerScraper
from core.scrapers.guru import GuruScraper
from core.scrapers.laborx import LaborXScraper

def test_new_scraper_platforms_are_pinned():
    assert BitjobScraper.platform == "bitjob"
    assert KarlancerScraper.platform == "karlancer"
    assert GuruScraper.platform == "guru"
    assert LaborXScraper.platform == "laborx"

def test_bitjob_scraper_parsing():
    scraper = BitjobScraper()
    html = '''<div class="project-card"><h2><a href="/project/123">Test Bitjob</a></h2><div class="budget">1000 تا 2000 تومان</div></div>'''
    res = scraper.parse_html(html)
    assert len(res) == 1
    assert res[0]["platform_id"] == "123"

def test_guru_scraper_parsing():
    scraper = GuruScraper()
    html = '''<div class="jobRecord"><h2><a href="/job/456">Test Guru</a></h2><div class="budget">$100 - $200</div></div>'''
    res = scraper.parse_html(html)
    assert len(res) == 1
    assert res[0]["currency"] == "USD"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_scrapers.py -v -k "new_scraper"`
Expected: FAIL — `ModuleNotFoundError` for the new scraper modules.

- [ ] **Step 3: Implement the 4 scrapers**

Implement each class using basic Regex/HTML parsing mimicking `ParscodersScraper`.
- `Bitjob` & `Karlancer` inherit `BrowserScraperBase`. Their `fetch_projects` calls `fetch_via_browser`.
- `Guru` & `LaborX` inherit `BaseScraper`. Their `fetch_projects` calls `self.get()`.
(Since we don't have exact DOM structures for these sites yet, implement robust generic regex fallback parsers similar to Parscoders that won't crash on bad HTML).

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_scrapers.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add core/scrapers/ tests/test_scrapers.py
git commit -m "feat(scrapers): implement initial bitjob, karlancer, guru, and laborx scrapers"
```

---

### Task 15: Wiring New Scrapers into Config and CLI

**Files:**
- Modify: `core/scrapers/query_builder.py`
- Modify: `interfaces/cli.py`
- Modify: `tests/test_scrapers.py`

**Interfaces:**
- Consumes: The 4 new scrapers.

- [ ] **Step 1: Modify `query_builder.py`**
Update `IRANIAN_PLATFORMS = frozenset({"ponisha", "parscoders", "bitjob", "karlancer"})`

- [ ] **Step 2: Modify `cli.py`**
Import the 4 new scrapers.
In `run_scan`, append them to `scrapers_to_run` if enabled in config:
```python
if plat == "bitjob":
    scrapers_to_run.append(BitjobScraper(rate_limit_delay_sec=delay))
elif plat == "karlancer":
    scrapers_to_run.append(KarlancerScraper(rate_limit_delay_sec=delay))
elif plat == "guru":
    scrapers_to_run.append(GuruScraper(rate_limit_delay_sec=delay))
elif plat == "laborx":
    scrapers_to_run.append(LaborXScraper(rate_limit_delay_sec=delay))
```

- [ ] **Step 3: Write test verifying IRANIAN_PLATFORMS**
In `tests/test_scrapers.py`, update the `test_scraper_platform_attributes_match_config_keys` test (if necessary) to assert `IRANIAN_PLATFORMS == {"ponisha", "parscoders", "bitjob", "karlancer"}`.

- [ ] **Step 4: Run tests**
Run: `python -m pytest -v`

- [ ] **Step 5: Commit**

```bash
git add core/scrapers/query_builder.py interfaces/cli.py tests/test_scrapers.py
git commit -m "feat(cli): wire new scrapers into pipeline and query builder"
```
