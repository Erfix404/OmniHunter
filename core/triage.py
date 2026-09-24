import re
from typing import Any


def _resolve_triage_profile(profile: Any | None) -> Any | None:
    """Lazily resolve a profile object without hard-importing core.profile."""
    if profile is None:
        return None
    if hasattr(profile, "is_scope_declined") and hasattr(profile, "get_min_budget"):
        return profile
    if isinstance(profile, dict):
        try:
            from core.profile import FreelancerProfile

            return FreelancerProfile(data=profile)
        except Exception:
            return None
    return None

# ponytail: heuristic keyword scoring over LLM classifier; ceiling ~90% accuracy on ambiguous briefs, upgrade to Claude Haiku/Sonnet triage when budget allows.
# ponytail: static baseline hours per scope over task breakdown estimation; upgrade to LLM scope estimator when multi-feature tasks are scanned.

# Claude leverage tiers by scope: how much Claude accelerates delivery
CLAUDE_LEVERAGE: dict[str, int] = {
    "bots": 9,        # aiogram, telethon, pyrogram — high Claude leverage
    "automation": 9,  # webhooks, n8n scripting, bots
    "scraping": 9,    # playwright, beautifulsoup — high Claude leverage
    "scripting": 9,   # fastapi, sqlite, python APIs
    "excel": 7,       # pandas, openpyxl — general python
    "translation": 5, # text work, less code-centric
}

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

DEFAULT_RED_FLAGS: list[str] = [
    "تست رایگان",
    "نمونه رایگان",
    "پروژه تستی رایگان",
    "free test",
    "free sample",
    "کار دو ساعته",
    "کار ساده و سریع",
    "کار چند دقیقه ای",
    "خیلی راحته",
    "کار آسونیه",
    "two hour job",
    "very easy job",
    "پشتیبانی نامحدود",
    "پشتیبانی دائمی رایگان",
    "unlimited support",
    "تغییرات جزئی حین کار",
    "تغییرات مکرر",
    "تغییرات بعد از تحویل",
    "ارزان ترین قیمت",
    "کمترین هزینه با بالاترین کیفیت",
    "lowest budget",
    "cheapest",
    "تسویه بعد از تست یک ماهه",
]

_RISK_ORDER: dict[str, int] = {"low": 0, "medium": 1, "high": 2}


def _compute_arbitrage(
    estimated_hours: float | None,
    claude_leverage: int | None,
    effective_budget: float | None,
) -> tuple[float | None, float | None]:
    """Calculate agent_hours and arbitrage_score (effective hourly yield).

    agent_hours = max(0.5, round(estimated_hours * max(0.15, 1.0 - (leverage-1)*0.09), 2))
    arbitrage_score = round(effective_budget / agent_hours, 2) when computable.
    """
    if estimated_hours is None:
        return None, None
    try:
        eh = float(estimated_hours)
    except (ValueError, TypeError):
        return None, None
    try:
        cl = int(claude_leverage) if claude_leverage is not None else 1
    except (ValueError, TypeError):
        cl = 1
    factor = max(0.15, (1.0 - (cl - 1) * 0.09))
    agent_hours = max(0.5, round(eh * factor, 2))
    arbitrage_score: float | None = None
    try:
        if effective_budget is not None and agent_hours > 0:
            arbitrage_score = round(float(effective_budget) / agent_hours, 2)
    except (ValueError, TypeError, ZeroDivisionError):
        arbitrage_score = None
    return agent_hours, arbitrage_score


def detect_red_flags(title_norm: str, desc_norm: str) -> list[str]:
    """Return the subset of DEFAULT_RED_FLAGS found in normalized title/description."""
    combined = f"{title_norm or ''} {desc_norm or ''}".strip()
    if not combined:
        return []
    matched: list[str] = []
    for flag in DEFAULT_RED_FLAGS:
        flag_norm = normalize_text(flag)
        if flag_norm and flag_norm in combined:
            matched.append(flag)
    return matched


