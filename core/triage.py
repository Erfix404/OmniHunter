import re
from typing import Any

# ponytail: heuristic keyword scoring over LLM classifier; ceiling ~90% accuracy on ambiguous briefs, upgrade to Claude Haiku/Sonnet triage when budget allows.
# ponytail: static baseline hours per scope over task breakdown estimation; upgrade to LLM scope estimator when multi-feature tasks are scanned.

DEFAULT_SCAM_BLACKLIST: list[str] = [
    "بیعانه",
    "پرداخت اول",
    "100% upfront",
    "upfront payment",
    "تضمین پرداخت",
    "شارژ حساب",
    "واریز بیعانه",
    "کارمزد اولیه",
    "تست رایگان",
    "پروژه تستی رایگان",
    "هزینه ثبت نام",
    "پرداخت قبل از شروع",
]

DEFAULT_SCOPES: dict[str, dict[str, Any]] = {
    "bots": {
        "name": "Telegram & Bale Bots",
        "enabled": True,
        "min_budget_irt": 1500000,
        "min_budget_usd": 20,
        "keywords": [
            "ربات تلگرام",
            "تلگرام",
            "بله",
            "telegram bot",
            "bale bot",
            "aiogram",
            "telethon",
            "pyrogram",
            "ربات",
        ],
    },
    "automation": {
        "name": "Process Automation",
        "enabled": True,
        "min_budget_irt": 1500000,
        "min_budget_usd": 20,
        "keywords": [
            "اتوماسیون",
            "n8n",
            "وب هوک",
            "webhook",
            "zapier",
            "automation",
            "خودکارسازی",
        ],
    },
    "translation": {
        "name": "Specialized & Academic Translation",
        "enabled": True,
        "min_budget_irt": 500000,
        "min_budget_usd": 10,
        "keywords": [
            "ترجمه مقاله",
            "ترجمه تخصصی",
            "ترجمه انگلیسی",
            "ترجمه متون",
            "scientific translation",
            "ترجمه",
        ],
    },
    "excel": {
        "name": "Excel & Data Cleaning",
        "enabled": True,
        "min_budget_irt": 500000,
        "min_budget_usd": 10,
        "keywords": [
            "اکسل",
            "excel",
            "vba",
            "ماکرو",
            "فرمول نویسی",
            "openpyxl",
            "pandas",
        ],
    },
    "scraping": {
        "name": "Web Scraping & Data Extraction",
        "enabled": True,
        "min_budget_irt": 1500000,
        "min_budget_usd": 20,
        "keywords": [
            "استخراج داده",
            "اسکرپ",
            "خزنده",
            "scraping",
            "crawler",
            "playwright",
            "selenium",
            "beautifulsoup",
            "وب اسکرپینگ",
        ],
    },
    "scripting": {
        "name": "Python Scripting & APIs",
        "enabled": True,
        "min_budget_irt": 1500000,
        "min_budget_usd": 20,
        "keywords": [
            "اسکریپت پایتون",
            "python script",
            "fastapi",
            "api",
            "requests",
            "sqlite",
            "پایتون",
            "python",
        ],
    },
    "formatting": {
        "name": "Document Formatting",
        "enabled": False,  # Disabled per specification
        "min_budget_irt": 500000,
        "min_budget_usd": 10,
        "keywords": [
            "صفحه آرایی",
            "فرمت بندی",
            "قالب بندی word",
            "word formatting",
        ],
    },
}

DEFAULT_ESTIMATED_HOURS: dict[str, float] = {
    "bots": 6.0,
    "automation": 5.0,
    "translation": 3.0,
    "excel": 2.5,
    "scraping": 4.0,
    "scripting": 4.0,
}


def normalize_text(text: Any) -> str:
    """Standardize Persian/Arabic characters, whitespace, and lowercase."""
    if not text or not isinstance(text, str):
        return ""
    normalized = (
        text.replace("ي", "ی")
        .replace("ك", "ک")
        .replace("‌", " ")
        .lower()
    )
    return " ".join(normalized.split())


