import pytest
from core.triage import evaluate_project


def test_scam_detection():
    proj = {
        "title": "تایپ فایل",
        "description": "پرداخت اول 50 هزار تومان به عنوان بیعانه",
        "budget_min": 100000,
    }
    res = evaluate_project(proj, {})
    assert res["is_scam"] is True
    assert res["tier"] == "C"
    assert res["rejection_reason"] == "scam_detected"
    assert res["scope"] is None
    assert res["fit_score"] == 0.0


def test_scam_detection_variations():
    # English scam phrasing
    proj_en = {
        "title": "Data Entry Job",
        "description": "100% upfront registration fee required before start",
        "budget_min": 50,
        "currency": "USD",
    }
    res = evaluate_project(proj_en, {})
    assert res["is_scam"] is True
    assert res["tier"] == "C"
    assert res["rejection_reason"] == "scam_detected"

    # Upfront payment scam phrase
    proj_upfront = {
        "title": "Python Scripting",
        "description": "Upfront payment needed to secure slot",
        "budget_min": 100,
        "currency": "USD",
    }
    res = evaluate_project(proj_upfront, {})
    assert res["is_scam"] is True
    assert res["rejection_reason"] == "scam_detected"

    # Persian "تست رایگان" scam phrase
    proj_free = {
        "title": "پروژه ترجمه",
        "description": "ابتدا تست رایگان ارسال نمایید",
        "budget_min": 1000000,
    }
    res = evaluate_project(proj_free, {})
    assert res["is_scam"] is True
    assert res["rejection_reason"] == "scam_detected"


def test_scope_bots_tier_a():
    proj = {
        "title": "ساخت ربات تلگرام ووکامرس",
        "description": "پایتون و تلگرام برای فروشگاه",
        "budget_min": 2500000,
        "currency": "IRT",
    }
    res = evaluate_project(proj, {})
    assert res["is_scam"] is False
    assert res["scope"] == "bots"
    assert res["tier"] == "A"
    assert res["fit_score"] >= 0.75
    assert res["rejection_reason"] is None
    assert res["estimated_hours"] == 6.0
    assert res["roi_score"] is not None
    assert res["roi_score"] > 0


def test_all_active_scopes_tier_a():
    cases = [
        (
            "automation",
            {
                "title": "اتوماسیون فرایند با n8n و وب هوک",
                "description": "اتصال وب هوک ووکامرس با اتوماسیون n8n",
                "budget_min": 3000000,
                "currency": "IRT",
            },
            5.0,
        ),
        (
            "translation",
            {
                "title": "ترجمه مقاله تخصصی هوش مصنوعی",
                "description": "ترجمه متون دانشگاهی و مقاله ISI انگلیسی به فارسی",
                "budget_min": 800000,
                "currency": "IRT",
            },
            3.0,
        ),
        (
            "excel",
            {
                "title": "فرمول نویسی و تمیزکاری اکسل",
                "description": "فایل اکسل نیازمند ماکرو نویسی و فرمول نویسی پیشرفته vba",
                "budget_min": 700000,
                "currency": "IRT",
            },
            2.5,
        ),
        (
            "scraping",
            {
                "title": "استخراج داده و اسکرپ سایت دیجی‌کالا",
                "description": "خزنده و وب اسکرپینگ محصولات با playwright یا selenium",
                "budget_min": 2000000,
                "currency": "IRT",
            },
            4.0,
        ),
        (
            "scripting",
            {
                "title": "نوشتن اسکریپت پایتون و ساخت api با fastapi",
                "description": "توسعه اسکریپت پایتون با requests و fastapi و دیتابیس sqlite",
                "budget_min": 2500000,
                "currency": "IRT",
            },
            4.0,
        ),
    ]

    for expected_scope, proj, expected_hours in cases:
        res = evaluate_project(proj, {})
        assert res["is_scam"] is False, f"Failed on {expected_scope}: marked as scam"
        assert res["scope"] == expected_scope, f"Expected scope {expected_scope}, got {res['scope']}"
        assert res["tier"] == "A", f"Expected Tier A for {expected_scope}, got {res['tier']}"
        assert res["fit_score"] >= 0.75, f"Fit score too low for {expected_scope}: {res['fit_score']}"
        assert res["rejection_reason"] is None
        assert res["estimated_hours"] == expected_hours
        assert res["roi_score"] is not None