def assess_client_risk(red_flags: list[str] | None) -> str:
    """Map red-flag count to client risk level."""
    count = len(red_flags or [])
    if count >= 2:
        return "high"
    if count == 1:
        return "medium"
    return "low"

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


def _compute_win_probability(fit_score: float, project: dict[str, Any]) -> float:
    """Calculate win probability based on fit score and competition level."""
    proposals_count = project.get("proposals_count") or project.get("bid_count")
    if proposals_count is None:
        proposals_count = 5
    else:
        try:
            proposals_count = int(proposals_count)
        except (ValueError, TypeError):
            proposals_count = 5
    competition_penalty = min(0.6, proposals_count * 0.025)
    raw = fit_score * (1.0 - competition_penalty)
    return round(max(0.10, min(0.95, raw)), 2)


def _compute_difficulty(fit_score: float, estimated_hours: float | None) -> tuple[str, int]:
    """Return (difficulty_label, difficulty_score) based on fit and hours."""
    hours = estimated_hours or 0.0
    if fit_score >= 0.7 and hours <= 4:
        return "آسان", 1
    elif hours > 8 or fit_score < 0.4:
        return "پیچیده", 5
    elif 4 < hours <= 8:
        return "متوسط", 3
    else:
        # hours <= 4 but fit_score < 0.7 and >= 0.4
        return "متوسط", 3


def _compute_pricing_strategy(win_probability: float) -> str:
    """Determine pricing strategy from win probability."""
    if win_probability < 0.4:
        return "competitive_entry"
    elif win_probability > 0.75:
        return "value_driven"
    else:
        return "sweet_spot"


