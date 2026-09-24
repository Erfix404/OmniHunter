"""Tests for Phase 5: OmniHunterAgentAPI SDK and review/pick/blueprint/fill CLI."""

from argparse import Namespace
from unittest.mock import MagicMock, patch

import pytest

from core.agent_api import OmniHunterAgentAPI
from core.db import DB
from interfaces.cli import (
    build_parser,
    main,
    run_blueprint,
    run_fill,
    run_pick,
    run_review,
)


BOT_PROJECT = {
    "platform": "ponisha",
    "platform_id": "sdk_bot_1",
    "job_hash": "ponisha_sdk_bot_1",
    "title": "ساخت ربات تلگرام فروشگاهی با پایتون و aiogram",
    "url": "https://ponisha.ir/project/sdk_bot_1",
    "budget_min": 3000000,
    "budget_max": 6000000,
    "currency": "IRT",
    "description": "پیاده‌سازی ربات تلگرام با فریمورک aiogram متصل به دیتابیس و درگاه پرداخت.",
    "skills": ["Python", "Telegram Bot", "aiogram"],
}

SCRAPE_PROJECT = {
    "platform": "parscoders",
    "platform_id": "sdk_scrape_1",
    "job_hash": "parscoders_sdk_scrape_1",
    "title": "Python Web Scraping Pipeline with Playwright",
    "url": "https://parscoders.com/project/sdk_scrape_1",
    "budget_min": 50,
    "budget_max": 150,
    "currency": "USD",
    "description": "Need automated web scraping script using Playwright for data extraction.",
    "skills": ["Python", "Web Scraping", "Playwright"],
}

SCAM_PROJECT = {
    "platform": "ponisha",
    "platform_id": "sdk_scam_1",
    "job_hash": "ponisha_sdk_scam_1",
    "title": "تایپ و ترجمه متون",
    "url": "https://ponisha.ir/project/sdk_scam_1",
    "budget_min": 5000000,
    "budget_max": 10000000,
    "currency": "IRT",
    "description": "واریز بیعانه و کارمزد اولیه قبل از تحویل فایل الزامی است.",
    "skills": ["تایپ"],
}


def _make_api(tmp_path, **kwargs):
    db_path = str(tmp_path / "agent_api.db")
    cfg_path = tmp_path / "agent_cfg.yaml"
    cfg_path.write_text("database:\n  path: dummy\n", encoding="utf-8")
    return OmniHunterAgentAPI(config_path=str(cfg_path), db_path=db_path, **kwargs)


# ----------------------------------------------------------------------
# initialization
# ----------------------------------------------------------------------

def test_agent_api_init_defaults(tmp_path):
    db_path = str(tmp_path / "defaults.db")
    api = OmniHunterAgentAPI(config_path="nonexistent-config.yaml", db_path=db_path)
    try:
        assert api.config == {}
        assert api.db_path == db_path
        assert api.profile is not None
        assert isinstance(api.scrapers, dict) and len(api.scrapers) >= 1
    finally:
        api.close()


def test_agent_api_init_custom_paths(tmp_path):
    cfg_path = tmp_path / "custom.yaml"
    cfg_path.write_text(
        "database:\n  path: inner.db\n"
        "platforms:\n  ponisha:\n    enabled: true\n  parscoders:\n    enabled: false\n",
        encoding="utf-8",
    )
    profile_path = tmp_path / "profile.yaml"
    profile_path.write_text(
        "identity:\n  name: Test User\n  min_project_irt: 1000\n  min_project_usd: 5\n",
        encoding="utf-8",
    )
    db_path = str(tmp_path / "custom.db")
    api = OmniHunterAgentAPI(
        config_path=str(cfg_path), profile_path=str(profile_path), db_path=db_path
    )
    try:
        assert api.config["platforms"]["parscoders"]["enabled"] is False
        assert "parscoders" not in api.scrapers
        assert "ponisha" in api.scrapers
        assert api.profile.identity.get("name") == "Test User"
    finally:
        api.close()


# ----------------------------------------------------------------------
# hunt()
# ----------------------------------------------------------------------

