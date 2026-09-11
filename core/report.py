from datetime import datetime
import json
from pathlib import Path
import re
from typing import Any

# ponytail: Telegram legacy markdown over HTML/MarkdownV2; ceiling 4096 chars per message, upgrade to Telegram HTML or multi-message chunker if proposals grow large.
# ponytail: file-based markdown reports over database-backed dashboard; upgrade to SQLite/Web dashboard when historical query UI is needed.


def escape_telegram_markdown(text: Any) -> str:
    """Escape special characters for Telegram legacy Markdown.

    Escapes backslash first, then _, *, `, [, and ].
    """
    if text is None:
        return ""
    s = str(text)
    s = s.replace("\\", "\\\\")
    for char in ("_", "*", "`", "[", "]"):
        s = s.replace(char, f"\\{char}")
    return s


def _ensure_list(val: Any) -> list[str]:
    """Ensure value is returned as a list of strings."""
    if val is None:
        return []
    if isinstance(val, list):
        return [str(item).strip() for item in val if item is not None]
    if isinstance(val, str):
        val_str = val.strip()
        if val_str.startswith("[") and val_str.endswith("]"):
            try:
                parsed = json.loads(val_str)
                if isinstance(parsed, list):
                    return [str(item).strip() for item in parsed if item is not None]
            except Exception:
                pass
        if "\n" in val_str:
            return [line.strip().lstrip("•-*0123456789. ") for line in val_str.splitlines() if line.strip()]
        if val_str:
            return [val_str]
    return []


def _format_currency_amount(amount: Any, currency: str = "IRT") -> str:
    """Format numeric amounts with clean comma separators."""
    if amount is None or amount == "":
        return "توافقی"
    try:
        val = float(amount)
        if val.is_integer():
            return f"{int(val):,} {currency}"
        return f"{val:,.2f} {currency}"
    except (ValueError, TypeError):
        return f"{amount} {currency}".strip()


def _format_budget(b_min: Any, b_max: Any, currency: str = "IRT") -> str:
    """Format client budget range neatly."""
    if b_min is None and b_max is None:
        return "توافقی"

    c = str(currency or "IRT").strip().upper()
    min_str = _format_currency_amount(b_min, c) if b_min is not None else None
    max_str = _format_currency_amount(b_max, c) if b_max is not None else None

    if min_str and max_str:
        if b_min == b_max:
            return min_str
        return f"{min_str} تا {max_str}"
    if min_str:
        return f"حداقل {min_str}"
    return f"حداکثر {max_str}"


def _get_tracking_id(project: dict[str, Any]) -> str:
    """Extract standard tracking identifier from project dict."""
    raw_id = (
        project.get("id")
        or project.get("platform_id")
        or project.get("job_hash", "")[:8]
        or "N/A"
    )
    raw_str = str(raw_id).strip()
    return raw_str if raw_str.startswith("#") else f"#{raw_str}"


