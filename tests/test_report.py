from datetime import datetime
import json
from pathlib import Path

from core.report import (
    build_markdown_report,
    escape_telegram_markdown,
    format_telegram_message,
)


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
        "proposal": "سلام، پروژه با aiogram قابل انجام است.",
    }
    msg = format_telegram_message(proj)
    assert "#105" in msg
    assert "رودمپ" in msg
    assert "پیشنهاد" in msg


def test_escape_telegram_markdown():
    raw = "test_var *bold* `code` [link] back\\slash"
    escaped = escape_telegram_markdown(raw)
    assert "test\\_var" in escaped
    assert "\\*bold\\*" in escaped
    assert "\\`code\\`" in escaped
    assert "\\[link\\]" in escaped
    assert "back\\\\slash" in escaped
    assert escape_telegram_markdown(None) == ""
    assert escape_telegram_markdown(123) == "123"


def test_telegram_message_escaping():
    proj = {
        "id": "bot_99",
        "title": "ربات_اسکریپت *پایتون*",
        "platform": "parscoders",
        "scope": "scripting",
        "budget_min": 1000000,
        "budget_max": 1000000,
        "currency": "IRT",
        "tier": "A",
        "roadmap": ["گام ۱: تست_واحد", "گام ۲: دیپلوی"],
        "tech_stack": ["python_telegram_bot", "requests"],
        "proposal": "پیشنهاد با متغیر `my_config` و [لینک].",
    }
    msg = format_telegram_message(proj)
    assert "#bot_99" in msg
    assert "ربات\\_اسکریپت" in msg
    assert "\\*پایتون\\*" in msg
    assert "python\\_telegram\\_bot" in msg
    assert "تست\\_واحد" in msg
    assert "\\`my\\_config\\`" in msg
    assert "\\[لینک\\]" in msg


def test_telegram_message_with_and_without_url():
    with_url = {
        "id": 201,
        "title": "پروژه با لینک",
        "url": "https://ponisha.ir/project/201?ref=test(1)",
        "tier": "A",
        "scope": "bots",
    }
    msg_url = format_telegram_message(with_url)
    assert "[پروژه با لینک](https://ponisha.ir/project/201?ref=test%281%29)" in msg_url

    bracket_title = {
        "id": 203,
        "title": "[فوری] ربات تلگرام",
        "url": "https://ponisha.ir/project/203",
        "tier": "A",
        "scope": "bots",
    }
    msg_bracket = format_telegram_message(bracket_title)
    assert "[\\[فوری\\] ربات تلگرام](https://ponisha.ir/project/203)" in msg_bracket

    no_url = {
        "id": 202,
        "title": "پروژه بدون لینک",
        "tier": "B",
        "scope": "excel",
    }
    msg_no_url = format_telegram_message(no_url)
    assert "پروژه بدون لینک" in msg_no_url
    assert "http" not in msg_no_url


def test_telegram_message_with_json_serialized_fields():
    # Simulates records loaded directly from SQLite text columns
    proj = {
        "id": 301,
        "title": "پروژه دیتابیس",
        "tier": "A",
        "scope": "scraping",
        "roadmap": json.dumps(["فاز ۱: تحلیل وبسایت", "فاز ۲: استخراج"]),
        "tech_stack": json.dumps(["Playwright", "BeautifulSoup"]),
        "suggested_bid": 2500000,
        "delivery_days": 2,
    }
    msg = format_telegram_message(proj)
    assert "#301" in msg
    assert "Playwright" in msg
    assert "BeautifulSoup" in msg
    assert "فاز ۱: تحلیل وبسایت" in msg
    assert "۲,۵۰۰,۰۰۰" in msg or "2,500,000" in msg
    assert "۲ روز کاری" in msg or "2 روز کاری" in msg


def test_telegram_message_truncation_for_large_payload():
    huge_proposal = "توضیح بسیار طولانی پروژه " * 300  # ~7500 chars
    proj = {
        "id": 401,
        "title": "پروژه طولانی",
        "proposal": huge_proposal,
    }
    msg = format_telegram_message(proj)
    assert len(msg) <= 4096
    assert "کوتاه‌شده به دلیل محدودیت" in msg


def test_telegram_message_malformed_and_empty_inputs():
    assert format_telegram_message({}) != ""
    assert "#N/A" in format_telegram_message({})
    assert format_telegram_message(None) != ""  # type: ignore


def test_telegram_tracking_id_fallbacks():
    p1 = {"platform_id": "P555", "title": "Test"}
    assert "#P555" in format_telegram_message(p1)

    p2 = {"job_hash": "abcdef123456", "title": "Test"}
    assert "#abcdef12" in format_telegram_message(p2)

    p3 = {"id": "#already_prefixed", "title": "Test"}
    assert "#already_prefixed" in format_telegram_message(p3)


