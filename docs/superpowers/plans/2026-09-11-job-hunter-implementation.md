# Job Hunter (Hybrid Engine) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a modular, automated job hunting and bidding system combining lightweight multi-platform scraping, ROI-based triage, AI technical architecture/roadmap drafting, dual reporting (Telegram + Markdown), and human-in-the-loop Playwright form-filling.

**Architecture:** A pipeline orchestrator collects jobs via HTTP scrapers with session cookies, passes them through scam/budget filtering and ROI scoring (`triage.py`), enriches top tiers with AI-generated technical roadmaps and proposals (`architect.py`), saves records into SQLite, dispatches alerts to Telegram/Markdown, and allows semi-automated application via Playwright (`form_filler`).

**Tech Stack:** Python 3.10+, SQLite3, Playwright, PyYAML, urllib/requests, pytest.

**Spec:** [docs/superpowers/specs/2026-09-11-job-hunter-design.md](../../superpowers/specs/2026-09-11-job-hunter-design.md)

## Global Constraints
- Target platforms: Ponisha, Parscoders, Freelancer.com.
- Scopes: Telegram/Bale Bots, Automation (n8n/Python), Translation, Excel, Scraping, Python Scripting.
- Document formatting scope remains disabled.
- Minimum budgets: Iranian >= 500,000 Toman (Translation/Excel) or >= 1,500,000 Toman (Bots/Dev); Foreign >= $10.
- Safety: Playwright form filler must pause for manual inspection before actual submit.
- Database: SQLite at `data/hunter.db` with duplicate prevention via unique job hashes.

---

### Task 1: Configuration & SQLite Database Layer

**Files:**
- Create: `config.yaml`
- Create: `core/db.py`
- Create: `tests/test_db.py`

**Interfaces:**
- Consumes: None
- Produces: `DB` class with methods `init_schema()`, `save_project(proj_dict)`, `get_project(job_id)`, `is_seen(job_hash)`, `list_projects(tier=None, status=None)`

- [ ] **Step 1: Write failing tests for DB operations**

```python
# tests/test_db.py
import pytest
from core.db import DB

def test_db_init_and_deduplication(tmp_path):
    db_file = tmp_path / "test_hunter.db"
    db = DB(str(db_file))
    db.init_schema()
    
    project = {
        "job_hash": "hash_123",
        "platform": "ponisha",
        "platform_id": "101",
        "title": "Telegram Bot",
        "url": "https://ponisha.ir/project/101",
        "budget_min": 1000000,
        "budget_max": 2000000,
        "currency": "IRT",
        "description": "Build a bot",
        "scope": "bots",
        "tier": "A",
        "fit_score": 0.85,
        "status": "new"
    }
    
    saved = db.save_project(project)
    assert saved is True
    assert db.is_seen("hash_123") is True
    assert db.is_seen("non_existent") is False
    
    # Duplicate insert should return False
    assert db.save_project(project) is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_db.py -v`  
Expected: FAIL (No module named `core.db`)

- [ ] **Step 3: Implement `config.yaml` and `core/db.py`**

Create `config.yaml` with platforms, scopes, keywords, budget floors, and Telegram config.  
Implement `DB` class in `core/db.py` with tables `projects` and `applications`.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_db.py -v`  
Expected: PASS

---

### Task 2: Multi-Platform Scraping Engine

**Files:**
- Create: `core/scrapers/base.py`
- Create: `core/scrapers/ponisha.py`
- Create: `core/scrapers/parscoders.py`
- Create: `core/scrapers/freelancer.py`
- Create: `tests/test_scrapers.py`

**Interfaces:**
- Consumes: `config.yaml`
- Produces: `BaseScraper` interface and subclasses yielding standard normalized dict:
  `{"platform", "platform_id", "title", "url", "budget_min", "budget_max", "currency", "description", "skills"}`

- [ ] **Step 1: Write tests with mock data for scrapers**

```python
# tests/test_scrapers.py
from core.scrapers.ponisha import PonishaScraper
from core.scrapers.parscoders import ParscodersScraper
import json