def _patch_scrapers(api, mapping):
    # Neutralize every scraper first so no test ever hits the live network;
    # then install the projects each named platform should return.
    for name in list(api.scrapers.keys()):
        quiet = MagicMock()
        quiet.fetch_projects.return_value = []
        api.scrapers[name] = quiet
    for name, projects in mapping.items():
        if name in api.scrapers:
            fake = MagicMock()
            fake.fetch_projects.side_effect = lambda q="", _p=list(projects): [dict(p) for p in _p]
            api.scrapers[name] = fake
        else:
            fake = MagicMock()
            fake.fetch_projects.side_effect = lambda q="", _p=list(projects): [dict(p) for p in _p]
            api.scrapers[name] = fake


def test_hunt_scans_triage_sorts_and_filters_scam(tmp_path):
    api = _make_api(tmp_path)
    try:
        _patch_scrapers(api, {"ponisha": [BOT_PROJECT, SCAM_PROJECT]})
        results = api.hunt(limit=10, sort_by="roi")
        hashes = [p["job_hash"] for p in results]
        assert SCAM_PROJECT["job_hash"] not in hashes
        assert BOT_PROJECT["job_hash"] in hashes
        # Persisted with triage + architect enrichment
        stored = api.db.get_project(BOT_PROJECT["job_hash"])
        assert stored is not None
        assert stored["tier"] in ("A", "B")
        assert stored["proposal"]
        assert stored["claude_leverage"] is not None
        assert stored["win_probability"] is not None
    finally:
        api.close()


def test_hunt_sorting_and_filters(tmp_path):
    api = _make_api(tmp_path)
    try:
        _patch_scrapers(api, {"ponisha": [BOT_PROJECT], "parscoders": [SCRAPE_PROJECT]})
        by_roi = api.hunt(limit=10, sort_by="roi")
        assert by_roi[0]["job_hash"] == BOT_PROJECT["job_hash"]

        by_win = api.hunt(limit=10, sort_by="win_probability")
        assert {p["job_hash"] for p in by_win} == {
            BOT_PROJECT["job_hash"],
            SCRAPE_PROJECT["job_hash"],
        }
        wins = [p.get("win_probability") or 0 for p in by_win]
        assert wins == sorted(wins, reverse=True)

        by_lev = api.hunt(limit=10, sort_by="claude_leverage")
        assert len(by_lev) == 2

        bots_only = api.hunt(scopes=["bots"])
        assert [p["job_hash"] for p in bots_only] == [BOT_PROJECT["job_hash"]]

        rich_only = api.hunt(min_budget=1_000_000)
        assert [p["job_hash"] for p in rich_only] == [BOT_PROJECT["job_hash"]]

        ponisha_only = api.hunt(platforms=["ponisha"])
        assert [p["job_hash"] for p in ponisha_only] == [BOT_PROJECT["job_hash"]]

        limited = api.hunt(limit=1, sort_by="roi")
        assert len(limited) == 1
    finally:
        api.close()


def test_hunt_survives_scraper_outage_via_db_fallback(tmp_path):
    api = _make_api(tmp_path)
    try:
        api.db.save_project({**BOT_PROJECT, "tier": "A", "roi_score": 500000.0,
                              "win_probability": 0.8, "claude_leverage": 9,
                              "fit_score": 0.9, "status": "new", "scope": "bots"})
        for name in api.scrapers:
            broken = MagicMock()
            broken.fetch_projects.side_effect = RuntimeError("portal down")
            api.scrapers[name] = broken
        results = api.hunt(limit=5)
        assert [p["job_hash"] for p in results] == [BOT_PROJECT["job_hash"]]
    finally:
        api.close()


# ----------------------------------------------------------------------
# get_blueprint()
# ----------------------------------------------------------------------

