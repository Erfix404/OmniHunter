import json
import os
import re
import sys
import urllib.request
from pathlib import Path
from typing import Any

if str(Path(__file__).resolve().parent.parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.triage import evaluate_project, normalize_text

# ponytail: rule-based template generation over dynamic LLM calls; upgrade to Claude Haiku/Sonnet generator when customized client tone is needed.
# ponytail: direct HTTP call over heavy LLM SDKs; upgrade to anthropic/openai packages if streaming or multi-turn chats are required.

DEFAULT_FLOORS_IRT: dict[str, float] = {
    "bots": 1800000.0,
    "automation": 1800000.0,
    "translation": 600000.0,
    "excel": 600000.0,
    "scraping": 1800000.0,
    "scripting": 1800000.0,
}

DEFAULT_FLOORS_USD: dict[str, float] = {
    "bots": 25.0,
    "automation": 25.0,
    "translation": 15.0,
    "excel": 15.0,
    "scraping": 25.0,
    "scripting": 25.0,
}

DEFAULT_DELIVERY_DAYS: dict[str, int] = {
    "bots": 3,
    "automation": 3,
    "translation": 1,
    "excel": 1,
    "scraping": 2,
    "scripting": 2,
}

ROADMAPS: dict[str, list[str]] = {
    "bots": [
        "گام ۱: تحلیل جریان تعامل، طراحی ساختار پیام‌ها و تعریف ماشین حالت (FSM)",
        "گام ۲: پیاده‌سازی منطق هسته ربات و اتصال به پایگاه داده (SQLite / Redis)",
        "گام ۳: پیاده‌سازی پنل مدیریت، اعتبارسنجی ورودی‌ها و هندلینگ خطای شبکه",
        "گام ۴: تست سناریوهای کاربری، استقرار کانتینری Docker و تحویل داکیومنت راه‌اندازی",
    ],
    "automation": [
        "گام ۱: نگاشت کامل جریان داده، رویدادهای محرک (Triggers) و اندپوینت‌های مبدا/مقصد",
        "گام ۲: پیاده‌سازی وب‌هوک‌ها و سناریوهای اتوماسیون با n8n و اسکریپت‌های پایتون",
        "گام ۳: اضافه کردن لایه اعتبارسنجی داده، مدیریت خطا (Retry Policy) و سیستم لاگ‌گیری",
        "گام ۴: تست فرآیند در محیط پایلوت، مانیتورینگ عملکرد و تحویل مستندات یکپارچه‌سازی",
    ],
    "translation": [
        "گام ۱: استخراج و معادل‌یابی اصطلاحات تخصصی و تدوین واژه‌نامه یکپارچه (Glossary)",
        "گام ۲: ترجمه دقیق، تخصصی و روان متن با حفظ امانت علمی و لحن دانشگاهی",
        "گام ۳: بازخوانی تطبیقی دوگانه (Bilingual Proofreading) و اصلاح ساختارهای دستوری",
        "گام ۴: صفحه‌آرایی، تطبیق فرمول‌ها/جداول و تحویل فایل نهایی با فرمت درخواستی",
    ],
    "excel": [
        "گام ۱: بررسی و ساختاردهی داده‌های خام و تدوین الگوهای اعتبارسنجی",
        "گام ۲: پیاده‌سازی فرمول‌های محاسباتی پیشرفته و اتوماسیون استخراج با openpyxl و pandas",
        "گام ۳: طراحی داشبورد گزارش‌گیری، فرمت‌بندی شرطی و بهینه‌سازی خوانایی فایل",
        "گام ۴: تست صحت نتایج محاسباتی با داده‌های مرجع و تحویل فایل نهایی با راهنمای فرمول‌ها",
    ],
    "scraping": [
        "گام ۱: تحلیل ساختار صفحات، ریکوئست‌های شبکه و تعیین استراتژی بهینه خزش",
        "گام ۲: پیاده‌سازی اسکریپت استخراج داده با Playwright/BeautifulSoup با قابلیت دور زدن محدودیت‌ها",
        "گام ۳: پاکسازی، نرمال‌سازی ساختار داده‌ها و ذخیره‌سازی در فرمت JSON / CSV / Excel",
        "گام ۴: تست خزش در مقیاس آزمایشی، بهینه‌سازی سرعت و ارائه اسکریپت اجرای خودکار",
    ],
    "scripting": [
        "گام ۱: تحلیل معماری ورودی/خروجی و تفکیک ماژول‌های پردازشی",
        "گام ۲: کدنویسی منطق هسته برنامه با ساختار شیءگرا/ماژولار و پایتون استاندارد",
        "گام ۳: پیاده‌سازی سیستم مدیریت خطا، لاگ‌گیری و اعتبارسنجی ورودی‌ها",
        "گام ۴: نوشتن تست‌های عملکردی، ساخت فایل کانفیگ و تحویل کد تمیز به همراه داکیومنت",
    ],
}

BANNED_CLICHES: list[str] = [
    "سلام و احترام، امیدوارم حالتون خوب باشه",
    "من یک برنامه‌نویس با تجربه و با انگیزه هستم",
    "امیدوارم حالتون خوب باشه",
    "با سلام و احترام",
    "من یک برنامه نویس با تجربه",
    "امیدوارم روز خوبی داشته باشید",
    "با کمال میل می‌توانم",
    "i am an experienced developer",
    "hope you are doing well",
]

# Scope-specific technical hooks (direct, no clichés)
DEFAULT_TECHNICAL_HOOKS: dict[str, str] = {
    "bots": "معماری ربات بر پایه aiogram 3.x با FSM و مدیریت نشست‌ها طراحی می‌شود تا پایداری و مقیاس‌پذیری در بار بالا تضمین گردد.",
    "automation": "پایپلاین اتوماسیون با وب‌هوک‌های n8n و اسکریپت‌های پایتون طراحی می‌شود تا جریان داده بدون افت یا خطا پردازش شود.",
    "translation": "ترجمه تخصصی بر اساس واژه‌نامه یکپارچه حوزه مربوطه انجام می‌شود تا یکدستی اصطلاحات در کل متن حفظ گردد.",
    "excel": "پردازش داده‌ها با ترکیب فرمول‌های پیشرفته اکسل و اسکریپت‌های pandas/openpyxl اتوماسیون می‌شود.",
    "scraping": "خزنده مبتنی بر Playwright با مدیریت ریت‌لیمیت و دور زدن محدودیت‌های anti-bot طراحی می‌شود.",
    "scripting": "ساختار ماژولار با FastAPI و Type Hinting کامل پیاده‌سازی می‌شود تا نگهداری و توسعه‌پذیری بلندمدت تضمین گردد.",
}

# Scope-specific prerequisites
DEFAULT_PREREQUISITES: dict[str, list[str]] = {
    "bots": ["توکن ربات (Bot Token) از BotFather", "نمونه جریان تعامل کاربران", "مشخصات درگاه پرداخت (در صورت نیاز)"],
    "automation": ["اندپوینت‌های API مبدا و مقصد", "نمونه داده ورودی/خروجی", "اطلاعات احراز هویت سرویس‌ها"],
    "translation": ["فایل‌های متن اصلی", "واژه‌نامه تخصصی حوزه (در صورت وجود)", "فرمت خروجی مورد نظر"],
    "excel": ["فایل‌های اکسل نمونه", "توضیح ساختار داده‌ها و ستون‌ها", "خروجی مورد انتظار"],
    "scraping": ["آدرس URL صفحات هدف", "نمونه داده‌های مورد نیاز", "فرمت خروجی (CSV/JSON/Excel)"],
    "scripting": ["مشخصات API و اندپوینت‌ها", "نمونه داده ورودی", "اطلاعات دسترسی سرور/دیتابیس"],
}

# Scope-specific clarifying questions
DEFAULT_CLARIFYING_QUESTIONS: dict[str, str] = {
    "bots": "آیا ربات نیاز به مدیریت نشست‌های همزمان چند کاربره و ذخیره‌سازی وضعیت (State) دارد؟",
    "automation": "حجم تقریبی درخواست‌ها در ساعت و سیاست بازتلاش (Retry) مورد نظر چگونه است؟",
    "translation": "آیا واژه‌نامه تخصصی از قبل تدوین شده یا باید در فاز اول پروژه استخراج شود؟",
    "excel": "آیا فرمول‌ها باید در خود فایل اکسل باشند یا پردازش با اسکریپت پایتون خارجی هم قابل قبول است؟",
    "scraping": "آیا سایت هدف از رندرینگ جاوااسکریپت (SPA) استفاده می‌کند یا محتوا در HTML استاتیک موجود است؟",
    "scripting": "آیا خروجی نهایی باید به صورت REST API باشد یا اسکریپت CLI کافی است؟",
}


def _parse_num(val: Any) -> float | None:
    if val is None or val == "":
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def _detect_tech_stack(project: dict[str, Any], scope: str) -> list[str]:
    title_norm = normalize_text(project.get("title"))
    desc_norm = normalize_text(project.get("description"))
    combined = f"{title_norm} {desc_norm}"

    if scope == "bots":
        stack = ["Python 3.12"]
        if "بله" in combined or "bale" in combined:
            stack.append("Bale Bot API (bale-bot-python / HTTP API)")
        else:
            stack.append("aiogram 3.x (Asynchronous)")
            stack.append("python-telegram-bot")
        stack.extend(["SQLite / Redis", "Docker"])
        return stack

    if scope == "automation":
        stack = [
            "Python 3.12",
            "n8n Workflow Engine",
            "Webhook Endpoints",
            "REST APIs Integration",
            "Background Workers / Cron",
        ]
        return stack

    if scope == "translation":
        return [
            "Specialized Academic Translation (EN <-> FA)",
            "Technical Terminology Glossary",
            "Bilingual Quality Verification",
            "LaTeX / Word Document Formatting",
        ]

    if scope == "excel":
        stack = ["Python 3.12", "openpyxl", "pandas", "Advanced Excel Formulas"]
        if "vba" in combined or "ماکرو" in combined:
            stack.append("VBA / Macro Automation")
        stack.append("Data Cleaning Pipeline")
        return stack

    if scope == "scraping":
        return [
            "Python 3.12",
            "Playwright (Headless Browser)",
            "BeautifulSoup4",
            "Requests / aiohttp",
            "CSV / JSON / Excel Exporter",
            "Anti-Bot & Rate-Limiting Protection",
        ]

    # scripting (default)
    return [
        "Python 3.12",
        "FastAPI / Requests",
        "SQLite Database",
        "Modular CLI Architecture",
        "Automated Error Handling & Logging",
    ]


def _calculate_pricing(
    project: dict[str, Any], scope: str
) -> tuple[int | float, int]:
    currency = str(project.get("currency") or "IRT").strip().upper()
    b_min = _parse_num(project.get("budget_min"))
    b_max = _parse_num(project.get("budget_max"))

    is_usd = currency in ("USD", "$")
    is_irr = currency in ("IRR", "RIAL", "RIALS")

    if is_usd:
        default_floor = DEFAULT_FLOORS_USD.get(scope, 25.0)
    elif is_irr:
        default_floor = DEFAULT_FLOORS_IRT.get(scope, 1800000.0) * 10.0
    else:
        default_floor = DEFAULT_FLOORS_IRT.get(scope, 1800000.0)

    if b_min is not None and b_max is not None:
        b_low = min(b_min, b_max)
        b_high = max(b_min, b_max)
        if b_low == b_high:
            raw_bid = b_low
        else:
            # 65% into the range (competitive sweet spot between 60% and 70%)
            raw_bid = b_low + 0.65 * (b_high - b_low)
    elif b_min is not None:
        raw_bid = b_min * 1.15
    elif b_max is not None:
        raw_bid = b_max * 0.80
    else:
        raw_bid = default_floor

    # Clean rounding
    if is_usd:
        suggested_bid = max(5, int(round(raw_bid / 5.0) * 5))
    elif is_irr:
        suggested_bid = max(100000, int(round(raw_bid / 500000.0) * 500000))
    else:
        suggested_bid = max(50000, int(round(raw_bid / 50000.0) * 50000))

    # Delivery days calculation
    baseline_days = DEFAULT_DELIVERY_DAYS.get(scope, 2)
    if is_usd and suggested_bid >= 80:
        delivery_days = min(5, baseline_days + 1)
    elif not is_usd and not is_irr and suggested_bid >= 5000000:
        delivery_days = min(5, baseline_days + 1)
    elif is_irr and suggested_bid >= 50000000:
        delivery_days = min(5, baseline_days + 1)
    else:
        delivery_days = baseline_days

    return suggested_bid, max(1, min(5, delivery_days))


def _resolve_architect_profile(profile: Any | None) -> Any | None:
    """Lazily resolve a profile object without hard-importing core.profile."""
    if profile is None:
        return None
    if (
        hasattr(profile, "get_relevant_portfolio")
        and hasattr(profile, "get_relevant_evidence")
        and hasattr(profile, "tone")
    ):
        return profile
    if isinstance(profile, dict):
        try:
            from core.profile import FreelancerProfile

            return FreelancerProfile(data=profile)
        except Exception:
            return None
    return None


def _estimate_hours_for_bid(scope: str, tech_stack: list[str]) -> float:
    try:
        from core.triage import DEFAULT_ESTIMATED_HOURS

        return float(DEFAULT_ESTIMATED_HOURS.get(scope, 4.0))
    except Exception:
        return 4.0


def _align_bid_with_profile_rate(
    suggested_bid: int | float,
    scope: str,
    currency: str,
    tech_stack: list[str],
    profile: Any | None,
) -> int | float:
    """Align ``suggested_bid`` with the profile hourly rate when available."""
    cur = str(currency or "IRT").strip().upper()
    is_usd = cur in ("USD", "$")
    is_irr = cur in ("IRR", "RIAL", "RIALS")
    try:
        ident = profile.identity
        if not isinstance(ident, dict):
            return suggested_bid
        hourly = ident.get("hourly_rate_usd") if is_usd else ident.get("hourly_rate_irt")
        if hourly is None:
            return suggested_bid
        hourly_rate = float(hourly)
    except (ValueError, TypeError, AttributeError):
        return suggested_bid
    if hourly_rate <= 0:
        return suggested_bid

    hours = _estimate_hours_for_bid(scope, tech_stack)
    rate_based = hourly_rate * hours
    if is_irr:
        rate_based *= 10
    floor = suggested_bid if isinstance(suggested_bid, (int, float)) else 0
    try:
        floor_f = float(floor)
    except (ValueError, TypeError):
        floor_f = 0.0
    target = max(rate_based, floor_f)
    if is_usd:
        return max(5, int(round(target / 5.0) * 5))
    if is_irr:
        return max(100000, int(round(target / 500000.0) * 500000))
    return max(50000, int(round(target / 50000.0) * 50000))


def _strip_code_blocks(text: str) -> str:
    """Remove markdown code blocks, inline code, and raw code snippets."""
    if not text:
        return text
    # Remove fenced code blocks (```...```) entirely.
    cleaned = re.sub(r"```.*?```", "", text, flags=re.DOTALL)
    # Remove any leftover fence markers.
    cleaned = cleaned.replace("```", "")
    # Remove inline code spans (`...`) but keep the inner text.
    cleaned = re.sub(r"`([^`\n]+)`", r"\1", cleaned)
    return cleaned.strip()


def _build_rule_based_proposal(
    project: dict[str, Any],
    scope: str,
    tech_stack: list[str],
    roadmap: list[str],
    delivery_days: int,
) -> str:
    """Build a high-level 4-pillar persuasion proposal (no code, no code blocks)."""
    title = str(project.get("title") or "").strip()
    title_ref = f" «{title}»" if title else ""

    is_bale = any("bale" in str(item).lower() for item in tech_stack) or (
        "بله" in normalize_text(project.get("title"))
        or "بله" in normalize_text(project.get("description"))
    )

    # Pillar 1: Pain-point empathy & business context (scope-specific).
    if scope == "bots":
        platform_ref = "پیام‌رسان بله" if is_bale else "تلگرام"
        empathy = (
            f"دغدغه اصلی شما در این پروژه{title_ref} کاملاً مشخص است: یک {platform_ref} پایدار "
            "که بدون قطعی پاسخ بدهد، سفارش‌ها و پیام‌ها را دقیق و امن ثبت کند و در ساعات شلوغی هم "
            "بدون افت کیفیت کار کند. مهم‌ترین ریسک چنین پروژه‌هایی از نگاه کسب‌وکار، ناپایداری، "
            "از دست رفتن پیام‌ها و درگیر شدن با محدودیت یا مسدود شدن حساب است؛ "
            "معماری پیشنهادی من دقیقاً برای رفع همین دغدغه‌ها طراحی شده است."
        )
        tool_hint = (
            "پیام‌رسان بله" if is_bale
            else "پایتون با فریم‌ورک غیرهمگام aiogram"
        )
        step_one_tail = "بررسی نیازمندی‌ها، دریافت توکن و اتصال امن اولیه به پیام‌رسان و پیکربندی محیط اجرا"
        step_two_tail = "پیاده‌سازی هسته پردازش و منطق خودکار گفتگو با مدیریت خطا، تلاش مجدد و پایداری در بار همزمان"
    elif scope == "automation":
        empathy = (
            f"درک می‌کنم که دغدغه اصلی شما در این پروژه{title_ref} حذف ساعت‌ها کار دستی تکراری، "
            "جلوگیری از خطای انسانی و اطمینان از انتقال دقیق و بدون افت داده‌ها بین سرویس‌هاست. "
            "بزرگ‌ترین درد چنین فرآیندهایی، توقف‌های نامرئی و مغایرت داده‌هاست که مستقیم روی درآمد و اعتماد مشتری اثر می‌گذارد؛ "
            "راه‌حل پیشنهادی من دقیقاً روی همین نقطه تمرکز دارد."
        )
        tool_hint = "پایتون در کنار ابزارهای اتوماسیون و وب‌هوک"
        step_one_tail = "بررسی نیازمندی‌ها، شناسایی نقاط اتصال سرویس‌ها و پیکربندی امن اولیه ارتباط‌ها"
        step_two_tail = "پیاده‌سازی هسته پردازش و منطق خودکار انتقال داده با مدیریت خطا، تلاش مجدد و پایداری"
    elif scope == "translation":
        empathy = (
            f"دغدغه اصلی شما در این پروژه{title_ref} روشن است: متنی دقیق، روان و علمی که اصطلاحات تخصصی "
            "در سراسر آن یکدست باشد و اعتبار علمی کار حفظ شود. درد رایج، ترجمه‌های تحت‌اللفظی یا ماشینی است "
            "که اعتماد خواننده را از بین می‌برد؛ فرآیند پیشنهادی من دقیقاً برای رفع همین دغدغه طراحی شده است."
        )
        tool_hint = "فرآیند ترجمه تخصصی با واژه‌نامه یکپارچه"
        step_one_tail = "بررسی نیازمندی‌ها، استخراج اصطلاحات کلیدی و پیکربندی اولیه واژه‌نامه تخصصی"
        step_two_tail = "پیاده‌سازی هسته پردازش و منطق خودکار بازبینی کیفی با مدیریت خطا و پایداری یکدستی واژگان"
    elif scope == "excel":
        empathy = (
            f"دغدغه اصلی شما در این پروژه{title_ref} مشخص است: داده‌هایی تمیز و قابل اتکا که بدون ساعت‌ها کار دستی، "
            "محاسباتشان دقیق باشد و گزارش‌گیری از آن‌ها ساده شود. درد رایج، فرمول‌های شکننده و خطاهای پنهان محاسباتی است؛ "
            "راه‌حل پیشنهادی من دقیقاً برای رفع همین دغدغه طراحی شده است."
        )
        tool_hint = "پایتون با کتابخانه‌های پردازش داده در کنار فرمول‌های پیشرفته اکسل"
        step_one_tail = "بررسی نیازمندی‌ها، شناخت ساختار داده‌ها و پیکربندی امن اولیه فایل‌ها و الگوها"
        step_two_tail = "پیاده‌سازی هسته پردازش و منطق خودکار محاسبات و پاکسازی با مدیریت خطا و پایداری نتایج"
    elif scope == "scraping":
        empathy = (
            f"دغدغه اصلی شما در این پروژه{title_ref} کاملاً قابل درک است: دسترسی به داده‌هایی دقیق و به‌روز "
            "بدون صرف ساعت‌ها کار دستی، با خروجی تمیز و قابل استفاده. درد اصلی چنین پروژه‌هایی، مسدود شدن دسترسی، "
            "ناقص ماندن داده‌ها و بی‌ثباتی در برابر تغییرات سایت است؛ راه‌حل پیشنهادی من دقیقاً برای رفع همین دغدغه‌ها طراحی شده است."
        )
        tool_hint = "پایتون با ابزارهای مرورگر خودکار و استخراج ساختاریافته"
        step_one_tail = "بررسی نیازمندی‌ها، شناسایی صفحات هدف و پیکربندی امن اولیه دسترسی و نرخ درخواست"
        step_two_tail = "پیاده‌سازی هسته پردازش و منطق خودکار استخراج و پاکسازی داده با مدیریت خطا و پایداری"
    else:  # scripting
        empathy = (
            f"دغدغه اصلی شما در این پروژه{title_ref} روشن است: ابزاری پایدار و قابل اتکا که ورودی‌ها را درست پردازش کند، "
            "در شرایط خطا متوقف نشود و نگهداری آن در بلندمدت ساده باشد. درد رایج، اسکریپت‌های شکننده‌ای است که با اولین "
            "ورودی غیرمنتظره از کار می‌افتند؛ معماری پیشنهادی من دقیقاً برای رفع همین دغدغه طراحی شده است."
        )
        tool_hint = "پایتون با ساختار ماژولار و تمیز"
        step_one_tail = "بررسی نیازمندی‌ها، شناخت ورودی‌ها و خروجی‌ها و پیکربندی امن اولیه محیط اجرا"
        step_two_tail = "پیاده‌سازی هسته پردازش و منطق خودکار برنامه با مدیریت خطا، ثبت رویداد و پایداری"

    intro = f"{empathy} برای این منظور، از {tool_hint} استفاده می‌کنم."

    proposal = (
        f"{intro}\n\n"
        "طرح کلی اجرا در ۳ گام کلان:\n"
        f"گام اول: {step_one_tail}.\n"
        f"گام دوم: {step_two_tail}.\n"
        "گام سوم: آزمون نهایی، آماده‌سازی خروجی تمیز و تحویل شفاف.\n\n"
        "کاهش ریسک و تضمین پایداری:\n"
        "تعهد می‌دهم پیش از تحویل، تست کامل سناریوهای اصلی و حالت‌های مرزی را انجام دهم، "
        "مستندات شفاف نحوه اجرا و استفاده از سیستم را تحویل دهم "
        "و پشتیبانی اولیه برای رفع اشکال را بدون هزینه اضافه انجام دهم تا با خیال راحت تصمیم بگیرید.\n\n"
        "اگر این چارچوب کلی مدنظر شماست، خوشحال می‌شم در چت گفتگو کنیم تا ساختار خروجی و زمان‌بندی رو دقیق‌تر هماهنگ کنیم.\n"
        f"زمان تحویل: {delivery_days} روز کاری."
    )
    return _strip_code_blocks(proposal).strip()


def _clean_llm_proposal(text: str) -> str | None:
    """Filter LLM proposal text, stripping sentences with banned cliches or returning None."""
    if not text:
        return None

    text = _strip_code_blocks(text)
    if not text:
        return None

    # Check if any cliche is present
    has_cliche = any(cliche.lower() in text.lower() for cliche in BANNED_CLICHES)
    if not has_cliche:
        clean = text.strip()
        return clean if len(clean) > 50 else None

    # Split into lines and sentences to strip the cliche sentences
    cleaned_lines: list[str] = []
    for line in text.splitlines():
        if not any(cliche.lower() in line.lower() for cliche in BANNED_CLICHES):
            cleaned_lines.append(line)
        else:
            sentences = re.split(r'(?<=[.!؟?\n])\s+', line)
            kept = [
                s.strip()
                for s in sentences
                if s.strip() and not any(cliche.lower() in s.lower() for cliche in BANNED_CLICHES)
            ]
            if kept:
                cleaned_lines.append(" ".join(kept))

    cleaned = "\n".join(cleaned_lines).strip()
    if any(cliche.lower() in cleaned.lower() for cliche in BANNED_CLICHES):
        return None
    if len(cleaned) < 50:
        return None
    return cleaned


def _query_llm_proposal(
    project: dict[str, Any],
    scope: str,
    tech_stack: list[str],
    roadmap: list[str],
    delivery_days: int,
) -> str | None:
    anthropic_key = os.getenv("ANTHROPIC_API_KEY")
    openai_key = os.getenv("OPENAI_API_KEY")
    if not anthropic_key and not openai_key:
        return None

    title = project.get("title", "")
    desc = project.get("description", "")
    prompt = (
        f"You are a senior technical architect drafting a freelance proposal in Persian.\n"
        f"Project Title: {title}\n"
        f"Project Description: {desc}\n"
        f"Scope: {scope}\n"
        f"Tech Stack: {', '.join(tech_stack)}\n"
        f"Roadmap: {' | '.join(roadmap)}\n"
        f"Delivery Days: {delivery_days}\n"
        "Rules:\n"
        "- Respond in professional, human Persian.\n"
        "- NO greetings or clichés (NEVER say 'سلام', 'امیدوارم حالتون خوب باشه', 'من با تجربه هستم').\n"
        "- NEVER include raw code, code snippets, or markdown code blocks (no ``` fences, no inline code).\n"
        "- Follow the 4-pillar persuasion blueprint: (1) pain-point empathy and business context, "
        "(2) a clean 3-step high-level conceptual workflow with no low-level code, "
        "(3) risk reversal with pre-delivery testing, clean usage docs, and free initial bug-fix support, "
        "(4) a friendly low-pressure invitation to discuss output structure and timing in chat.\n"
        "- Under 300 words."
    )

    if anthropic_key:
        try:
            req = urllib.request.Request(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": anthropic_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                data=json.dumps(
                    {
                        "model": "claude-3-5-haiku-latest",
                        "max_tokens": 800,
                        "messages": [{"role": "user", "content": prompt}],
                    }
                ).encode("utf-8"),
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                content = data.get("content", [])
                if content and isinstance(content, list):
                    raw_text = content[0].get("text", "")
                    cleaned = _clean_llm_proposal(raw_text)
                    if cleaned:
                        return cleaned
        except Exception:
            pass

    if openai_key:
        try:
            req = urllib.request.Request(
                "https://api.openai.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {openai_key}",
                    "Content-Type": "application/json",
                },
                data=json.dumps(
                    {
                        "model": "gpt-4o-mini",
                        "max_tokens": 800,
                        "messages": [{"role": "user", "content": prompt}],
                    }
                ).encode("utf-8"),
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                choices = data.get("choices", [])
                if choices and isinstance(choices, list):
                    raw_text = choices[0].get("message", {}).get("content", "")
                    cleaned = _clean_llm_proposal(raw_text)
                    if cleaned:
                        return cleaned
        except Exception:
            pass

    return None


def _enforce_tone_avoid(text: str, avoid_phrases: list[str]) -> str:
    """Remove sentences/lines containing banned tone phrases (case-insensitive)."""
    if not text or not avoid_phrases:
        return text
    banned = [str(p).strip().lower() for p in avoid_phrases if str(p).strip()]
    if not banned:
        return text
    out_lines: list[str] = []
    for line in text.splitlines():
        low = line.lower()
        if not any(b in low for b in banned):
            out_lines.append(line)
            continue
        sentences = re.split(r"(?<=[.!؟?\n])\s+", line)
        kept = [
            s.strip()
            for s in sentences
            if s.strip() and not any(b in s.lower() for b in banned)
        ]
        if kept:
            out_lines.append(" ".join(kept))
    cleaned = "\n".join(out_lines).strip()
    for b in banned:
        if b and b in cleaned.lower():
            # Last-resort: blank the residual phrase occurrences rather than
            # shipping a banned phrase.
            cleaned = re.sub(re.escape(b), "", cleaned, flags=re.IGNORECASE)
    return " ".join(cleaned.split())


def _inject_profile_evidence(
    proposal: str, scope: str, profile: Any | None
) -> str:
    """Append 1-2 relevant portfolio results or skill evidence to the proposal."""
    if profile is None:
        return proposal
    snippets: list[str] = []
    try:
        portfolio_items = profile.get_relevant_portfolio(scope) or []
    except Exception:
        portfolio_items = []
    for item in portfolio_items[:2]:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title", "")).strip()
        result = str(item.get("result", "")).strip()
        if title and result:
            snippets.append(f"نمونه‌کار مرتبط «{title}»: {result}")
        elif result:
            snippets.append(f"نمونه‌کار مرتبط: {result}")
        elif title:
            snippets.append(f"نمونه‌کار مرتبط: {title}")
    try:
        evidence = profile.get_relevant_evidence(scope) or []
    except Exception:
        evidence = []
    for ev in evidence:
        if len(snippets) >= 2:
            break
        ev_str = str(ev).strip()
        if ev_str and ev_str not in snippets:
            snippets.append(ev_str)
    if not snippets:
        return proposal
    evidence_block = "\n".join(f"• {s}" for s in snippets[:2])
    return (
        f"{proposal.rstrip()}\n\n"
        "سوابق مرتبط:\n"
        f"{evidence_block}"
    ).strip()


def generate_architecture(
    project: dict[str, Any], config: dict[str, Any] | None = None,
    profile: Any | None = None,
) -> dict[str, Any]:
    """Generate architecture specification, roadmap, pricing, and proposal.

    Return contract:
    {
        "suggested_bid": int | float,
        "delivery_days": int,
        "tech_stack": list[str],
        "roadmap": list[str],
        "proposal": str,
    }
    """
    if not isinstance(project, dict):
        project = {}

    scope = project.get("scope")
    if not scope or scope not in ROADMAPS:
        # Fallback to triage evaluation or default to scripting
        eval_res = evaluate_project(project, config)
        scope = eval_res.get("scope") or "scripting"

    suggested_bid, delivery_days = _calculate_pricing(project, scope)
    tech_stack = _detect_tech_stack(project, scope)
    roadmap = list(ROADMAPS.get(scope, ROADMAPS["scripting"]))
    prof = _resolve_architect_profile(profile)

    # Try optional LLM proposal first if configured, else rule-based
    proposal = _query_llm_proposal(
        project, scope, tech_stack, roadmap, delivery_days
    )
    if proposal:
        proposal = _strip_code_blocks(proposal)
    if not proposal:
        proposal = _build_rule_based_proposal(
            project, scope, tech_stack, roadmap, delivery_days
        )
    else:
        # Rule-based blueprint is the canonical persuasion structure; merge the
        # LLM draft into it only when it adds no code and keeps the pillars.
        proposal = _strip_code_blocks(proposal)
        if "```" in proposal:
            proposal = _build_rule_based_proposal(
                project, scope, tech_stack, roadmap, delivery_days
            )

    technical_hook = DEFAULT_TECHNICAL_HOOKS.get(scope, DEFAULT_TECHNICAL_HOOKS["scripting"])

    if prof is not None:
        proposal = _inject_profile_evidence(proposal, scope, prof)
        try:
            avoid = prof.tone.get("avoid", []) if isinstance(prof.tone, dict) else []
        except Exception:
            avoid = []
        avoid_list = [str(p) for p in (avoid or []) if str(p).strip()]
        proposal = _enforce_tone_avoid(proposal, avoid_list)
        proposal = _strip_code_blocks(proposal)
        technical_hook = _enforce_tone_avoid(str(technical_hook), avoid_list)
        currency = str(project.get("currency") or "IRT")
        suggested_bid = _align_bid_with_profile_rate(
            suggested_bid, scope, currency, tech_stack, prof
        )

    return {
        "suggested_bid": suggested_bid,
        "delivery_days": delivery_days,
        "tech_stack": tech_stack,
        "roadmap": roadmap,
        "proposal": proposal,
        "technical_hook": technical_hook,
        "prerequisites": list(DEFAULT_PREREQUISITES.get(scope, DEFAULT_PREREQUISITES["scripting"])),
        "clarifying_question": DEFAULT_CLARIFYING_QUESTIONS.get(scope, DEFAULT_CLARIFYING_QUESTIONS["scripting"]),
    }


if __name__ == "__main__":
    sample_proj = {
        "title": "ربات تلگرام ثبت سفارش",
        "description": "ربات پایتون برای دریافت اطلاعات سفارش و ذخیره در دیتابیس",
        "scope": "bots",
        "budget_min": 2000000,
        "budget_max": 3000000,
        "currency": "IRT",
    }
    arch = generate_architecture(sample_proj)
    assert len(arch["roadmap"]) >= 3
    assert "aiogram" in " ".join(arch["tech_stack"]).lower() or "python" in " ".join(arch["tech_stack"]).lower()
    assert arch["suggested_bid"] >= 2000000
    assert len(arch["proposal"]) > 50
    assert not any(cliche in arch["proposal"] for cliche in BANNED_CLICHES)
    print("All architect self-checks passed.")
