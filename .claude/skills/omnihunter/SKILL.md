# OmniHunter Super-Skill — Claude Code & Hermes Agent

> **Version:** 1.0 (Phase 5) · **Entry point:** `core/agent_api.py::OmniHunterAgentAPI`
> **Companion copy:** `.claude/skills/omnihunter/SKILL.md` (identical content, skill-loader path)

OmniHunter is an intelligent freelance job-hunting and automation engine for
Iranian (Ponisha, Parscoders, Karlancer) and international (Freelancer, Kaya,
Bitjob, Guru, LaborX) platforms. This super-skill lets an agent **hunt** for
projects, build a **senior-freelancer dossier** (blueprint), **prepare** a
customized proposal, **shortlist** winners, and **fill** the platform bid form —
always with a human in the loop before anything is submitted.

## Operating rules

### Rule 1 — Human-in-the-Loop Gate (NON-NEGOTIABLE)

- **NEVER click submit without explicit user confirmation.** The default path
  is fill-without-submit.
- `fill_tab(..., confirm_submit=False)` (the default) MUST return
  `status="ready_for_review"` with `submitted=False`: fields populated,
  scrolled into view, submission NOT triggered.
- Only when the user explicitly confirms (CLI `--confirm`, or an unambiguous
  "yes, submit it") may `confirm_submit=True` be used, which calls the
  platform `_submit_form` and returns `status="success"`, `submitted=True`.
- In chat, always report what was filled (bid, days, proposal preview) and ask
  for confirmation before submitting.

### Rule 2 — Anti-Cliché Proposal Writing

- Every proposal **starts with the solution architecture**, never a greeting.
- **Banned openers** (NEVER emit): «سلام و احترام»، «امیدوارم حالتون خوب
  باشه»، «با سلام و احترام»، «من یک برنامه‌نویس با تجربه هستم»,
  "hope you are doing well", "I am an experienced developer".
- Required shape: **technical hook → tech stack → roadmap → quality/testing
  commitment → delivery schedule → 1–2 portfolio evidence lines**.
- Keep it under ~300 words, in professional Persian (or the platform's
  language), scoped to the project's actual requirements.

### Rule 3 — Claude Leverage Maximization

- **Prioritize projects with Claude Leverage ≥ 8** (bots, automation,
  scraping, scripting — where AI-assisted delivery is fastest).
- When presenting options, sort by ROI first, then surface `win_probability`
  and `claude_leverage` so the user sees *why* a project ranks highly.
- Deprioritize translation/formatting and anything flagged `is_scam=True`.

## Slash commands & interaction playbook

All commands map 1:1 onto `OmniHunterAgentAPI` methods. CLI equivalents are
shown for terminal use (`python run.py <cmd>`).

### `/hunt [scopes...]` — scan, triage, rank

```python
from core.agent_api import OmniHunterAgentAPI
api = OmniHunterAgentAPI()
top = api.hunt(scopes=["bots", "scraping"], limit=10, sort_by="roi")
# sort_by: "roi" | "win_probability" | "claude_leverage"
```

Playbook:
1. Call `hunt()` (optionally filtered by `scopes`, `platforms`, `min_budget`).
2. Scam projects are already filtered out. Present the top N as a table:
   `id | tier | roi | win% | leverage | title`.
3. Recommend the highest-ROI project with leverage ≥ 8 and ask which to blueprint.

CLI: `python run.py review [--limit 10] [--shortlisted] [--sort roi|win_probability|claude_leverage]`

### `/blueprint <id>` — senior-freelancer dossier

```python
dossier = api.get_blueprint("<job_hash or id>")
# -> {"project": {...}, "triage": {...},
#     "blueprint": {"technical_hook", "prerequisites",
#                   "clarifying_question", "proposal", "roadmap",
#                   "tech_stack", "suggested_bid", "delivery_days",
#                   "pricing_breakdown"}}
```

Playbook:
1. Show the **technical hook**, **prerequisites**, and **clarifying question**
   first — these prove seniority.
2. Then the roadmap and pricing (`suggested_bid`, `delivery_days`).
3. Paste the full proposal last. Offer to customize it
   (`prepare_proposal(bid_amount=..., delivery_days=..., custom_notes=...)`)
   or to shortlist it (`pick(id)`).

CLI: `python run.py blueprint <id>` · `python run.py pick <id>...`

### `/fill <id>` — populate the bid form (gated)

```python
res = api.fill_tab("<job_hash or id>", cdp_url=None, confirm_submit=False)
# -> {"status": "ready_for_review", "submitted": False, ...}
```

Playbook:
1. Default: fill only. Report `bid`, `delivery_days`, and the proposal
   excerpt, then **ask for explicit confirmation**.
2. Only on confirmation, re-run with `confirm_submit=True`.
3. `cdp_url` attaches to live Chrome; omit it for an isolated browser.

CLI: `python run.py fill <id> [--cdp [URL]] [--confirm]`

### `/review` — shortlist triage

```python
shortlisted = api.list_shortlist()
api.pick("<job_hash or id>")  # -> True on success
```

Playbook:
1. Show shortlisted projects; for each, offer `/blueprint` or `/fill`.
2. Never submit from `/review` directly — always go through `/fill`'s gate.

## API quick reference

| Method | Purpose |
|---|---|
| `OmniHunterAgentAPI(config_path="config.yaml", profile_path=None, db_path=None)` | Init config, DB, profile, scrapers |
| `hunt(scopes=None, min_budget=None, platforms=None, limit=10, sort_by="roi")` | Scan → triage → persist → ranked top N |
| `get_blueprint(job_hash_or_id)` | Full dossier incl. hook, roadmap, pricing |
| `prepare_proposal(job_hash_or_id, bid_amount=None, delivery_days=None, custom_notes=None)` | Customize proposal/pricing (persisted) |
| `fill_tab(job_hash_or_id, cdp_url=None, confirm_submit=False)` | Gated form fill |
| `pick(job_hash_or_id) -> bool` | Mark `shortlisted` |
| `list_shortlist() -> list[dict]` | All shortlisted projects |

## Safety & failure modes

- **Submit gate:** if `confirm_submit` is falsy, `_submit_form` is never called.
- **Scam filter:** triage rejects blacklist matches (`is_scam=True`,
  `rejection_reason="scam_detected"`); `hunt()` drops them from results.
- **Unsupported platform:** `fill_tab` raises a clear `ValueError` naming the
  platform instead of opening a wrong form.
- **Missing project:** `get_blueprint` / `prepare_proposal` / `fill_tab` raise
  `ValueError("Project '<id>' not found in database")`.
- **Scraper outage:** a failing platform is skipped; DB-backed history still
  serves ranked results.