def evaluate_project(
    project: dict[str, Any],
    config: dict[str, Any] | None = None,
    profile: Any | None = None,
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
        "client_risk": "low" | "medium" | "high",
        "red_flags": list[str],
    }
    """
    _empty_risk_flags: list[str] = []
    if not isinstance(project, dict):
        _ah, _as = _compute_arbitrage(None, 1, None)
        return {
            "tier": "C",
            "fit_score": 0.0,
            "scope": None,
            "is_scam": False,
            "rejection_reason": "no_scope_match",
            "estimated_hours": None,
            "roi_score": None,
            "agent_hours": _ah,
            "arbitrage_score": _as,
            "claude_leverage": 1,
            "difficulty": "پیچیده",
            "difficulty_score": 5,
            "win_probability": 0.10,
            "pricing_strategy": "competitive_entry",
            "client_risk": "low",
            "red_flags": _empty_risk_flags,
        }

    cfg = config or {}

    # 1. Normalize text inputs
    title_norm = normalize_text(project.get("title"))
    desc_norm = normalize_text(project.get("description"))
    combined_text = f"{title_norm} {desc_norm}"

    # 1b. Client risk & red-flag vetting (toxic-client phrases)
    red_flags = detect_red_flags(title_norm, desc_norm)
    client_risk = assess_client_risk(red_flags)

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
            _s_ah, _s_as = _compute_arbitrage(None, 1, None)
            return {
                "tier": "C",
                "fit_score": 0.0,
                "scope": None,
                "is_scam": True,
                "rejection_reason": "scam_detected",
                "estimated_hours": None,
                "roi_score": None,
                "agent_hours": _s_ah,
                "arbitrage_score": _s_as,
                "claude_leverage": 1,
                "difficulty": "پیچیده",
                "difficulty_score": 5,
                "win_probability": 0.10,
                "pricing_strategy": "competitive_entry",
                "client_risk": client_risk,
                "red_flags": red_flags,
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
        _n_ah, _n_as = _compute_arbitrage(None, 1, None)
        return {
            "tier": "C",
            "fit_score": best_score,
            "scope": None,
            "is_scam": False,
            "rejection_reason": "no_scope_match",
            "estimated_hours": None,
            "roi_score": None,
            "agent_hours": _n_ah,
            "arbitrage_score": _n_as,
            "claude_leverage": 1,
            "difficulty": "پیچیده",
            "difficulty_score": 5,
            "win_probability": 0.10,
            "pricing_strategy": "competitive_entry",
            "client_risk": client_risk,
            "red_flags": red_flags,
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

    # Profile personal floor: the profile's minimum acts as a custom floor
    # only when it is specified and higher than the scope floor.
    _prof = _resolve_triage_profile(profile)
    if _prof is not None:
        try:
            profile_floor = _prof.get_min_budget(currency)
        except Exception:
            profile_floor = None
        if profile_floor is not None and profile_floor > min_budget:
            min_budget = float(profile_floor)

        if _prof.is_scope_declined(best_scope):
            _cl = CLAUDE_LEVERAGE.get(best_scope, 5)
            _wp = _compute_win_probability(best_score, project)
            _est = DEFAULT_ESTIMATED_HOURS.get(best_scope, 4.0)
            _diff, _ds = _compute_difficulty(best_score, _est)
            _ps = _compute_pricing_strategy(_wp)
            _d_ah, _d_as = _compute_arbitrage(_est, _cl, None)
            return {
                "tier": "C",
                "fit_score": best_score,
                "scope": best_scope,
                "is_scam": False,
                "rejection_reason": "scope_declined_by_profile",
                "estimated_hours": _est,
                "roi_score": None,
                "agent_hours": _d_ah,
                "arbitrage_score": _d_as,
                "claude_leverage": _cl,
                "difficulty": _diff,
                "difficulty_score": _ds,
                "win_probability": _wp,
                "pricing_strategy": _ps,
                "client_risk": client_risk,
                "red_flags": red_flags,
            }

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
        _cl = CLAUDE_LEVERAGE.get(best_scope, 5)
        _wp = _compute_win_probability(best_score, project)
        _diff, _ds = _compute_difficulty(best_score, estimated_hours)
        _ps = _compute_pricing_strategy(_wp)
        _b_ah, _b_as = _compute_arbitrage(estimated_hours, _cl, effective_budget)
        return {
            "tier": "C",
            "fit_score": best_score,
            "scope": best_scope,
            "is_scam": False,
            "rejection_reason": "budget_below_minimum",
            "estimated_hours": estimated_hours,
            "roi_score": roi_score,
            "agent_hours": _b_ah,
            "arbitrage_score": _b_as,
            "claude_leverage": _cl,
            "difficulty": _diff,
            "difficulty_score": _ds,
            "win_probability": _wp,
            "pricing_strategy": _ps,
            "client_risk": client_risk,
            "red_flags": red_flags,
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

    # 5b. Risk impact: high-risk clients are downgraded to protect the freelancer.
    if client_risk == "high":
        if tier == "A":
            tier = "B"
            rejection_reason = rejection_reason or "high_client_risk"
        elif tier == "B":
            tier = "C"
            rejection_reason = rejection_reason or "high_client_risk"
        else:
            rejection_reason = rejection_reason or "high_client_risk"

    # 6. New enrichment fields
    claude_leverage = CLAUDE_LEVERAGE.get(best_scope, 5)
    win_probability = _compute_win_probability(best_score, project)
    difficulty, difficulty_score = _compute_difficulty(best_score, estimated_hours)
    pricing_strategy = _compute_pricing_strategy(win_probability)
    agent_hours, arbitrage_score = _compute_arbitrage(
        estimated_hours, claude_leverage, effective_budget
    )

    return {
        "tier": tier,
        "fit_score": best_score,
        "scope": best_scope,
        "is_scam": False,
        "rejection_reason": rejection_reason,
        "estimated_hours": estimated_hours,
        "roi_score": roi_score,
        "agent_hours": agent_hours,
        "arbitrage_score": arbitrage_score,
        "claude_leverage": claude_leverage,
        "difficulty": difficulty,
        "difficulty_score": difficulty_score,
        "win_probability": win_probability,
        "pricing_strategy": pricing_strategy,
        "client_risk": client_risk,
        "red_flags": red_flags,
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