def test_get_blueprint_returns_full_dossier(tmp_path):
    api = _make_api(tmp_path)
    try:
        _patch_scrapers(api, {"ponisha": [BOT_PROJECT]})
        api.hunt()
        dossier = api.get_blueprint(BOT_PROJECT["job_hash"])
        assert set(dossier.keys()) == {"project", "triage", "blueprint"}
        blueprint = dossier["blueprint"]
        for field in ("technical_hook", "prerequisites", "clarifying_question",
                      "proposal", "roadmap", "suggested_bid", "delivery_days",
                      "pricing_breakdown"):
            assert blueprint[field] not in (None, "", []), field
        assert isinstance(blueprint["roadmap"], list) and len(blueprint["roadmap"]) >= 3
        assert isinstance(blueprint["prerequisites"], list) and blueprint["prerequisites"]
        assert len(blueprint["proposal"]) > 50
        assert blueprint["pricing_breakdown"]["suggested_bid"] == blueprint["suggested_bid"]
        # Triage view carries the Phase-1 enrichment fields.
        for field in ("tier", "fit_score", "scope", "is_scam", "claude_leverage",
                      "win_probability", "difficulty", "pricing_strategy",
                      "client_risk", "red_flags"):
            assert field in dossier["triage"], field
        assert dossier["triage"]["client_risk"] in ("low", "medium", "high")
        assert isinstance(dossier["triage"]["red_flags"], list)
        # Works by integer id too.
        by_id = api.get_blueprint(dossier["project"]["id"])
        assert by_id["project"]["job_hash"] == BOT_PROJECT["job_hash"]
    finally:
        api.close()


def test_get_blueprint_missing_project(tmp_path):
    api = _make_api(tmp_path)
    try:
        with pytest.raises(ValueError, match="not found"):
            api.get_blueprint("no-such-hash")
    finally:
        api.close()


# ----------------------------------------------------------------------
# prepare_proposal()
# ----------------------------------------------------------------------

def test_prepare_proposal_modifies_fields_cleanly(tmp_path):
    api = _make_api(tmp_path)
    try:
        _patch_scrapers(api, {"ponisha": [BOT_PROJECT]})
        api.hunt()
        original = api.db.get_project(BOT_PROJECT["job_hash"])["proposal"]
        res = api.prepare_proposal(
            BOT_PROJECT["job_hash"],
            bid_amount=7770000,
            delivery_days=4,
            custom_notes="تحویل با داکیومنت کامل.",
        )
        assert res["suggested_bid"] == 7770000
        assert res["delivery_days"] == 4
        assert "تحویل با داکیومنت کامل." in res["proposal"]
        assert original in res["proposal"]
        stored = api.db.get_project(BOT_PROJECT["job_hash"])
        assert stored["suggested_bid"] == 7770000
        assert stored["delivery_days"] == 4
        assert "تحویل با داکیومنت کامل." in stored["proposal"]

        # Defaults keep stored values when overrides are omitted.
        res2 = api.prepare_proposal(BOT_PROJECT["job_hash"])
        assert res2["suggested_bid"] == 7770000
        assert res2["delivery_days"] == 4
    finally:
        api.close()


def test_prepare_proposal_missing_project(tmp_path):
    api = _make_api(tmp_path)
    try:
        with pytest.raises(ValueError, match="not found"):
            api.prepare_proposal("ghost")
    finally:
        api.close()


# ----------------------------------------------------------------------
# fill_tab()
# ----------------------------------------------------------------------

def test_fill_tab_confirmation_gate(tmp_path):
    api = _make_api(tmp_path)
    try:
        _patch_scrapers(api, {"ponisha": [BOT_PROJECT]})
        api.hunt()
        with patch("core.agent_api.get_form_filler") as mock_factory:
            filler = MagicMock()
            filler.fill_application.return_value = {
                "status": "ready_for_review",
                "platform": "ponisha",
                "url": BOT_PROJECT["url"],
                "bid": 5000000,
                "delivery_days": 3,
                "submitted": False,
                "details": "Form populated in browser. Waiting for user confirmation.",
            }
            mock_factory.return_value = filler

            res = api.fill_tab(BOT_PROJECT["job_hash"])
            assert res["status"] == "ready_for_review"
            assert res["submitted"] is False
            _, kwargs = filler.fill_application.call_args
            assert kwargs["mode"] == "isolated"
            assert kwargs["confirm_submit"] is False

            filler.fill_application.return_value = {
                "status": "success",
                "platform": "ponisha",
                "url": BOT_PROJECT["url"],
                "bid": 5000000,
                "delivery_days": 3,
                "submitted": True,
                "details": "Application submitted successfully",
            }
            res2 = api.fill_tab(
                BOT_PROJECT["job_hash"],
                cdp_url="ws://127.0.0.1:9222/devtools/browser",
                confirm_submit=True,
            )
            assert res2["status"] == "success"
            assert res2["submitted"] is True
            _, kwargs2 = filler.fill_application.call_args
            assert kwargs2["mode"] == "cdp"
            assert kwargs2["cdp_url"] == "ws://127.0.0.1:9222/devtools/browser"
            assert kwargs2["confirm_submit"] is True
    finally:
        api.close()