def test_build_markdown_report_comprehensive(tmp_path):
    projects = [
        {
            "id": 101,
            "title": "ربات تلگرام خرید و فروش",
            "url": "https://ponisha.ir/project/101",
            "platform": "ponisha",
            "scope": "bots",
            "tier": "A",
            "fit_score": 0.92,
            "budget_min": 3000000,
            "budget_max": 5000000,
            "currency": "IRT",
            "suggested_bid": 4300000,
            "delivery_days": 4,
            "description": "نیاز به ربات پیشرفته متصل به درگاه پرداخت",
            "tech_stack": ["Python 3.12", "aiogram 3.x"],
            "roadmap": ["طراحی پایگاه داده", "پیاده‌سازی FSM", "تست سناریو"],
            "proposal": "پروژه با بالاترین استانداردها قابل اجراست.",
        },
        {
            "id": 102,
            "title": "اسکریپت تمیزکاری اکسل | فرمول نویسی",
            "url": "https://parscoders.com/project/102",
            "platform": "parscoders",
            "scope": "excel",
            "tier": "B",
            "fit_score": 0.65,
            "budget_min": 800000,
            "budget_max": 1200000,
            "currency": "IRT",
            "suggested_bid": 950000,
            "delivery_days": 2,
        },
        {
            "id": 103,
            "title": "تایپ فایل صوتی با پرداخت بیعانه",
            "platform": "ponisha",
            "scope": "translation",
            "tier": "C",
            "rejection_reason": "ریسک اسکم: درخواست بیعانه اولیه",
        },
    ]

    out_file = tmp_path / "custom_report.md"
    content = build_markdown_report(projects, output_path=str(out_file))

    # Check return string and file creation
    assert out_file.exists()
    assert out_file.read_text(encoding="utf-8") == content

    # Check Summary Metrics
    assert "مجموع کل پروژه‌های اسکن‌شده | **3**" in content
    assert "رده A (ارزش بالا / اقدام فوری) | **1**" in content
    assert "رده B (ارزش متوسط) | **1**" in content
    assert "رده C (رد شده / کم‌ارزش / اسکم) | **1**" in content
    assert "`bots`" in content
    assert "`excel`" in content
    assert "ponisha" in content
    assert "parscoders" in content

    # Check Tier A card
    assert "#101 - [ربات تلگرام خرید و فروش](https://ponisha.ir/project/101)" in content
    assert "Python 3.12" in content
    assert "طراحی پایگاه داده" in content
    assert "پروژه با بالاترین استانداردها قابل اجراست." in content

    # Check Tier B table
    assert "اسکریپت تمیزکاری اکسل - فرمول نویسی" in content
    assert "parscoders" in content
    assert "0.65" in content

    # Check Tier C rejection table
    assert "ریسک اسکم: درخواست بیعانه اولیه" in content


def test_build_markdown_report_default_path():
    today = datetime.now().strftime("%Y-%m-%d")
    expected_path = Path(f"reports/{today}.md")

    sample = [
        {
            "id": 501,
            "title": "پروژه تست مسیر پیش‌فرض",
            "tier": "A",
            "scope": "scripting",
        }
    ]

    try:
        content = build_markdown_report(sample)
        assert expected_path.exists()
        assert "#501" in content
        assert "scripting" in content
    finally:
        if expected_path.exists():
            expected_path.unlink()


def test_build_markdown_report_empty_list(tmp_path):
    out_file = tmp_path / "empty_report.md"
    content = build_markdown_report([], output_path=str(out_file))
    assert out_file.exists()
    assert "مجموع کل پروژه‌های اسکن‌شده | **0**" in content
    assert "هیچ پروژه‌ای با رتبه Tier A" in content
    assert "هیچ پروژه‌ای در رده Tier B" in content
    assert "هیچ پروژه رد شده‌ای" in content


def test_budget_formatting_permutations(tmp_path):
    projects = [
        {
            "id": 601,
            "title": "بودجه دلاری",
            "tier": "B",
            "budget_min": 50,
            "budget_max": 100,
            "currency": "USD",
            "suggested_bid": 75,
            "delivery_days": 3,
        },
        {
            "id": 602,
            "title": "بودجه تک مقداری",
            "tier": "B",
            "budget_min": 2000000,
            "budget_max": 2000000,
            "currency": "IRT",
        },
        {
            "id": 603,
            "title": "بودجه توافقی",
            "tier": "B",
            "budget_min": None,
            "budget_max": None,
        },
    ]
    out_file = tmp_path / "budget_test.md"
    content = build_markdown_report(projects, output_path=str(out_file))
    assert "50 USD تا 100 USD" in content or "50 تا 100 USD" in content
    assert "2,000,000 IRT" in content
    assert "توافقی" in content