def test_ponisha_parser_from_next_data():
    scraper = PonishaScraper(session_cookie=None)
    mock_html = '''<script id="__NEXT_DATA__">{"props":{"pageProps":{"dehydratedState":{"queries":[{"state":{"data":{"data":[{"id":12,"title":"ربات بله","slug":"bale-bot","description":"توضیح","amount_min":1500000,"amount_max":2500000}]}}}]}}}}</script>'''
    items = scraper.parse_html(mock_html)
    assert len(items) == 1
    assert items[0]["title"] == "ربات بله"
    assert items[0]["budget_min"] == 1500000
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_scrapers.py -v`  
Expected: FAIL (`PonishaScraper` not found)

- [ ] **Step 3: Implement scrapers**

Implement `BaseScraper` in `core/scrapers/base.py` with standard request handling, delay pacing, and user-agent.  
Implement Ponisha extractor (`core/scrapers/ponisha.py`) from `__NEXT_DATA__`.  
Implement Parscoders HTML extractor (`core/scrapers/parscoders.py`).  
Implement Freelancer.com public API client (`core/scrapers/freelancer.py`).

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_scrapers.py -v`  
Expected: PASS

---

### Task 3: Triage, Scam Filter, and ROI Scoring Engine

**Files:**
- Create: `core/triage.py`
- Create: `tests/test_triage.py`

**Interfaces:**
- Consumes: Raw project dict from scrapers and `config.yaml` rules
- Produces: `evaluate_project(project, config)` returning `{"tier": "A"|"B"|"C", "fit_score": float, "scope": str, "is_scam": bool, "rejection_reason": str|None}`

- [ ] **Step 1: Write test for scam detection and scope matching**

```python
# tests/test_triage.py
from core.triage import evaluate_project

def test_scam_detection():
    proj = {"title": "تایپ فایل", "description": "پرداخت اول 50 هزار تومان به عنوان بیعانه", "budget_min": 100000}
    res = evaluate_project(proj, {})
    assert res["is_scam"] is True
    assert res["tier"] == "C"

def test_scope_bots_tier_a():
    proj = {"title": "ساخت ربات تلگرام ووکامرس", "description": "پایتون و تلگرام برای فروشگاه", "budget_min": 2500000, "currency": "IRT"}
    res = evaluate_project(proj, {})
    assert res["is_scam"] is False
    assert res["scope"] == "bots"
    assert res["tier"] == "A"
    assert res["fit_score"] >= 0.75
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_triage.py -v`  
Expected: FAIL (`evaluate_project` not defined)

- [ ] **Step 3: Implement `core/triage.py`**

Implement keyword matching for the 6 scopes: Bots, Automation, Translation, Excel, Scraping, Python Scripting.  
Check scam blacklist phrases (بیعانه، پرداخت اول، 100% upfront).  
Calculate Fit Score and assign Tier A, B, or C based on budget floors and keyword density.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_triage.py -v`  
Expected: PASS

---

### Task 4: AI Architect Engine (Roadmap, Proposal, Pricing)

**Files:**
- Create: `core/architect.py`
- Create: `tests/test_architect.py`

**Interfaces:**
- Consumes: Evaluated project dict (Tier A / B)
- Produces: `generate_architecture(project)` returning:
  `{"suggested_bid": int|float, "delivery_days": int, "tech_stack": list[str], "roadmap": list[str], "proposal": str}`

- [ ] **Step 1: Write test for roadmap and proposal generation**

```python
# tests/test_architect.py
from core.architect import generate_architecture

def test_architect_bot_project():
    proj = {
        "title": "ربات تلگرام ثبت سفارش",
        "description": "ربات پایتون برای دریافت اطلاعات سفارش و ذخیره در دیتابیس",
        "scope": "bots",
        "budget_min": 2000000,
        "budget_max": 3000000,
        "currency": "IRT"
    }
    arch = generate_architecture(proj)
    assert len(arch["roadmap"]) >= 3
    assert "aiogram" in " ".join(arch["tech_stack"]).lower() or "python" in " ".join(arch["tech_stack"]).lower()
    assert arch["suggested_bid"] >= 2000000
    assert len(arch["proposal"]) > 50
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_architect.py -v`  
Expected: FAIL (`generate_architecture` not defined)

- [ ] **Step 3: Implement `core/architect.py`**

Implement template-based and rule-based expert logic for each scope (with optional LLM API fallback if `ANTHROPIC_API_KEY` or `OPENAI_API_KEY` is present).  
Produce clean, non-generic proposals, technical stack specifications, and 3-4 step implementation roadmaps.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_architect.py -v`  
Expected: PASS

---

### Task 5: Dual Reporting Layer (Markdown & Telegram)

