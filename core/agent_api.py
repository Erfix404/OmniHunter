"""Agent SDK for OmniHunter: programmatic hunting, dossiers, and form filling.

This module is the single entry point used by the Claude/Hermes super-skill
(``SKILL.md``), the interactive CLI commands (``review``/``pick``/
``blueprint``/``fill``), and external agents. It orchestrates the existing
building blocks -- scrapers, triage, architect, profile, database, and form
fillers -- without duplicating their logic.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

from core.architect import generate_architecture
from core.db import DB
from core.form_filler import get_form_filler
from core.profile import FreelancerProfile
from core.scrapers.query_builder import build_search_queries
from core.triage import evaluate_project

# ponytail: synchronous SDK orchestration over an async agent loop; upgrade to asyncio if hunt() fans out to 8 platforms concurrently.
# ponytail: DB-backed shortlist over in-memory shortlist; survives restarts and stays consistent with the CLI/telegram bot.

_SORT_KEYS: dict[str, str] = {
    "roi": "roi_score",
    "win_probability": "win_probability",
    "win": "win_probability",
    "claude_leverage": "claude_leverage",
    "leverage": "claude_leverage",
    "claude": "claude_leverage",
}

_PERSIST_COLUMNS = (
    "scope",
    "tier",
    "fit_score",
    "rejection_reason",
    "suggested_bid",
    "delivery_days",
    "tech_stack",
    "roadmap",
    "proposal",
    "technical_hook",
    "prerequisites",
    "clarifying_question",
    "claude_leverage",
    "win_probability",
    "difficulty",
    "pricing_strategy",
    "client_risk",
    "red_flags",
)

_RISK_ORDER: dict[str, int] = {"low": 0, "medium": 1, "high": 2}


def _load_config_file(config_path: str | Path) -> dict[str, Any]:
    path = Path(config_path)
    if not path.exists():
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
            return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _to_db_value(value: Any) -> Any:
    if isinstance(value, (list, dict)):
        return json.dumps(value, ensure_ascii=False)
    return value


def _num(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


def _effective_budget(project: dict[str, Any]) -> float | None:
    vals = [_num(project.get("budget_min")), _num(project.get("budget_max"))]
    vals = [v for v in vals if v is not None]
    if not vals:
        return None
    return max(vals)


def _sort_value(project: dict[str, Any], field: str) -> float:
    val = _num(project.get(field))
    return val if val is not None else 0.0


class OmniHunterAgentAPI:
    """High-level SDK orchestrating hunt -> dossier -> proposal -> fill."""

    def __init__(
        self,
        config_path: str | Path = "config.yaml",
        profile_path: str | Path | None = None,
        db_path: str | Path | None = None,
    ) -> None:
        self.config_path = str(config_path)
        self.config: dict[str, Any] = _load_config_file(config_path)

        resolved_db = (
            str(db_path)
            if db_path is not None
            else str(self.config.get("database", {}).get("path", "data/hunter.db"))
        )
        self.db_path = resolved_db
        self.db = DB(resolved_db)
        self.db.init_schema()
        self._owns_db = True

        if profile_path is not None:
            self.profile = FreelancerProfile(path=profile_path)
        else:
            self.profile = FreelancerProfile()

        self.scrapers: dict[str, Any] = self._build_scrapers()

    # ------------------------------------------------------------------
    # internals
    # ------------------------------------------------------------------

    def _build_scrapers(self) -> dict[str, Any]:
        """Instantiate one scraper per enabled platform from config."""
        # Local imports keep module import light when only the DB is needed.
        from core.scrapers.bitjob import BitjobScraper
        from core.scrapers.freelancer import FreelancerScraper
        from core.scrapers.guru import GuruScraper
        from core.scrapers.karlancer import KarlancerScraper
        from core.scrapers.kaya import KayaScraper
        from core.scrapers.laborx import LaborXScraper
        from core.scrapers.parscoders import ParscodersScraper
        from core.scrapers.ponisha import PonishaScraper

        classes: dict[str, Any] = {
            "ponisha": PonishaScraper,
            "parscoders": ParscodersScraper,
            "freelancer": FreelancerScraper,
            "bitjob": BitjobScraper,
            "karlancer": KarlancerScraper,
            "guru": GuruScraper,
            "laborx": LaborXScraper,
            "kaya": KayaScraper,
        }
        plat_cfgs = self.config.get("platforms", {})
        if not isinstance(plat_cfgs, dict) or not plat_cfgs:
            plat_cfgs = {name: {"enabled": True} for name in classes}

        scrapers: dict[str, Any] = {}
        for name, cls in classes.items():
            cfg = plat_cfgs.get(name, {})
            if isinstance(cfg, dict) and cfg.get("enabled", True) is False:
                continue
            delay = 2.0
            if isinstance(cfg, dict):
                try:
                    delay = float(cfg.get("rate_limit_delay_sec", 2.0 if name != "freelancer" else 3.0))
                except (ValueError, TypeError):
                    delay = 2.0
            try:
                scrapers[name] = cls(rate_limit_delay_sec=delay)
            except Exception:
                continue
        return scrapers

    def _persist_enrichment(self, job_hash: str, fields: dict[str, Any]) -> None:
        updates = {k: _to_db_value(v) for k, v in fields.items() if k in _PERSIST_COLUMNS and v is not None}
        if not updates or not job_hash:
            return
        set_clause = ", ".join(f"{col} = ?" for col in updates)
        try:
            self.db.conn.execute(
                f"UPDATE projects SET {set_clause}, updated_at = CURRENT_TIMESTAMP WHERE job_hash = ?",
                (*updates.values(), job_hash),
            )
            self.db.conn.commit()
        except Exception:
            pass

    def _triage_view(self, project: dict[str, Any]) -> dict[str, Any]:
        red_flags = project.get("red_flags")
        if not isinstance(red_flags, list):
            red_flags = []
        return {
            "tier": project.get("tier"),
            "fit_score": project.get("fit_score"),
            "scope": project.get("scope"),
            "is_scam": bool(project.get("is_scam")),
            "rejection_reason": project.get("rejection_reason"),
            "estimated_hours": project.get("estimated_hours"),
            "roi_score": project.get("roi_score"),
            "claude_leverage": project.get("claude_leverage"),
            "win_probability": project.get("win_probability"),
            "difficulty": project.get("difficulty"),
            "pricing_strategy": project.get("pricing_strategy"),
            "client_risk": project.get("client_risk") or "low",
            "red_flags": red_flags,
        }

    # ------------------------------------------------------------------
    # public API
    # ------------------------------------------------------------------

    def hunt(
        self,
        scopes: list[str] | None = None,
        min_budget: float | None = None,
        platforms: list[str] | None = None,
        limit: int = 10,
        sort_by: str = "roi",
        max_client_risk: str = "medium",
    ) -> list[dict[str, Any]]:
        """Scan platforms, triage, persist, and return the top N projects.

        Live scraping failures never abort the hunt: the DB-backed pool of
        previously saved projects is always consulted as a fallback.
        """
        wanted = [str(p).strip().lower() for p in platforms] if platforms else None
        targets = wanted if wanted is not None else list(self.scrapers.keys())

        seen: set[str] = set()
        fresh: list[dict[str, Any]] = []
        for plat in targets:
            scraper = self.scrapers.get(plat)
            if scraper is None:
                continue
            try:
                queries = build_search_queries(self.config, plat, only_scopes=scopes, limit=0)
            except Exception:
                queries = []
            if not queries:
                if scopes is not None:
                    continue
                queries = [""]
            for query in queries:
                try:
                    fetched = scraper.fetch_projects(query) or []
                except Exception:
                    continue
                for raw in fetched:
                    if not isinstance(raw, dict):
                        continue
                    job_hash = str(raw.get("job_hash") or "")
                    if job_hash and job_hash in seen:
                        continue
                    if job_hash:
                        seen.add(job_hash)
                    triage = evaluate_project(raw, self.config, self.profile)
                    raw.update(triage)
                    if not raw.get("is_scam") and raw.get("tier") in ("A", "B"):
                        try:
                            raw.update(generate_architecture(raw, self.config, self.profile))
                        except Exception:
                            pass
                    if job_hash:
                        try:
                            if not self.db.is_seen(job_hash):
                                self.db.save_project(raw)
                            saved = self.db.get_project(job_hash)
                            if saved and saved.get("id") is not None:
                                raw["id"] = saved["id"]
                        except Exception:
                            pass
                    fresh.append(raw)

        pool: dict[str, dict[str, Any]] = {}
        for proj in fresh:
            key = str(proj.get("job_hash") or "")
            if key:
                pool[key] = proj
        try:
            stored = self.db.list_projects()
        except Exception:
            stored = []
        for proj in stored:
            key = str(proj.get("job_hash") or "")
            if key and key not in pool:
                pool[key] = proj

        candidates = list(pool.values())
        if scopes is not None:
            wanted_scopes = set(scopes)
            candidates = [p for p in candidates if p.get("scope") in wanted_scopes]
        if wanted is not None:
            wanted_set = set(wanted)
            candidates = [p for p in candidates if str(p.get("platform") or "").lower() in wanted_set]
        if min_budget is not None:
            try:
                floor = float(min_budget)
            except (ValueError, TypeError):
                floor = None
            if floor is not None:
                kept: list[dict[str, Any]] = []
                for p in candidates:
                    eff = _effective_budget(p)
                    if eff is None or eff >= floor:
                        kept.append(p)
                candidates = kept

        # Scam filtering: fresh triage flags plus the persisted rejection reason.
        candidates = [
            p
            for p in candidates
            if not p.get("is_scam") and p.get("rejection_reason") != "scam_detected"
        ]

        # Client-risk filtering: exclude projects riskier than max_client_risk.
        risk_cap = _RISK_ORDER.get(str(max_client_risk or "medium").strip().lower(), 1)
        filtered: list[dict[str, Any]] = []
        for p in candidates:
            risk = str(p.get("client_risk") or "low").strip().lower()
            if _RISK_ORDER.get(risk, 0) <= risk_cap:
                filtered.append(p)
        candidates = filtered

        sort_field = _SORT_KEYS.get(str(sort_by or "roi").strip().lower(), "roi_score")
        candidates.sort(
            key=lambda p: (_sort_value(p, sort_field), _sort_value(p, "fit_score")),
            reverse=True,
        )
        if limit is not None and limit > 0:
            candidates = candidates[:limit]
        return candidates

    def get_blueprint(self, job_hash_or_id: str | int) -> dict[str, Any]:
        """Return the full senior-freelancer dossier for a stored project."""
        project = self.db.get_project(job_hash_or_id)
        if not project:
            raise ValueError(f"Project '{job_hash_or_id}' not found in database")

        triage = evaluate_project(project, self.config, self.profile)
        merged = dict(project)
        merged.update(triage)
        arch = generate_architecture(merged, self.config, self.profile)

        self._persist_enrichment(
            str(project.get("job_hash") or ""),
            {**triage, **arch},
        )

        currency = str(project.get("currency") or merged.get("currency") or "IRT")
        estimated_hours = triage.get("estimated_hours")
        suggested_bid = arch.get("suggested_bid")
        hourly: float | None = None
        if estimated_hours and suggested_bid:
            try:
                hourly = round(float(suggested_bid) / float(estimated_hours), 2)
            except (ValueError, TypeError, ZeroDivisionError):
                hourly = None

        blueprint = {
            "technical_hook": arch.get("technical_hook"),
            "prerequisites": arch.get("prerequisites"),
            "clarifying_question": arch.get("clarifying_question"),
            "proposal": arch.get("proposal"),
            "roadmap": arch.get("roadmap"),
            "tech_stack": arch.get("tech_stack"),
            "suggested_bid": suggested_bid,
            "delivery_days": arch.get("delivery_days"),
            "pricing_breakdown": {
                "currency": currency,
                "suggested_bid": suggested_bid,
                "delivery_days": arch.get("delivery_days"),
                "estimated_hours": estimated_hours,
                "effective_hourly_rate": hourly,
            },
        }
        refreshed = self.db.get_project(job_hash_or_id) or project
        return {
            "project": refreshed,
            "triage": self._triage_view({**project, **triage}),
            "blueprint": blueprint,
        }

    def prepare_proposal(
        self,
        job_hash_or_id: str | int,
        bid_amount: float | None = None,
        delivery_days: int | None = None,
        custom_notes: str | None = None,
    ) -> dict[str, Any]:
        """Customize proposal text and pricing, persisting the result."""
        project = self.db.get_project(job_hash_or_id)
        if not project:
            raise ValueError(f"Project '{job_hash_or_id}' not found in database")

        base_proposal = str(project.get("proposal") or "").strip()
        if not base_proposal:
            arch = generate_architecture(project, self.config, self.profile)
            base_proposal = str(arch.get("proposal") or "")
            if project.get("suggested_bid") is None and arch.get("suggested_bid") is not None:
                project["suggested_bid"] = arch["suggested_bid"]
            if project.get("delivery_days") is None and arch.get("delivery_days") is not None:
                project["delivery_days"] = arch["delivery_days"]

        proposal = base_proposal
        notes = str(custom_notes or "").strip()
        if notes and notes not in proposal:
            proposal = f"{proposal.rstrip()}\n\n{notes}".strip()

        final_bid = bid_amount if bid_amount is not None else project.get("suggested_bid")
        final_days = delivery_days if delivery_days is not None else project.get("delivery_days")

        job_hash = str(project.get("job_hash") or "")
        if job_hash:
            try:
                self.db.conn.execute(
                    "UPDATE projects SET proposal = ?, suggested_bid = ?, delivery_days = ?,"
                    " updated_at = CURRENT_TIMESTAMP WHERE job_hash = ?",
                    (proposal, final_bid, final_days, job_hash),
                )
                self.db.conn.commit()
            except Exception:
                pass

        updated = self.db.get_project(job_hash_or_id) or project
        return {
            "project": updated,
            "proposal": proposal,
            "suggested_bid": final_bid,
            "delivery_days": final_days,
            "custom_notes": notes or None,
        }

    def fill_tab(
        self,
        job_hash_or_id: str | int,
        cdp_url: str | None = None,
        confirm_submit: bool = False,
    ) -> dict[str, Any]:
        """Populate the bid form in a live tab (CDP) or isolated browser.

        Human-in-the-loop gate: with ``confirm_submit=False`` the form is
        filled and scrolled into view but never submitted
        (``status="ready_for_review"``).
        """
        project = self.db.get_project(job_hash_or_id)
        if not project:
            raise ValueError(f"Project '{job_hash_or_id}' not found in database")

        if (
            project.get("suggested_bid") is None
            or project.get("delivery_days") is None
            or not str(project.get("proposal") or "").strip()
        ):
            arch = generate_architecture(project, self.config, self.profile)
            self._persist_enrichment(str(project.get("job_hash") or ""), arch)
            project = self.db.get_project(job_hash_or_id) or project

        platform = str(project.get("platform") or "")
        filler = get_form_filler(platform)

        mode = "cdp" if cdp_url is not None else "isolated"
        kwargs: dict[str, Any] = {"mode": mode, "confirm_submit": confirm_submit}
        if cdp_url:
            # A truthy URL is passed through; None/"" falls back to
            # connect_live auto-discovery inside live_cdp.
            kwargs["cdp_url"] = cdp_url
        if mode == "isolated":
            kwargs["dry_run"] = not confirm_submit
            kwargs["headless"] = True

        result = filler.fill_application(project, **kwargs)
        if not isinstance(result, dict):
            result = {
                "status": "error",
                "platform": platform,
                "url": str(project.get("url") or ""),
                "bid": project.get("suggested_bid"),
                "delivery_days": project.get("delivery_days"),
                "submitted": False,
                "details": "Form filler returned an unexpected result",
            }

        # Normalize the confirmation gate: without explicit confirmation a
        # non-submitted fill is always reported as ready_for_review.
        if (
            not confirm_submit
            and not result.get("submitted")
            and result.get("status") in ("ready", "success", "ready_for_review")
        ):
            result["status"] = "ready_for_review"
            result["details"] = result.get("details") or (
                "Form populated in browser. Waiting for user confirmation."
            )
        return result

    def pick(self, job_hash_or_id: str | int) -> bool:
        """Shortlist a project for action."""
        try:
            return bool(self.db.update_status(job_hash_or_id, "shortlisted"))
        except Exception:
            return False

    def list_shortlist(self) -> list[dict[str, Any]]:
        """Return all shortlisted projects."""
        try:
            return self.db.list_projects(status="shortlisted")
        except Exception:
            return []

    def close(self) -> None:
        """Close the underlying database connection."""
        if not getattr(self, "_owns_db", True):
            return
        try:
            self.db.close()
        except Exception:
            pass