def _parse_budget_val(val: Any) -> float | None:
    if val is None or val == "":
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def _word_matches(needle: str, haystack: str, is_multi: bool) -> bool:
    if not needle or not haystack:
        return False
    if is_multi:
        return needle in haystack
    # For single keywords, enforce word boundary to avoid substring collisions (e.g. 'بله' in 'دوبله')
    pattern = r"(?:\b|^)" + re.escape(needle) + r"(?:\b|$)"
    return bool(re.search(pattern, haystack, re.IGNORECASE))


def _calculate_scope_fit(
    title_norm: str,
    desc_norm: str,
    skills_norm: list[str],
    scope_cfg: dict[str, Any],
) -> float:
    """Calculate fit score [0.0 to 1.0] for a specific scope."""
    keywords = scope_cfg.get("keywords", [])
    if not keywords:
        return 0.0

    title_score = 0.0
    desc_score = 0.0
    skills_score = 0.0
    has_multi_word_title = False

    for kw in keywords:
        kw_norm = normalize_text(kw)
        if not kw_norm:
            continue
        is_multi = len(kw_norm.split()) >= 2

        if _word_matches(kw_norm, title_norm, is_multi):
            if is_multi:
                title_score += 0.50
                has_multi_word_title = True
            else:
                title_score += 0.35

        if _word_matches(kw_norm, desc_norm, is_multi):
            if is_multi:
                desc_score += 0.30
            else:
                desc_score += 0.20

        for skill in skills_norm:
            if _word_matches(kw_norm, skill, is_multi):
                skills_score += 0.25
                break

    if has_multi_word_title:
        title_score += 0.15

    raw_score = title_score + desc_score + skills_score
    return round(min(1.0, max(0.0, raw_score)), 2)