def test_disabled_scope_formatting():
    # Document formatting is explicitly disabled in the system specification
    proj = {
        "title": "صفحه آرایی و فرمت بندی پایان نامه",
        "description": "فرمت بندی فایل ورد و تنظیم فونت و ساختار ورد",
        "budget_min": 1000000,
        "currency": "IRT",
    }
    res = evaluate_project(proj, {})
    assert res["is_scam"] is False
    assert res["tier"] == "C"
    assert res["rejection_reason"] == "no_scope_match"
    assert res["scope"] is None


def test_budget_below_minimum_floor_irt():
    # Translation floor is 500,000 IRT
    proj_trans = {
        "title": "ترجمه مقاله تخصصی",
        "description": "ترجمه مقاله انگلیسی",
        "budget_min": 200000,  # Below 500k
        "currency": "IRT",
    }
    res = evaluate_project(proj_trans, {})
    assert res["scope"] == "translation"
    assert res["tier"] == "C"
    assert res["rejection_reason"] == "budget_below_minimum"

    # Bots floor is 1,500,000 IRT
    proj_bot = {
        "title": "طراحی ربات تلگرام حرفه‌ای",
        "description": "ربات اختصاصی تلگرام با aiogram",
        "budget_max": 800000,  # Below 1.5M
        "currency": "IRT",
    }
    res = evaluate_project(proj_bot, {})
    assert res["scope"] == "bots"
    assert res["tier"] == "C"
    assert res["rejection_reason"] == "budget_below_minimum"


def test_budget_below_minimum_floor_usd():
    # Scraping floor is $20 USD
    proj_usd = {
        "title": "Python Web Scraping Crawler",
        "description": "Scraping script using playwright to crawl products",
        "budget_min": 10,  # Below $20 USD
        "currency": "USD",
    }
    res = evaluate_project(proj_usd, {})
    assert res["scope"] == "scraping"
    assert res["tier"] == "C"
    assert res["rejection_reason"] == "budget_below_minimum"


def test_no_scope_match():
    # Irrelevant project
    proj = {
        "title": "طراحی کاتالوگ در فتوشاپ",
        "description": "نیازمند طراح گرافیک مسلط به ایلوستریتور و ایندیزاین",
        "budget_min": 3000000,
        "currency": "IRT",
    }
    res = evaluate_project(proj, {})
    assert res["is_scam"] is False
    assert res["scope"] is None
    assert res["fit_score"] < 0.3
    assert res["tier"] == "C"
    assert res["rejection_reason"] == "no_scope_match"


def test_low_fit_score_under_0_3():
    # Accidental single keyword in description only
    proj = {
        "title": "همکاری در فروش و بازاریابی تلفنی",
        "description": "یک شرکت نیازمند بازاریاب، آشنایی مختصری با پایتون مزیت است",
        "budget_min": 5000000,
        "currency": "IRT",
    }
    res = evaluate_project(proj, {})
    assert res["fit_score"] < 0.3
    assert res["tier"] == "C"
    assert res["rejection_reason"] == "no_scope_match"


def test_tier_b_moderate_fit():
    # Moderate fit (between 0.45 and 0.75) with valid budget
    proj = {
        "title": "پروژه کوچک اکسل",
        "description": "انجام محاسبات ساده در اکسل",
        "budget_min": 600000,
        "currency": "IRT",
    }
    res = evaluate_project(proj, {})
    assert res["scope"] == "excel"
    assert 0.45 <= res["fit_score"] < 0.75
    assert res["tier"] == "B"
    assert res["rejection_reason"] is None


def test_negotiable_budget_handling():
    # Project with no budget specified (negotiable)
    proj = {
        "title": "ساخت ربات تلگرام فروشگاهی",
        "description": "ربات تلگرام با پایتون و aiogram جهت ثبت سفارش مشتریان",
        "budget_min": None,
        "budget_max": None,
        "currency": "IRT",
    }
    res = evaluate_project(proj, {})
    assert res["scope"] == "bots"
    assert res["fit_score"] >= 0.75
    assert res["tier"] == "A"
    assert res["rejection_reason"] is None
    assert res["estimated_hours"] == 6.0
    assert res["roi_score"] is None