**Files:**
- Create: `core/report.py`
- Create: `tests/test_report.py`

**Interfaces:**
- Consumes: List of enriched project dicts
- Produces:
  - `build_markdown_report(projects, output_path)`
  - `format_telegram_message(project)`

- [ ] **Step 1: Write test for report formatting**

```python
# tests/test_report.py
from core.report import format_telegram_message, build_markdown_report

def test_telegram_message_contains_essential_blocks():
    proj = {
        "id": 105,
        "title": "طراحی ربات تلگرام",
        "platform": "ponisha",
        "scope": "bots",
        "budget_min": 2000000,
        "budget_max": 3000000,
        "currency": "IRT",
        "tier": "A",
        "roadmap": ["اتصال به API", "طراحی منوها", "تست نهایی"],
        "tech_stack": ["Python", "aiogram"],
        "proposal": "سلام، پروژه با aiogram قابل انجام است."
    }
    msg = format_telegram_message(proj)
    assert "#105" in msg
    assert "رودمپ" in msg
    assert "پیشنهاد" in msg
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_report.py -v`  
Expected: FAIL (`format_telegram_message` not defined)

- [ ] **Step 3: Implement `core/report.py`**

Implement Telegram message generator with proper Markdown escaping.  
Implement daily report generator writing to `reports/YYYY-MM-DD.md`.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_report.py -v`  
Expected: PASS

---

### Task 6: Session Management & Playwright Form Filler

**Files:**
- Create: `core/auth_helper.py`
- Create: `core/form_filler/base_filler.py`
- Create: `core/form_filler/ponisha_filler.py`
- Create: `core/form_filler/parscoders_filler.py`
- Create: `tests/test_form_filler.py`

**Interfaces:**
- Consumes: Project details (`url`, `suggested_bid`, `delivery_days`, `proposal`) and stored session state
- Produces: `fill_application(project, session_path, dry_run=True)` opening browser and populating form

- [ ] **Step 1: Write test for form filler parameter validation**

```python
# tests/test_form_filler.py
import pytest
from core.form_filler.base_filler import BaseFormFiller

def test_form_filler_validates_required_fields():
    filler = BaseFormFiller()
    incomplete_proj = {"url": "https://ponisha.ir/test"}
    with pytest.raises(ValueError, match="Missing required bid parameters"):
        filler.validate_project(incomplete_proj)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_form_filler.py -v`  
Expected: FAIL (`BaseFormFiller` not defined)

- [ ] **Step 3: Implement `auth_helper.py` and `core/form_filler/`**

Create `auth_helper.py` to launch Chromium, prompt user to log in, and save `storage_state.json`.  
Implement `PonishaFormFiller` and `ParscodersFormFiller` using Playwright to fill bid inputs and pause for user inspection before submission.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_form_filler.py -v`  
Expected: PASS

---

### Task 7: CLI Interface & Telegram Bot Interaction

**Files:**
- Create: `interfaces/cli.py`
- Create: `interfaces/telegram_bot.py`
- Create: `run.py`
- Create: `tests/test_cli.py`

**Interfaces:**
- Consumes: All core modules
- Produces: CLI commands (`scan`, `list`, `apply`, `auth`, `bot`) and interactive Telegram bot webhook/polling handler.

- [ ] **Step 1: Write CLI argument parsing test**

```python
# tests/test_cli.py
from interfaces.cli import build_parser

def test_cli_parser():
    parser = build_parser()
    args = parser.parse_args(["scan", "--mock"])
    assert args.command == "scan"
    assert args.mock is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_cli.py -v`  
Expected: FAIL (`build_parser` not defined)

- [ ] **Step 3: Implement `interfaces/cli.py`, `interfaces/telegram_bot.py`, and `run.py`**

Tie together the pipeline: `scan` executes scrapers -> triage -> architect -> db -> reports.  
Implement `apply <id>` to invoke the appropriate `form_filler`.  
Implement `bot` command to listen for Telegram inline button interactions.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_cli.py -v`  
Expected: PASS

---

## Plan Review & Verification
1. **Spec Coverage:** Verified all 6 scopes, scam filtering, ROI scoring, architecture/roadmap generation, Markdown/Telegram reporting, and Playwright human-in-the-loop form filling are covered.
2. **Self-Review:** No placeholders or vague TODOs; exact signatures and tests specified for all 7 tasks.
