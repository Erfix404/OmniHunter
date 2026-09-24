import os
from unittest.mock import patch

import pytest
from core.architect import BANNED_CLICHES, generate_architecture


def test_architect_bot_project():
    proj = {
        "title": "ربات تلگرام ثبت سفارش",
        "description": "ربات پایتون برای دریافت اطلاعات سفارش و ذخیره در دیتابیس",
        "scope": "bots",
        "budget_min": 2000000,
        "budget_max": 3000000,
        "currency": "IRT",
    }
    arch = generate_architecture(proj)
    assert len(arch["roadmap"]) >= 3
    assert "aiogram" in " ".join(arch["tech_stack"]).lower() or "python" in " ".join(arch["tech_stack"]).lower()
    assert arch["suggested_bid"] >= 2000000
    assert len(arch["proposal"]) > 50
    # New fields
    assert "technical_hook" in arch
    assert isinstance(arch["technical_hook"], str)
    assert len(arch["technical_hook"]) > 10
    assert "prerequisites" in arch
    assert isinstance(arch["prerequisites"], list)
    assert len(arch["prerequisites"]) >= 1
    assert "clarifying_question" in arch
    assert isinstance(arch["clarifying_question"], str)
    assert len(arch["clarifying_question"]) > 10


def test_architect_bale_bot():
    proj = {
        "title": "ربات پیام‌رسان بله برای فروشگاه",
        "description": "نیاز به ربات بله برای اتصال به درگاه پرداخت",
        "scope": "bots",
        "budget_min": 2500000,
        "currency": "IRT",
    }
    arch = generate_architecture(proj)
    tech_str = " ".join(arch["tech_stack"]).lower()
    assert "bale" in tech_str
    assert "بله" in arch["proposal"] or "bale" in arch["proposal"].lower()


@pytest.mark.parametrize(
    "scope,expected_tech,expected_min_bid",
    [
        ("bots", ["python", "sqlite"], 1800000),
        ("automation", ["n8n", "webhook"], 1800000),
        ("translation", ["translation", "glossary"], 600000),
        ("excel", ["openpyxl", "pandas"], 600000),
        ("scraping", ["playwright", "beautifulsoup4"], 1800000),
        ("scripting", ["fastapi", "sqlite"], 1800000),
    ],
)
def test_architect_all_six_scopes(scope, expected_tech, expected_min_bid):
    proj = {
        "title": f"پروژه تستی برای {scope}",
        "description": "توضیحات فنی نیازمندی‌ها",
        "scope": scope,
        "currency": "IRT",
    }
    arch = generate_architecture(proj)
    assert 3 <= len(arch["roadmap"]) <= 4
    assert 1 <= arch["delivery_days"] <= 5
    assert arch["suggested_bid"] >= expected_min_bid
    assert len(arch["proposal"]) > 100

    tech_joined = " ".join(arch["tech_stack"]).lower()
    for tech in expected_tech:
        assert tech in tech_joined


def test_architect_pricing_sweet_spot():
    proj = {
        "title": "اتوماسیون وب‌هوک",
        "scope": "automation",
        "budget_min": 2000000,
        "budget_max": 3000000,
        "currency": "IRT",
    }
    arch = generate_architecture(proj)
    # 2,000,000 + 0.65 * 1,000,000 = 2,650,000
    assert arch["suggested_bid"] == 2650000


def test_architect_pricing_only_min():
    proj = {
        "title": "اسکریپت پایتون",
        "scope": "scripting",
        "budget_min": 2000000,
        "budget_max": None,
        "currency": "IRT",
    }
    arch = generate_architecture(proj)
    # 2,000,000 * 1.15 = 2,300,000
    assert arch["suggested_bid"] == 2300000


def test_architect_pricing_only_max():
    proj = {
        "title": "اسکراپر سایت فروشگاهی",
        "scope": "scraping",
        "budget_min": None,
        "budget_max": 3000000,
        "currency": "IRT",
    }
    arch = generate_architecture(proj)
    # 3,000,000 * 0.80 = 2,400,000
    assert arch["suggested_bid"] == 2400000


def test_architect_pricing_negotiable_irt():
    proj_bot = {"title": "ربات تلگرام", "scope": "bots", "currency": "IRT"}
    arch_bot = generate_architecture(proj_bot)
    assert arch_bot["suggested_bid"] == 1800000

    proj_trans = {"title": "ترجمه مقاله", "scope": "translation", "currency": "IRT"}
    arch_trans = generate_architecture(proj_trans)
    assert arch_trans["suggested_bid"] == 600000


def test_architect_pricing_negotiable_usd():
    proj_bot = {"title": "Telegram Bot", "scope": "bots", "currency": "USD"}
    arch_bot = generate_architecture(proj_bot)
    assert arch_bot["suggested_bid"] == 25

    proj_trans = {"title": "Article Translation", "scope": "translation", "currency": "USD"}
    arch_trans = generate_architecture(proj_trans)
    assert arch_trans["suggested_bid"] == 15


