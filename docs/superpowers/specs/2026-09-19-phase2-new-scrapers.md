# OmniHunter: Phase 2 - Four New Scrapers (SPA & HTML)

> **Date:** 2026-09-19
> **Component:** Multi-Platform Scrapers
> **Status:** Architectural Design

## 1. Goal
Expand OmniHunter's coverage by adding four new freelance marketplaces: Bitjob, Karlancer, Guru, and LaborX. This requires establishing a robust mechanism to scrape Single Page Applications (SPAs) without abandoning the fast, lightweight HTTP parsing used for traditional HTML sites.

## 2. Context & Constraints
- **Bitjob & Karlancer:** Iranian marketplaces. Both use client-side rendering (SPA). Pure HTTP requests (`requests.get`) return skeletal HTML without project data. They require a real browser to execute JavaScript and wait for DOM population.
- **Guru & LaborX:** International (dollar/crypto) marketplaces. They serve static/traditional HTML or easily parsable JSON APIs.
- **Language Routing:** Bitjob and Karlancer must receive Persian keywords. Guru and LaborX must receive English keywords.

## 3. Architecture

### 3.1. `core/scrapers/base.py` Evolution
We preserve the existing `BaseScraper` for fast HTTP requests. We introduce a new `BrowserScraperBase` class that inherits the normalizer and interface but utilizes the `SessionManager` from Phase 1.

```python
class BrowserScraperBase(BaseScraper):
    """Base class for scrapers that require JavaScript rendering."""
    def fetch_via_browser(self, url: str, wait_selector: str) -> str:
        # Opens SessionManager in isolated mode (headless) or live mode
        # Navigates to URL, waits for wait_selector
        # Returns page.content() (the fully rendered HTML)
```
*Note: Scraping does not strictly require the user's logged-in session, so `BrowserScraperBase` can default to an isolated headless context to avoid popping up windows, but can reuse the live CDP connection if desired.*

### 3.2. New Scraper Modules
1. **`core/scrapers/bitjob.py`:**
   - Inherits: `BrowserScraperBase`
   - Platform ID: `bitjob`
   - Parses the rendered DOM for project cards.
2. **`core/scrapers/karlancer.py`:**
   - Inherits: `BrowserScraperBase`
   - Platform ID: `karlancer`
   - Parses the rendered DOM for project cards.
3. **`core/scrapers/guru.py`:**
   - Inherits: `BaseScraper`
   - Platform ID: `guru`
   - Uses plain HTTP requests.
4. **`core/scrapers/laborx.py`:**
   - Inherits: `BaseScraper`
   - Platform ID: `laborx`
   - Uses plain HTTP requests.

### 3.3. Config & Query Builder Integration
- `config.yaml`: Add the four platforms under `platforms:` with `enabled: true`.
- `core/scrapers/query_builder.py`: Add `"bitjob"` and `"karlancer"` to the `IRANIAN_PLATFORMS` frozenset. Unknown platforms (Guru, LaborX) will automatically route to English keywords, preserving existing logic.
- `interfaces/cli.py`: Instantiate and append the four new scrapers to `scrapers_to_run` if enabled in the config.

## 4. Execution & Testing Strategy
Because we do not have live credentials or active accounts for these new sites mocked out yet, the TDD cycle will rely heavily on localized mock HTML/DOM structures to verify parsing logic independently of network conditions, just like the existing scrapers.