def format_telegram_message(project: dict[str, Any]) -> str:
    """Format an enriched project into a rich Telegram alert message.

    Structure:
    - Tracking ID & Title (linked if URL present)
    - Platform, Scope, Tier, Fit Score
    - Client Budget, Suggested Bid, Delivery Days
    - Tech Stack
    - Roadmap (numbered steps)
    - Proposal Draft
    """
    if not isinstance(project, dict):
        project = {}

    track_id = _get_tracking_id(project)
    raw_title = str(project.get("title") or "پروژه بدون عنوان").strip()
    escaped_title = escape_telegram_markdown(raw_title)

    raw_url = str(project.get("url") or "").strip()
    if raw_url.startswith(("http://", "https://")):
        safe_url = raw_url.replace(")", "%29").replace("(", "%28")
        title_block = f"📌 [{escaped_title}]({safe_url}) ({track_id})"
    else:
        title_block = f"📌 *{escaped_title}* ({track_id})"

    platform = escape_telegram_markdown(project.get("platform") or "نامشخص")
    scope = escape_telegram_markdown(project.get("scope") or "scripting")
    tier = str(project.get("tier") or "A").strip().upper()

    score = project.get("fit_score")
    score_str = f" ({float(score):.2f})" if isinstance(score, (int, float)) else ""
    meta_block = (
        f"🌐 *پلتفرم:* {platform} | 🎯 *اسکوپ:* {scope} | 🏆 *رده:* Tier {tier}{score_str}"
    )

    currency = str(project.get("currency") or "IRT").strip().upper()
    budget_str = _format_budget(project.get("budget_min"), project.get("budget_max"), currency)
    budget_line = f"💰 *بودجه کارفرما:* {escape_telegram_markdown(budget_str)}"

    suggested_bid = project.get("suggested_bid")
    delivery_days = project.get("delivery_days")
    bid_parts: list[str] = []
    if suggested_bid is not None:
        bid_parts.append(f"💡 *پیشنهاد ما:* {_format_currency_amount(suggested_bid, currency)}")
    if delivery_days is not None:
        bid_parts.append(f"⏱ *تحویل:* {delivery_days} روز کاری")
    pricing_line = " | ".join(bid_parts) if bid_parts else ""

    budget_and_bid = f"{budget_line}\n{pricing_line}".strip()

    tech_stack = _ensure_list(project.get("tech_stack"))
    if tech_stack:
        stack_items = "\n".join(f"• {escape_telegram_markdown(item)}" for item in tech_stack)
        tech_block = f"🛠 *پشته فنی:*\n{stack_items}"
    else:
        tech_block = ""

    roadmap = _ensure_list(project.get("roadmap"))
    if roadmap:
        steps: list[str] = []
        for i, step in enumerate(roadmap, 1):
            clean = str(step).strip()
            if re.match(r"^(گام\s*\d+|step\s*\d+|\d+[\.\-\)])", clean, re.IGNORECASE):
                steps.append(escape_telegram_markdown(clean))
            else:
                steps.append(f"{i}. {escape_telegram_markdown(clean)}")
        roadmap_block = "📋 *رودمپ اجرا:*\n" + "\n".join(steps)
    else:
        roadmap_block = ""

    proposal = str(project.get("proposal") or "").strip()
    if proposal:
        proposal_block = f"📝 *پیش‌نویس پیشنهاد:*\n{escape_telegram_markdown(proposal)}"
    else:
        proposal_block = ""

    sections = [
        title_block,
        meta_block,
        budget_and_bid,
        tech_block,
        roadmap_block,
        proposal_block,
    ]

    message = "\n\n".join(section for section in sections if section).strip()

    # Telegram hard limit is 4096 UTF-8 characters; cap safely
    if len(message) > 4000:
        message = message[:3950] + "\n\n... (کوتاه‌شده به دلیل محدودیت طول پیام)"

    return message