def test_architect_pricing_negotiable_irr():
    proj_bot = {"title": "ربات تلگرام", "scope": "bots", "currency": "IRR"}
    arch_bot = generate_architecture(proj_bot)
    assert arch_bot["suggested_bid"] == 18000000


def test_architect_excel_vba_detection():
    proj = {
        "title": "ماکرو و فرمول نویسی اکسل",
        "description": "فایل اکسل با کد vba برای خودکارسازی انبارداری",
        "scope": "excel",
        "currency": "IRT",
    }
    arch = generate_architecture(proj)
    tech_joined = " ".join(arch["tech_stack"]).lower()
    assert "vba" in tech_joined


def test_architect_proposal_no_banned_cliches():
    for scope in ["bots", "automation", "translation", "excel", "scraping", "scripting"]:
        proj = {
            "title": f"پروژه نمونه {scope}",
            "description": "توضیحات سناریوی پروژه",
            "scope": scope,
            "currency": "IRT",
        }
        arch = generate_architecture(proj)
        proposal_lower = arch["proposal"].lower()
        for cliche in BANNED_CLICHES:
            assert cliche.lower() not in proposal_lower


def test_architect_delivery_days_scaling():
    # Standard budget -> baseline
    proj_small = {"title": "خزنده وب", "scope": "scraping", "budget_min": 2000000, "currency": "IRT"}
    arch_small = generate_architecture(proj_small)
    assert arch_small["delivery_days"] == 2

    # High budget -> baseline + 1
    proj_large = {"title": "خزنده وب بزرگ", "scope": "scraping", "budget_min": 6000000, "currency": "IRT"}
    arch_large = generate_architecture(proj_large)
    assert arch_large["delivery_days"] == 3


def test_architect_auto_scope_fallback():
    # No scope provided, but title indicates scraping
    proj = {
        "title": "استخراج داده از سایت دیجی کالا با پایتون",
        "description": "نیاز به خزش و اسکرپ قیمت‌ها",
        "budget_min": 2000000,
        "currency": "IRT",
    }
    arch = generate_architecture(proj)
    assert "playwright" in " ".join(arch["tech_stack"]).lower() or "beautifulsoup4" in " ".join(arch["tech_stack"]).lower()


def test_architect_empty_and_malformed_input():
    arch_empty = generate_architecture({})
    assert arch_empty["suggested_bid"] > 0
    assert len(arch_empty["roadmap"]) >= 3
    assert len(arch_empty["tech_stack"]) > 0
    assert len(arch_empty["proposal"]) > 50

    arch_none = generate_architecture(None)
    assert arch_none["suggested_bid"] > 0


def test_architect_optional_llm_fallback(monkeypatch):
    # Set dummy keys and simulate urllib failure to verify graceful fallback
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-key")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-proj-test-key")

    with patch("urllib.request.urlopen", side_effect=Exception("Network error")):
        proj = {
            "title": "ربات ثبت سفارش",
            "scope": "bots",
            "budget_min": 2000000,
            "currency": "IRT",
        }
        arch = generate_architecture(proj)
        assert len(arch["proposal"]) > 50
        assert "aiogram" in arch["proposal"] or "پایتون" in arch["proposal"]


def test_architect_fixed_budget_and_invalid_strings():
    # b_min == b_max
    proj_fixed = {
        "title": "پروژه با قیمت ثابت",
        "scope": "scripting",
        "budget_min": 2000000,
        "budget_max": 2000000,
        "currency": "IRT",
    }
    arch_fixed = generate_architecture(proj_fixed)
    assert arch_fixed["suggested_bid"] == 2000000

    # invalid string budget
    proj_invalid = {
        "title": "پروژه با بودجه نامعتبر",
        "scope": "scripting",
        "budget_min": "invalid-budget",
        "budget_max": "also-invalid",
        "currency": "IRT",
    }
    arch_invalid = generate_architecture(proj_invalid)
    assert arch_invalid["suggested_bid"] == 1800000


def test_architect_delivery_days_high_budget_usd_and_irr():
    # USD high budget
    proj_usd_high = {
        "title": "High budget bot",
        "scope": "bots",
        "budget_min": 100,
        "currency": "USD",
    }
    arch_usd = generate_architecture(proj_usd_high)
    assert arch_usd["delivery_days"] == 4  # baseline 3 + 1

    # IRR high budget
    proj_irr_high = {
        "title": "High budget IRR scraping",
        "scope": "scraping",
        "budget_min": 60000000,
        "currency": "IRR",
    }
    arch_irr = generate_architecture(proj_irr_high)
    assert arch_irr["delivery_days"] == 3  # baseline 2 + 1


