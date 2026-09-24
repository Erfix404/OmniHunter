import os

import pytest
import yaml

from core.architect import BANNED_CLICHES, generate_architecture
from core.profile import DEFAULT_PROFILE_DATA, FreelancerProfile
from core.triage import evaluate_project


def _bots_project(**overrides):
    proj = {
        "title": "ساخت ربات تلگرام فروشگاهی",
        "description": "ربات تلگرام با پایتون و aiogram جهت ثبت سفارش مشتریان",
        "budget_min": 3000000,
        "currency": "IRT",
    }
    proj.update(overrides)
    return proj


def _translation_project(**overrides):
    proj = {
        "title": "ترجمه مقاله تخصصی هوش مصنوعی",
        "description": "ترجمه متون دانشگاهی و مقاله ISI انگلیسی به فارسی",
        "budget_min": 800000,
        "currency": "IRT",
    }
    proj.update(overrides)
    return proj


def test_default_profile_when_file_absent(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    profile = FreelancerProfile()
    assert profile.identity["name"]
    assert profile.identity["hourly_rate_irt"] > 0
    assert isinstance(profile.skills, list) and len(profile.skills) >= 1
    assert isinstance(profile.portfolio, list) and len(profile.portfolio) >= 1
    assert isinstance(profile.tone.get("avoid"), list)
    assert isinstance(profile.scopes.get("declined"), list)


def test_default_profile_when_file_invalid(tmp_path, monkeypatch):
    bad = tmp_path / "freelancer_profile.yaml"
    bad.write_text("just a plain string, not a dict", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    profile = FreelancerProfile()
    assert profile.identity == FreelancerProfile(data={}).identity or profile.identity["name"]


def test_load_custom_profile_from_file(tmp_path):
    custom = {
        "identity": {
            "name": "Test Freelancer",
            "hourly_rate_irt": 500000,
            "hourly_rate_usd": 10,
            "min_project_irt": 1000000,
            "min_project_usd": 15,
        },
        "skills": [
            {
                "name": "Test Bots",
                "level": "expert",
                "tools": ["aiogram"],
                "evidence": "Custom bot evidence for test scope",
                "scopes": ["bots"],
            }
        ],
        "portfolio": [
            {
                "title": "Custom Bot",
                "scope": "bots",
                "result": "Custom result shipped for test client",
                "url": "https://example.com/custom",
            }
        ],
        "tone": {"style": "direct", "avoid": ["custom banned phrase"]},
        "scopes": {"preferred": ["bots"], "willing": [], "declined": ["excel"]},
    }
    path = tmp_path / "custom.yaml"
    path.write_text(yaml.safe_dump(custom, allow_unicode=True), encoding="utf-8")
    profile = FreelancerProfile(path=str(path))
    assert profile.identity["name"] == "Test Freelancer"
    assert profile.get_min_budget("IRT") == 1000000
    assert profile.is_scope_declined("excel") is True
    assert profile.is_scope_declined("bots") is False
    assert profile.get_relevant_portfolio("bots")[0]["title"] == "Custom Bot"
    assert profile.get_relevant_evidence("bots") == ["Custom bot evidence for test scope"]
    assert "custom banned phrase" in profile.tone["avoid"]


def test_get_relevant_portfolio_and_evidence():
    profile = FreelancerProfile(data=DEFAULT_PROFILE_DATA)
    bots_items = profile.get_relevant_portfolio("bots")
    assert len(bots_items) >= 1
    assert all(str(i.get("scope", "")).lower() == "bots" for i in bots_items)
    assert any("Cafe Mehras" in str(i.get("title", "")) for i in bots_items)

    evidence = profile.get_relevant_evidence("bots")
    assert len(evidence) >= 1
    assert any("Cafe Mehras" in e or "aiogram" in e for e in evidence)

    # Unknown scope yields empty lists, never crashes
    assert profile.get_relevant_portfolio("nope") == []
    assert profile.get_relevant_evidence("") == []


def test_is_scope_declined_and_triage_rejection():
    profile = FreelancerProfile()
    assert profile.is_scope_declined("translation") is True
    assert profile.is_scope_declined("formatting") is True
    assert profile.is_scope_declined("bots") is False

    res = evaluate_project(_translation_project(), {}, profile=profile)
    assert res["tier"] == "C"
    assert res["is_scam"] is False
    assert res["rejection_reason"] == "scope_declined_by_profile"
    assert res["scope"] == "translation"

    # Without a profile the same project is accepted
    res_no_profile = evaluate_project(_translation_project(), {})
    assert res_no_profile["tier"] == "A"

    # Non-declined scope passes through with a profile
    res_bots = evaluate_project(_bots_project(), {}, profile=profile)
    assert res_bots["tier"] == "A"
    assert res_bots["rejection_reason"] is None


def test_triage_profile_min_budget_floor():
    profile = FreelancerProfile(
        data={
            **DEFAULT_PROFILE_DATA,
            "identity": {**DEFAULT_PROFILE_DATA["identity"], "min_project_irt": 9000000},
        }
    )
    # Above scope floor (1.5M) but below profile floor (9M) -> rejected
    res = evaluate_project(_bots_project(budget_min=3000000), {}, profile=profile)
    assert res["tier"] == "C"
    assert res["rejection_reason"] == "budget_below_minimum"

    # Above both floors -> accepted
    res_ok = evaluate_project(_bots_project(budget_min=10000000), {}, profile=profile)
    assert res_ok["tier"] == "A"

    # Lower profile floor than scope floor must not weaken the scope floor
    weak = FreelancerProfile(
        data={
            **DEFAULT_PROFILE_DATA,
            "identity": {**DEFAULT_PROFILE_DATA["identity"], "min_project_irt": 100},
        }
    )
    res_weak = evaluate_project(_bots_project(budget_min=800000), {}, profile=weak)
    assert res_weak["tier"] == "C"
    assert res_weak["rejection_reason"] == "budget_below_minimum"

    # USD profile floor applies to USD projects
    usd_prof = FreelancerProfile(
        data={
            **DEFAULT_PROFILE_DATA,
            "identity": {**DEFAULT_PROFILE_DATA["identity"], "min_project_usd": 200},
        }
    )
    res_usd = evaluate_project(
        {
            "title": "Python Web Scraping Crawler",
            "description": "Scraping script using playwright to crawl products",
            "budget_min": 50,
            "currency": "USD",
        },
        {},
        profile=usd_prof,
    )
    assert res_usd["tier"] == "C"
    assert res_usd["rejection_reason"] == "budget_below_minimum"


def test_get_min_budget_currencies():
    profile = FreelancerProfile()
    assert profile.get_min_budget("IRT") == float(DEFAULT_PROFILE_DATA["identity"]["min_project_irt"])
    assert profile.get_min_budget("USD") == float(DEFAULT_PROFILE_DATA["identity"]["min_project_usd"])
    assert profile.get_min_budget("IRR") == float(DEFAULT_PROFILE_DATA["identity"]["min_project_irt"]) * 10


def test_proposal_includes_portfolio_and_evidence_and_respects_tone():
    profile = FreelancerProfile()
    proj = _bots_project(scope="bots", budget_min=3000000, budget_max=6000000)
    arch = generate_architecture(proj, profile=profile)
    assert len(arch["proposal"]) > 100
    # Real portfolio/evidence injected
    assert "Cafe Mehras" in arch["proposal"] or "aiogram" in arch["proposal"]
    # Tone avoidances respected in proposal and technical_hook
    for phrase in ["سلام و احترام", "امیدوارم حالتون خوب باشه"]:
        assert phrase not in arch["proposal"]
        assert phrase not in arch["technical_hook"]
    for cliche in BANNED_CLICHES:
        assert cliche.lower() not in arch["proposal"].lower()


def test_proposal_bid_aligned_with_hourly_rate():
    profile = FreelancerProfile(
        data={
            **DEFAULT_PROFILE_DATA,
            "identity": {**DEFAULT_PROFILE_DATA["identity"], "hourly_rate_irt": 2000000},
        }
    )
    # bots estimated hours = 6 -> 12M rate-based bid, above the plain floor
    arch = generate_architecture(_bots_project(scope="bots"), profile=profile)
    assert arch["suggested_bid"] >= 12000000

    # Without profile the same project uses plain pricing (3M * 1.15 = 3.45M)
    arch_plain = generate_architecture(_bots_project(scope="bots"))
    assert arch_plain["suggested_bid"] == 3450000

    # And a no-budget project without profile stays at the scope floor
    arch_floor = generate_architecture({"title": "ربات تلگرام", "scope": "bots", "currency": "IRT"})
    assert arch_floor["suggested_bid"] == 1800000


def test_profile_param_backward_compatible():
    proj = _bots_project(scope="bots", budget_min=3000000, budget_max=6000000)
    arch = generate_architecture(proj)
    assert arch["suggested_bid"] > 0
    res = evaluate_project(_bots_project(), {})
    assert res["tier"] == "A"

    # Dict profiles are coerced instead of crashing
    res_dict = evaluate_project(_translation_project(), {}, profile={"scopes": {"declined": ["translation"]}})
    assert res_dict["rejection_reason"] == "scope_declined_by_profile"