def evaluate_project(
    project: dict[str, Any],
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Evaluate a project for scam patterns, scope alignment, and ROI.

    Return contract:
    {
        "tier": "A" | "B" | "C",
        "fit_score": float,
        "scope": str | None,
        "is_scam": bool,
        "rejection_reason": str | None,
        "estimated_hours": float | None,
        "roi_score": float | None,
    }
    """
    if not isinstance(project, dict):
        return {
            "tier": "C",
            "fit_score": 0.0,
            "scope": None,
            "is_scam": False,
            "rejection_reason": "no_scope_match",
            "estimated_hours": None,
            "roi_score": None,
        }

    cfg = config or {}

    # 1. Normalize text inputs
    title_norm = normalize_text(project.get("title"))
    desc_norm = normalize_text(project.get("description"))
    combined_text = f"{title_norm} {desc_norm}"

    raw_skills = project.get("skills") or []
    skills_norm = [
        normalize_text(s) for s in raw_skills if isinstance(s, str)
    ]

    # 2. Scam Detection
    custom_blacklist = (
        (cfg.get("scam_filter") or {}).get("blacklist") or []
    )
    combined_blacklist = list(
        dict.fromkeys(DEFAULT_SCAM_BLACKLIST + custom_blacklist)
    )

    for term in combined_blacklist:
        term_norm = normalize_text(term)
        if term_norm and term_norm in combined_text:
            return {
                "tier": "C",
                "fit_score": 0.0,
                "scope": None,
                "is_scam": True,
                "rejection_reason": "scam_detected",
                "estimated_hours": None,
                "roi_score": None,
            }

    # 3. Scope Matching
    custom_scopes = cfg.get("scopes") or {}
    active_scopes: dict[str, dict[str, Any]] = {}
    all_scope_keys = set(DEFAULT_SCOPES.keys()) | set(custom_scopes.keys())

    for scope_key in all_scope_keys:
        base_cfg = DEFAULT_SCOPES.get(scope_key, {})
        override_cfg = custom_scopes.get(scope_key, {})
        merged_cfg = {**base_cfg, **override_cfg}
        if merged_cfg.get("enabled", True):
            active_scopes[scope_key] = merged_cfg

    best_scope: str | None = None
    best_score: float = 0.0

    for scope_name, scope_cfg in active_scopes.items():
        score = _calculate_scope_fit(
            title_norm, desc_norm, skills_norm, scope_cfg
        )
        if score > best_score:
            best_score = score
            best_scope = scope_name

    # Check minimum fit threshold
    if best_scope is None or best_score < 0.3:
        return {
            "tier": "C",
            "fit_score": best_score,
            "scope": None,
            "is_scam": False,
            "rejection_reason": "no_scope_match",
            "estimated_hours": None,
            "roi_score": None,
        }

    # 4. Budget & Floor Verification
    scope_cfg = active_scopes[best_scope]
    currency = str(project.get("currency") or "IRT").strip().upper()

    if currency in ("USD", "$"):
        default_usd = (
            20 if best_scope in ("bots", "automation", "scraping", "scripting") else 10
        )
        min_budget = float(scope_cfg.get("min_budget_usd", default_usd))
    elif currency in ("IRR", "RIAL", "RIALS"):
        default_irt = (
            1500000 if best_scope in ("bots", "automation", "scraping", "scripting") else 500000
        )
        min_budget = float(scope_cfg.get("min_budget_irt", default_irt)) * 10
    else:
        # Default IRT / TOMAN
        default_irt = (
            1500000 if best_scope in ("bots", "automation", "scraping", "scripting") else 500000
        )
        min_budget = float(scope_cfg.get("min_budget_irt", default_irt))

    b_min = _parse_budget_val(project.get("budget_min"))
    b_max = _parse_budget_val(project.get("budget_max"))

    if b_max is not None and b_min is not None:
        effective_budget = max(b_min, b_max)
    elif b_max is not None:
        effective_budget = b_max
    elif b_min is not None:
        effective_budget = b_min
    else:
        effective_budget = None

    estimated_hours = DEFAULT_ESTIMATED_HOURS.get(best_scope, 4.0)
    roi_score = (
        round(effective_budget / estimated_hours, 2)
        if (effective_budget is not None and estimated_hours > 0)
        else None
    )

    # Budget below minimum rejection
    if effective_budget is not None and effective_budget < min_budget:
        return {
            "tier": "C",
            "fit_score": best_score,
            "scope": best_scope,
            "is_scam": False,
            "rejection_reason": "budget_below_minimum",
            "estimated_hours": estimated_hours,
            "roi_score": roi_score,
        }

    # 5. Tier Assignment
    if best_score < 0.45:
        tier = "C"
        rejection_reason = "low_fit"
    elif best_score >= 0.75:
        tier = "A"
        rejection_reason = None
    else:
        tier = "B"
        rejection_reason = None

    return {
        "tier": tier,
        "fit_score": best_score,
        "scope": best_scope,
        "is_scam": False,
        "rejection_reason": rejection_reason,
        "estimated_hours": estimated_hours,
        "roi_score": roi_score,
    }


if __name__ == "__main__":
    test_proj = {
        "title": "ساخت ربات تلگرام ووکامرس",
        "description": "پایتون و تلگرام برای فروشگاه",
        "budget_min": 2500000,
        "currency": "IRT",
    }
    eval_res = evaluate_project(test_proj, {})
    assert eval_res["is_scam"] is False
    assert eval_res["scope"] == "bots"
    assert eval_res["tier"] == "A"
    assert eval_res["fit_score"] >= 0.75
    assert eval_res["estimated_hours"] == 6.0
    assert eval_res["roi_score"] is not None

    scam_proj = {
        "title": "تایپ",
        "description": "پرداخت اول 50 هزار تومان به عنوان بیعانه",
    }
    scam_res = evaluate_project(scam_proj, {})
    assert scam_res["is_scam"] is True
    assert scam_res["tier"] == "C"
    assert scam_res["rejection_reason"] == "scam_detected"
    print("All triage self-checks passed.")