def test_architect_llm_success_anthropic(monkeypatch):
    import io
    import json

    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-valid")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    fake_resp = io.BytesIO(
        json.dumps({
            "content": [{"text": "این یک پروپوزال ساختاریافته تولید شده توسط مدل زبانی با معماری دقیق و زمان‌بندی شفاف است."}]
        }).encode("utf-8")
    )

    with patch("urllib.request.urlopen", return_value=fake_resp):
        proj = {"title": "ربات تلگرام", "scope": "bots"}
        arch = generate_architecture(proj)
        assert "تولید شده توسط مدل زبانی" in arch["proposal"]


def test_architect_llm_success_openai(monkeypatch):
    import io
    import json

    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-proj-valid")

    fake_resp = io.BytesIO(
        json.dumps({
            "choices": [{"message": {"content": "پروپوزال فنی اختصاصی تولید شده توسط اوپن ای‌آی با رویکرد پایتون و معماری مدرن."}}]
        }).encode("utf-8")
    )

    with patch("urllib.request.urlopen", return_value=fake_resp):
        proj = {"title": "ربات تلگرام", "scope": "bots"}
        arch = generate_architecture(proj)
        assert "تولید شده توسط اوپن ای‌آی" in arch["proposal"]


def test_architect_llm_cliche_stripping(monkeypatch):
    import io
    import json

    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-valid")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    # First sentence has banned cliche, second sentence has clean technical proposal
    raw_llm = (
        "سلام و احترام، امیدوارم حالتون خوب باشه.\n"
        "برای پیاده‌سازی این پروژه، ساختاری ماژولار با فریم‌ورک غیرهمگام aiogram و پایتون استاندارد "
        "طراحی شده و با بالاترین کیفیت و قابلیت تست‌پذیری در زمان مقرر تحویل داده خواهد شد."
    )
    fake_resp = io.BytesIO(
        json.dumps({
            "content": [{"text": raw_llm}]
        }).encode("utf-8")
    )

    with patch("urllib.request.urlopen", return_value=fake_resp):
        proj = {"title": "ربات تلگرام", "scope": "bots"}
        arch = generate_architecture(proj)
        # Cliche should be stripped
        assert "امیدوارم حالتون خوب باشه" not in arch["proposal"]
        # Valid content retained
        assert "ساختاری ماژولار" in arch["proposal"]


def test_architect_llm_cliche_complete_fallback(monkeypatch):
    import io
    import json

    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-valid")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    # Entire LLM response is just banned cliches -> should fall back to rule-based proposal
    raw_llm = "سلام و احترام، امیدوارم حالتون خوب باشه. من یک برنامه نویس با تجربه هستم."
    fake_resp = io.BytesIO(
        json.dumps({
            "content": [{"text": raw_llm}]
        }).encode("utf-8")
    )

    with patch("urllib.request.urlopen", return_value=fake_resp):
        proj = {"title": "ربات تلگرام", "scope": "bots"}
        arch = generate_architecture(proj)
        assert "امیدوارم حالتون خوب باشه" not in arch["proposal"]
        # Fallback to rule-based template
        assert "aiogram" in arch["proposal"] or "پایتون" in arch["proposal"]


def test_architect_new_fields_all_scopes():
    """All scopes return technical_hook, prerequisites, clarifying_question."""
    for scope in ["bots", "automation", "translation", "excel", "scraping", "scripting"]:
        proj = {
            "title": f"پروژه تستی برای {scope}",
            "description": "توضیحات فنی نیازمندی‌ها",
            "scope": scope,
            "currency": "IRT",
        }
        arch = generate_architecture(proj)

        assert "technical_hook" in arch, f"Missing technical_hook for {scope}"
        assert isinstance(arch["technical_hook"], str)
        assert len(arch["technical_hook"]) > 10
        # No cliché greetings in technical_hook
        assert "سلام" not in arch["technical_hook"]
        assert "احترام" not in arch["technical_hook"]

        assert "prerequisites" in arch, f"Missing prerequisites for {scope}"
        assert isinstance(arch["prerequisites"], list)
        assert len(arch["prerequisites"]) >= 1
        assert all(isinstance(p, str) for p in arch["prerequisites"])

        assert "clarifying_question" in arch, f"Missing clarifying_question for {scope}"
        assert isinstance(arch["clarifying_question"], str)
        assert len(arch["clarifying_question"]) > 10


def test_architect_empty_input_has_new_fields():
    """Even empty/None input returns the new fields."""
    arch_empty = generate_architecture({})
    assert "technical_hook" in arch_empty
    assert "prerequisites" in arch_empty
    assert "clarifying_question" in arch_empty

    arch_none = generate_architecture(None)
    assert "technical_hook" in arch_none
    assert "prerequisites" in arch_none
    assert "clarifying_question" in arch_none


