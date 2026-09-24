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


def _build_rule_based_proposal(
    project: dict[str, Any],
    scope: str,
    tech_stack: list[str],
    roadmap: list[str],
    delivery_days: int,
) -> str:
    stack_list = "\n".join(f"• {item}" for item in tech_stack)
    roadmap_list = "\n".join(f"{step}" for step in roadmap)

    if scope == "bots":
        framework_mention = (
            "Bale Bot API (یا کلاینت اختصاصی بله)"
            if any("bale" in item.lower() for item in tech_stack)
            else "فریم‌ورک غیرهمگام aiogram 3.x"
        )
        opening = (
            f"برای پیاده‌سازی این پروژه، معماری پیشنهادی مبتنی بر پایتون ۳.۱۲ و {framework_mention} است "
            "که پایداری و پردازش همزمان بالایی ارائه می‌دهد. مدیریت نشست‌های کاربران، ماشین حالت (FSM) "
            "و ذخیره‌سازی داده‌ها در یک پایگاه داده استاندارد و ایمن انجام خواهد شد."
        )
    elif scope == "automation":
        opening = (
            "برای خودکارسازی این فرآیند، پایپ‌لاین بهینه و ماژولار با پایتون و ابزارهای وب‌هوک/n8n "
            "طراحی و پیاده‌سازی می‌شود. فرآیند انتقال داده با اعتبارسنجی ورودی، بازتلاش خودکار (Retry Policy) "
            "و سیستم ثبت لاگ پیاده‌سازی خواهد شد تا از صحت و عدم افت اطلاعات اطمینان حاصل شود."
        )
    elif scope == "translation":
        opening = (
            "برای انجام ترجمه تخصصی این پروژه، فرآیند بر پایه معادل‌یابی دقیق دانشگاهی و نگارش سلیس و علمی "
            "پیش خواهد رفت. در فاز نخست، یک واژه‌نامه تخصصی (Glossary) از اصطلاحات کلیدی حوزه مربوطه استخراج و تدوین "
            "می‌شود تا یکدستی واژگان در تمام متن حفظ شده و از ترجمه‌های تحت‌اللفظی یا ماشینی پرهیز گردد."
        )
    elif scope == "excel":
        opening = (
            "برای پردازش و اتوماسیون داده‌های اکسل، از ترکیب فرمول‌های محاسباتی پیشرفته و اسکریپت‌های پایتون "
            "با کتابخانه‌های openpyxl و pandas استفاده می‌شود. ساختار داده‌ها نرمال‌سازی شده، اعتبارسنجی خودکار "
            "اعمال می‌گردد و خروجی نهایی با کاربری آسان و گزارش‌گیری تمیز آماده خواهد شد."
        )
    elif scope == "scraping":
        opening = (
            "برای استخراج ساختاریافته داده‌های مورد نظر، خزنده‌ای پایدار مبتنی بر Python 3.12 و ابزارهای "
            "Playwright / BeautifulSoup پیاده‌سازی خواهد شد. اسکریپت با مدیریت ریت‌لیمیت، دور زدن محدودیت‌های خزش "
            "و پردازش درخواست‌های داینامیک، خروجی داده‌ها را در فرمت استاندارد (Excel / CSV / JSON) استخراج می‌کند."
        )
    else:  # scripting
        opening = (
            "برای پیاده‌سازی این اسکریپت، ساختاری ماژولار و تمیز با Python 3.12، مدیریت خطا و لاگ‌گیری استاندارد "
            "طراحی می‌شود. تفکیک لایه‌های پردازش و داده با Type Hinting کامل پیاده‌سازی خواهد شد تا پایداری و نگهداری "
            "ساده کد در طولانی‌مدت تضمین شود."
        )

    proposal = (
        f"{opening}\n\n"
        "پشته فنی و ابزارهای مورد استفاده:\n"
        f"{stack_list}\n\n"
        "نقشه راه و مراحل اجرا:\n"
        f"{roadmap_list}\n\n"
        "تعهد کیفیت و پشتیبانی:\n"
        "• تست جامع سناریوهای کاربری و پوشش تمام حالت‌های مرزی قبل از تحویل\n"
        "• تحویل سورس کد تمیز به همراه داکیومنت و راهنمای شفاف راه‌اندازی\n"
        f"• زمان تحویل: {delivery_days} روز کاری به همراه پشتیبانی و اعمال بازخوردهای شما تا رضایت کامل"
    )
    return proposal.strip()


def _clean_llm_proposal(text: str) -> str | None:
    """Filter LLM proposal text, stripping sentences with banned cliches or returning None."""
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
        "- Start immediately with direct technical solution and architecture.\n"
        "- Detail the roadmap, testing assurance, and delivery schedule.\n"
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
    if not proposal:
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