def test_fill_tab_missing_project(tmp_path):
    api = _make_api(tmp_path)
    try:
        with pytest.raises(ValueError, match="not found"):
            api.fill_tab("ghost")
    finally:
        api.close()


# ----------------------------------------------------------------------
# pick() / list_shortlist()
# ----------------------------------------------------------------------

def test_pick_and_list_shortlist(tmp_path):
    api = _make_api(tmp_path)
    try:
        _patch_scrapers(api, {"ponisha": [BOT_PROJECT]})
        api.hunt()
        assert api.list_shortlist() == []
        assert api.pick(BOT_PROJECT["job_hash"]) is True
        shortlisted = api.list_shortlist()
        assert len(shortlisted) == 1
        assert shortlisted[0]["job_hash"] == BOT_PROJECT["job_hash"]
        assert shortlisted[0]["status"] == "shortlisted"
        assert api.pick("ghost-hash") is False
    finally:
        api.close()


# ----------------------------------------------------------------------
# CLI: review / pick / blueprint / fill
# ----------------------------------------------------------------------

def test_cli_parsers_for_new_commands():
    parser = build_parser()
    args = parser.parse_args(["review", "--limit", "5", "--shortlisted", "--sort", "win_probability"])
    assert args.command == "review"
    assert args.limit == 5
    assert args.shortlisted is True
    assert args.sort == "win_probability"

    args = parser.parse_args(["pick", "1", "abc"])
    assert args.command == "pick"
    assert args.ids == ["1", "abc"]

    args = parser.parse_args(["blueprint", "42"])
    assert args.command == "blueprint"
    assert args.job_id == "42"

    args = parser.parse_args(["fill", "42", "--confirm"])
    assert args.command == "fill"
    assert args.job_id == "42"
    assert args.confirm is True

    args = parser.parse_args(["fill", "42", "--cdp", "ws://127.0.0.1:9222/x"])
    assert args.cdp == "ws://127.0.0.1:9222/x"


def test_cli_review_pick_blueprint(tmp_path, capsys):
    db = DB(str(tmp_path / "cli_phase5.db"))
    db.init_schema()
    db.save_project({**BOT_PROJECT, "tier": "A", "roi_score": 800000.0,
                     "win_probability": 0.85, "claude_leverage": 9,
                     "fit_score": 0.9, "status": "new", "scope": "bots",
                     "suggested_bid": 5000000, "delivery_days": 3,
                     "proposal": "پروپوزال تستی برای بررسی."})
    db.save_project({**SCRAPE_PROJECT, "tier": "B", "roi_score": 10.0,
                     "win_probability": 0.5, "claude_leverage": 9,
                     "fit_score": 0.6, "status": "new", "scope": "scraping",
                     "suggested_bid": 100, "delivery_days": 2,
                     "proposal": "Another test proposal."})

    # review (unapplied pool, sorted by roi)
    reviewed = run_review(Namespace(limit=10, shortlisted=False, sort="roi"), db=db)
    assert len(reviewed) == 2
    assert reviewed[0]["job_hash"] == BOT_PROJECT["job_hash"]
    out = capsys.readouterr().out
    assert "Review" in out

    # pick shortlists
    picked = run_pick(Namespace(ids=[BOT_PROJECT["job_hash"], "ghost"]), db=db)
    assert picked == [BOT_PROJECT["job_hash"]]
    out = capsys.readouterr().out
    assert "NOT FOUND" in out

    # review --shortlisted shows only the pick
    short_only = run_review(Namespace(limit=10, shortlisted=True, sort="roi"), db=db)
    assert [p["job_hash"] for p in short_only] == [BOT_PROJECT["job_hash"]]

    # blueprint renders the dossier
    dossier = run_blueprint(Namespace(job_id=BOT_PROJECT["job_hash"]), db=db)
    assert dossier["blueprint"]["proposal"]
    out = capsys.readouterr().out
    assert "Blueprint" in out