def test_custom_config_override():
    # Override scam blacklist and custom budget
    custom_config = {
        "scam_filter": {
            "blacklist": ["کلاهبرداری جدید"],
        },
        "scopes": {
            "bots": {
                "name": "Custom Bots",
                "enabled": True,
                "min_budget_irt": 4000000,  # Stricter floor
                "min_budget_usd": 50,
                "keywords": ["ربات تلگرام"],
            }
        },
    }
    # Test custom blacklist
    proj_scam = {"title": "پروژه خاص", "description": "این یک کلاهبرداری جدید است"}
    res_scam = evaluate_project(proj_scam, custom_config)
    assert res_scam["is_scam"] is True
    assert res_scam["rejection_reason"] == "scam_detected"

    # Test custom budget floor: 3,000,000 is below 4,000,000
    proj_bot = {
        "title": "ربات تلگرام اختصاصی",
        "description": "ربات تلگرام برای ثبت سفارش",
        "budget_min": 3000000,
        "currency": "IRT",
    }
    res_bot = evaluate_project(proj_bot, custom_config)
    assert res_bot["tier"] == "C"
    assert res_bot["rejection_reason"] == "budget_below_minimum"


def test_scam_precedence_over_budget_and_scope():
    # Both scam phrase and low budget: scam must take precedence
    proj = {
        "title": "ربات تلگرام ارزان",
        "description": "ربات تلگرام پرداخت اول بیعانه",
        "budget_min": 10000,
    }
    res = evaluate_project(proj, {})
    assert res["is_scam"] is True
    assert res["rejection_reason"] == "scam_detected"
    assert res["tier"] == "C"


def test_malformed_and_empty_project():
    # Non-dict input
    res_non_dict = evaluate_project("not a dict", {})
    assert res_non_dict["tier"] == "C"
    assert res_non_dict["rejection_reason"] == "no_scope_match"

    # Empty project dict
    res_empty = evaluate_project({}, {})
    assert res_empty["is_scam"] is False
    assert res_empty["tier"] == "C"
    assert res_empty["rejection_reason"] == "no_scope_match"

    # None fields and invalid budget string
    res_none = evaluate_project(
        {"title": None, "description": None, "budget_min": "invalid"}, {}
    )
    assert res_none["tier"] == "C"
    assert res_none["rejection_reason"] == "no_scope_match"


def test_skills_matching_and_budget_max_only():
    proj = {
        "title": "یک پروژه برنامه نویسی",
        "description": "نیاز به انجام کار",
        "skills": ["Telegram Bot", "aiogram"],
        "budget_max": 2000000,
        "currency": "IRT",
    }
    res = evaluate_project(proj, {})
    assert res["scope"] == "bots"
    assert res["tier"] in ("A", "B")
    assert res["fit_score"] >= 0.45


def test_rial_currency_conversion():
    # 15,000,000 IRR = 1,500,000 IRT (floor for bots)
    proj_pass = {
        "title": "ربات تلگرام فروشگاهی با پایتون",
        "description": "ربات تلگرام هوشمند",
        "budget_min": 16000000,  # 1.6M Toman in Rial
        "currency": "IRR",
    }
    res_pass = evaluate_project(proj_pass, {})
    assert res_pass["tier"] == "A"
    assert res_pass["rejection_reason"] is None

    # 10,000,000 IRR = 1,000,000 IRT (< 1.5M floor)
    proj_fail = {
        "title": "ربات تلگرام فروشگاهی با پایتون",
        "description": "ربات تلگرام هوشمند",
        "budget_min": 10000000,
        "currency": "IRR",
    }
    res_fail = evaluate_project(proj_fail, {})
    assert res_fail["tier"] == "C"
    assert res_fail["rejection_reason"] == "budget_below_minimum"


def test_low_fit_score_tier_c():
    # Fit score between 0.30 and 0.45: single keyword in title only
    proj = {
        "title": "پروژه اکسل",
        "description": "توضیحات کلی بدون جزییات یا مهارت خاص",
        "budget_min": 1000000,
        "currency": "IRT",
    }
    res = evaluate_project(proj, {})
    assert res["scope"] == "excel"
    assert 0.30 <= res["fit_score"] < 0.45
    assert res["tier"] == "C"
    assert res["rejection_reason"] == "low_fit"