def build_markdown_report(
    projects: list[dict[str, Any]], output_path: str | None = None
) -> str:
    """Generate daily Markdown report summarizing scanned projects across tiers.

    Saves to output_path (default reports/YYYY-MM-DD.md) and returns markdown string.
    """
    if not isinstance(projects, list):
        projects = []

    today_str = datetime.now().strftime("%Y-%m-%d")
    now_time = datetime.now().strftime("%Y-%m-%d %H:%M")

    tier_a: list[dict[str, Any]] = []
    tier_b: list[dict[str, Any]] = []
    tier_c: list[dict[str, Any]] = []

    scope_counts: dict[str, int] = {}
    platform_counts: dict[str, int] = {}

    for p in projects:
        if not isinstance(p, dict):
            continue
        tier = str(p.get("tier") or "C").strip().upper()
        if tier == "A":
            tier_a.append(p)
        elif tier == "B":
            tier_b.append(p)
        else:
            tier_c.append(p)

        sc = str(p.get("scope") or "scripting").strip()
        scope_counts[sc] = scope_counts.get(sc, 0) + 1

        pl = str(p.get("platform") or "other").strip()
        platform_counts[pl] = platform_counts.get(pl, 0) + 1

    lines: list[str] = [
        f"# گزارش پایش و شکار هوشمند پروژه (Job Hunter Report)",
        f"**تاریخ گزارش:** {today_str}  ",
        f"**زمان استخراج:** {now_time}  ",
        "",
        "---",
        "",
        "## ۱. خلاصه آمار و عملکرد (Summary Metrics)",
        "",
        "| شاخص | مقدار |",
        "| :--- | :---: |",
        f"| مجموع کل پروژه‌های اسکن‌شده | **{len(projects)}** |",
        f"| رده A (ارزش بالا / اقدام فوری) | **{len(tier_a)}** |",
        f"| رده B (ارزش متوسط) | **{len(tier_b)}** |",
        f"| رده C (رد شده / کم‌ارزش / اسکم) | **{len(tier_c)}** |",
        "",
        "### تفکیک بر اساس حوزه تخصصی (Scopes)",
        "| حوزه تخصصی | تعداد پروژه‌ها |",
        "| :--- | :---: |",
    ]

    if scope_counts:
        for sc, cnt in sorted(scope_counts.items(), key=lambda x: -x[1]):
            lines.append(f"| `{sc}` | {cnt} |")
    else:
        lines.append("| هیچ حوزه‌ای یافت نشد | 0 |")

    lines.extend([
        "",
        "### تفکیک بر اساس پلتفرم (Platforms)",
        "| پلتفرم | تعداد پروژه‌ها |",
        "| :--- | :---: |",
    ])

    if platform_counts:
        for pl, cnt in sorted(platform_counts.items(), key=lambda x: -x[1]):
            lines.append(f"| {pl} | {cnt} |")
    else:
        lines.append("| بدون پلتفرم | 0 |")

    lines.extend([
        "",
        "---",
        "",
        "## ۲. پروژه‌های رده A (Tier A - اولویت اقدام و ارسال پروپوزال)",
        "",
    ])

    if tier_a:
        for p in tier_a:
            track_id = _get_tracking_id(p)
            title = str(p.get("title") or "پروژه بدون عنوان").strip()
            url = str(p.get("url") or "").strip()
            title_header = f"[{title}]({url})" if url.startswith(("http://", "https://")) else title

            platform = p.get("platform") or "نامشخص"
            scope = p.get("scope") or "scripting"
            fit_score = p.get("fit_score")
            score_val = f"{float(fit_score):.2f}" if isinstance(fit_score, (int, float)) else "N/A"

            currency = str(p.get("currency") or "IRT").strip().upper()
            budget_str = _format_budget(p.get("budget_min"), p.get("budget_max"), currency)
            suggested_bid = p.get("suggested_bid")
            bid_str = _format_currency_amount(suggested_bid, currency) if suggested_bid is not None else "محاسبه‌نشده"
            delivery_days = p.get("delivery_days")
            days_str = f"{delivery_days} روز" if delivery_days is not None else "توافقی"

            lines.extend([
                f"### {track_id} - {title_header}",
                "",
                f"- **پلتفرم:** `{platform}` | **اسکوپ:** `{scope}` | **امتیاز تطابق (Fit Score):** `{score_val}`",
                f"- **بودجه کارفرما:** {budget_str} | **پیشنهاد ما:** **{bid_str}** ({days_str})",
            ])

            desc = str(p.get("description") or "").strip()
            if desc:
                clean_desc = desc[:300] + "..." if len(desc) > 300 else desc
                lines.extend([
                    f"- **توضیحات:** *{clean_desc}*",
                ])

            tech_stack = _ensure_list(p.get("tech_stack"))
            if tech_stack:
                lines.extend([
                    "",
                    "#### 🛠 پشته نرم‌افزاری",
                ])
                for t in tech_stack:
                    lines.append(f"- {t}")

            roadmap = _ensure_list(p.get("roadmap"))
            if roadmap:
                lines.extend([
                    "",
                    "#### 📋 نقشه راه و مراحل اجرا (Roadmap)",
                ])
                for i, step in enumerate(roadmap, 1):
                    clean_s = str(step).strip()
                    if re.match(r"^(گام\s*\d+|step\s*\d+|\d+[\.\-\)])", clean_s, re.IGNORECASE):
                        lines.append(f"- {clean_s}")
                    else:
                        lines.append(f"{i}. {clean_s}")

            proposal = str(p.get("proposal") or "").strip()
            if proposal:
                lines.extend([
                    "",
                    "#### 📝 پیش‌نویس پروپوزال اختصاصی",
                    "```text",
                    proposal,
                    "```",
                ])

            lines.extend(["", "---", ""])
    else:
        lines.extend([
            "*هیچ پروژه‌ای با رتبه Tier A در این دوره یافت نشد.*",
            "",
        ])

    lines.extend([
        "## ۳. پروژه‌های رده B (Tier B - ارزش متوسط / اولویت دوم)",
        "",
    ])

    if tier_b:
        lines.extend([
            "| شناسه | عنوان پروژه | پلتفرم | اسکوپ | بودجه کارفرما | پیشنهاد ما | تحویل | امتیاز |",
            "| :---: | :--- | :---: | :---: | :---: | :---: | :---: | :---: |",
        ])
        for p in tier_b:
            track_id = _get_tracking_id(p)
            title = str(p.get("title") or "پروژه بدون عنوان").replace("|", "-").strip()
            url = str(p.get("url") or "").strip()
            title_cell = f"[{title}]({url})" if url.startswith(("http://", "https://")) else title
            platform = str(p.get("platform") or "-").replace("|", "-")
            scope = str(p.get("scope") or "-").replace("|", "-")
            currency = str(p.get("currency") or "IRT").strip().upper()
            budget = _format_budget(p.get("budget_min"), p.get("budget_max"), currency).replace("|", "-")
            suggested_bid = p.get("suggested_bid")
            bid_cell = _format_currency_amount(suggested_bid, currency).replace("|", "-") if suggested_bid is not None else "-"
            delivery_days = p.get("delivery_days")
            days_cell = f"{delivery_days} روز" if delivery_days is not None else "-"
            fit_score = p.get("fit_score")
            score_cell = f"{float(fit_score):.2f}" if isinstance(fit_score, (int, float)) else "-"

            lines.append(
                f"| {track_id} | {title_cell} | {platform} | {scope} | {budget} | {bid_cell} | {days_cell} | {score_cell} |"
            )
        lines.append("")
    else:
        lines.extend([
            "*هیچ پروژه‌ای در رده Tier B ثبت نشد.*",
            "",
        ])

    lines.extend([
        "## ۴. پروژه‌های رد شده (Tier C / Rejections)",
        "",
    ])

    if tier_c:
        lines.extend([
            "| شناسه | عنوان پروژه | پلتفرم | دلیل رد (Rejection Reason) |",
            "| :---: | :--- | :---: | :--- |",
        ])
        for p in tier_c:
            track_id = _get_tracking_id(p)
            title = str(p.get("title") or "پروژه بدون عنوان").replace("|", "-").strip()
            platform = str(p.get("platform") or "-").replace("|", "-")
            reason = str(p.get("rejection_reason") or "بودجه زیر کف / عدم تطابق اسکوپ / ریسک اسکم").replace("|", "-")
            lines.append(f"| {track_id} | {title} | {platform} | {reason} |")
        lines.append("")
    else:
        lines.extend([
            "*هیچ پروژه رد شده‌ای در این دوره ثبت نشد.*",
            "",
        ])

    report_content = "\n".join(lines).strip() + "\n"

    target_path = Path(output_path) if output_path else Path(f"reports/{today_str}.md")
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_text(report_content, encoding="utf-8")

    return report_content


if __name__ == "__main__":
    sample_proj = {
        "id": 105,
        "title": "طراحی ربات تلگرام",
        "url": "https://ponisha.ir/project/105",
        "platform": "ponisha",
        "scope": "bots",
        "budget_min": 2000000,
        "budget_max": 3000000,
        "currency": "IRT",
        "tier": "A",
        "suggested_bid": 2650000,
        "delivery_days": 3,
        "roadmap": ["اتصال به API", "طراحی منوها", "تست نهایی"],
        "tech_stack": ["Python", "aiogram"],
        "proposal": "سلام، پروژه با aiogram قابل انجام است.",
    }
    msg = format_telegram_message(sample_proj)
    assert "#105" in msg
    assert "رودمپ" in msg
    assert "پیشنهاد" in msg

    md = build_markdown_report([sample_proj], output_path="reports/test_run.md")
    assert "گزارش پایش و شکار هوشمند پروژه" in md
    assert "#105" in md
    assert "Tier A" in md
    print("All report self-checks passed.")