def test_cli_fill_delegates_with_gate(tmp_path):
    db = DB(str(tmp_path / "cli_fill.db"))
    db.init_schema()
    db.save_project({**BOT_PROJECT, "tier": "A", "status": "new", "scope": "bots",
                     "suggested_bid": 5000000, "delivery_days": 3,
                     "proposal": "پروپوزال تستی."})
    with patch("core.agent_api.get_form_filler") as mock_factory:
        filler = MagicMock()
        filler.fill_application.return_value = {
            "status": "ready_for_review",
            "platform": "ponisha",
            "url": BOT_PROJECT["url"],
            "bid": 5000000,
            "delivery_days": 3,
            "submitted": False,
            "details": "Form populated in browser. Waiting for user confirmation.",
        }
        mock_factory.return_value = filler
        res = run_fill(Namespace(job_id=BOT_PROJECT["job_hash"], cdp=None, confirm=False), db=db)
        assert res["status"] == "ready_for_review"
        assert res["submitted"] is False


def test_main_dispatches_new_commands():
    with patch("interfaces.cli.run_review") as m:
        assert main(["review"]) == 0
        m.assert_called_once()
    with patch("interfaces.cli.run_pick") as m:
        assert main(["pick", "1"]) == 0
        m.assert_called_once()
    with patch("interfaces.cli.run_blueprint") as m:
        assert main(["blueprint", "1"]) == 0
        m.assert_called_once()
    with patch("interfaces.cli.run_fill") as m:
        assert main(["fill", "1"]) == 0
        m.assert_called_once()


def test_hunt_max_client_risk_filtering(tmp_path):
    risky = {
        "platform": "ponisha",
        "platform_id": "sdk_risk_1",
        "job_hash": "ponisha_sdk_risk_1",
        "title": "ساخت ربات تلگرام فروشگاهی با پایتون و aiogram",
        "url": "https://ponisha.ir/project/sdk_risk_1",
        "budget_min": 3000000,
        "budget_max": 6000000,
        "currency": "IRT",
        "description": "ربات تلگرام با پایتون؛ پشتیبانی نامحدود و تسویه بعد از تست یک ماهه.",
        "skills": ["Python", "Telegram Bot", "aiogram"],
    }
    api = _make_api(tmp_path)
    try:
        _patch_scrapers(api, {"ponisha": [BOT_PROJECT, risky]})
        default_results = api.hunt(limit=10)
        default_hashes = [p["job_hash"] for p in default_results]
        assert BOT_PROJECT["job_hash"] in default_hashes
        # 2 red flags -> high risk -> excluded by the default "medium" cap.
        assert risky["job_hash"] not in default_hashes

        inclusive = api.hunt(limit=10, max_client_risk="high")
        inclusive_hashes = [p["job_hash"] for p in inclusive]
        assert BOT_PROJECT["job_hash"] in inclusive_hashes
        assert risky["job_hash"] in inclusive_hashes

        risky_entry = next(p for p in inclusive if p["job_hash"] == risky["job_hash"])
        assert risky_entry["client_risk"] == "high"
        assert isinstance(risky_entry["red_flags"], list) and len(risky_entry["red_flags"]) >= 2
    finally:
        api.close()


def test_skill_files_exist():
    from pathlib import Path

    assert Path("SKILL.md").exists()
    assert Path(".claude/skills/omnihunter/SKILL.md").exists()
    root = Path("SKILL.md").read_text(encoding="utf-8")
    nested = Path(".claude/skills/omnihunter/SKILL.md").read_text(encoding="utf-8")
    assert root == nested
    for marker in ("Human-in-the-Loop", "Anti-Clich", "Claude Leverage",
                   "/hunt", "/blueprint", "/fill", "/review"):
        assert marker in root, marker
