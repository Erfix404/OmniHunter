import argparse
from datetime import datetime
import logging
import os
from pathlib import Path
import sys
import time
from typing import Any
import yaml

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
if hasattr(sys.stderr, "reconfigure"):
    try:
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from core.architect import generate_architecture
from core.auth_helper import interactive_login
from core.db import DB
from core.form_filler import fill_application
from core.report import build_markdown_report
from core.scrapers.freelancer import FreelancerScraper
from core.scrapers.parscoders import ParscodersScraper
from core.scrapers.ponisha import PonishaScraper
from core.triage import evaluate_project
from interfaces.telegram_bot import poll_updates, send_project_alert

logger = logging.getLogger(__name__)

# ponytail: argparse CLI over Click/Typer; stdlib keeps installation zero-dependency.
# ponytail: polling loop over Telegram webhook daemon; avoids setting up public SSL endpoint for local hunter.

MOCK_PROJECTS: list[dict[str, Any]] = [
    {
        "platform": "ponisha",
        "platform_id": "mock_1",
        "job_hash": "ponisha_mock_1",
        "title": "طراحی و ساخت ربات تلگرام فروشگاهی با پایتون",
        "url": "https://ponisha.ir/project/mock_1",
        "budget_min": 3000000,
        "budget_max": 6000000,
        "currency": "IRT",
        "description": "نیاز به پیاده‌سازی ربات تلگرام با فریمورک aiogram متصل به دیتابیس و درگاه پرداخت.",
        "skills": ["Python", "Telegram Bot", "aiogram"],
    },
    {
        "platform": "parscoders",
        "platform_id": "mock_2",
        "job_hash": "parscoders_mock_2",
        "title": "اسکریپت اتوماسیون فرایندها و وب‌هوک FastAPI",
        "url": "https://parscoders.com/project/mock_2",
        "budget_min": 2500000,
        "budget_max": 4500000,
        "currency": "IRT",
        "description": "پیاده‌سازی اتوماسیون n8n و وب هوک با FastAPI و دیتابیس سبک SQLite.",
        "skills": ["Python", "FastAPI", "Automation", "SQLite"],
    },
    {
        "platform": "freelancer",
        "platform_id": "mock_3",
        "job_hash": "freelancer_mock_3",
        "title": "Python Web Scraping Pipeline with Playwright",
        "url": "https://www.freelancer.com/projects/mock_3",
        "budget_min": 50,
        "budget_max": 150,
        "currency": "USD",
        "description": "Need automated web scraping script using Playwright or BeautifulSoup for data extraction.",
        "skills": ["Python", "Web Scraping", "Playwright"],
    },
    {
        "platform": "ponisha",
        "platform_id": "mock_4",
        "job_hash": "ponisha_mock_4",
        "title": "تایپ و ترجمه متون - پرداخت بیعانه الزامی است",
        "url": "https://ponisha.ir/project/mock_4",
        "budget_min": 5000000,
        "budget_max": 10000000,
        "currency": "IRT",
        "description": "پروژه فوری، لطفاً توجه کنید واریز بیعانه و کارمزد اولیه قبل از تحویل فایل الزامی است.",
        "skills": ["تایپ"],
    },
]


def _load_config(config_path: str = "config.yaml") -> dict[str, Any]:
    """Safely load project configuration."""
    path = Path(config_path)
    if not path.exists():
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
            return data if isinstance(data, dict) else {}
    except Exception as e:
        logger.warning(f"Could not load config file: {e}")
        return {}


def build_parser() -> argparse.ArgumentParser:
    """Construct command-line interface argument parser."""
    parser = argparse.ArgumentParser(
        prog="hunter",
        description="OmniHunter: Intelligent Freelance Job Hunting & Automation Engine",
    )
    subparsers = parser.add_subparsers(dest="command", help="Available subcommands")

    # scan
    scan_parser = subparsers.add_parser("scan", help="Scan platforms for new projects")
    scan_parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Evaluate projects without saving to database or notifying",
    )
    scan_parser.add_argument(
        "--mock",
        action="store_true",
        default=False,
        help="Use built-in mock projects instead of live scraping",
    )
    scan_parser.add_argument(
        "--platform",
        type=str,
        default=None,
        help="Limit scan to specific platform (ponisha, parscoders, freelancer)",
    )
    scan_parser.add_argument(
        "--notify",
        action="store_true",
        default=False,
        help="Send Telegram alerts for Tier A projects",
    )

    # list
    list_parser = subparsers.add_parser("list", help="List stored projects")
    list_parser.add_argument(
        "--tier",
        choices=["A", "B", "C", "a", "b", "c"],
        default=None,
        help="Filter by tier",
    )
    list_parser.add_argument(
        "--status",
        choices=["new", "evaluated", "applied", "rejected"],
        default=None,
        help="Filter by application status",
    )
    list_parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Limit maximum number of returned projects",
    )

    # apply
    apply_parser = subparsers.add_parser("apply", help="Open browser and populate proposal")
    apply_parser.add_argument("job_id", help="Target project ID or job hash")
    apply_parser.add_argument(
        "--dry-run",
        dest="dry_run",
        action="store_true",
        default=True,
        help="Fill form without submitting (default: True)",
    )
    apply_parser.add_argument(
        "--submit",
        dest="dry_run",
        action="store_false",
        help="Submit proposal to platform (disables dry-run)",
    )
    apply_parser.add_argument(
        "--headless",
        action="store_true",
        default=False,
        help="Run browser in headless mode",
    )

    # auth
    auth_parser = subparsers.add_parser("auth", help="Interactive login for platform sessions")
    auth_parser.add_argument("platform", help="Target platform (ponisha, parscoders, freelancer)")
    auth_parser.add_argument(
        "--headless",
        action="store_true",
        default=False,
        help="Run auth browser in headless mode",
    )

    # bot
    bot_parser = subparsers.add_parser("bot", help="Run Telegram bot listener")
    bot_parser.add_argument(
        "--once",
        action="store_true",
        default=False,
        help="Poll Telegram updates once and exit",
    )

    return parser


def run_scan(
    args: argparse.Namespace,
    config: dict[str, Any] | None = None,
    db: DB | None = None,
) -> list[dict[str, Any]]:
    """Execute end-to-end scanning pipeline."""
    cfg = config if config is not None else _load_config()

    if db is None:
        db_path = cfg.get("database", {}).get("path", "data/hunter.db")
        db = DB(db_path)
        db.init_schema()

    raw_projects: list[dict[str, Any]] = []

    if getattr(args, "mock", False):
        raw_projects = [dict(p) for p in MOCK_PROJECTS]
    else:
        target_platform = getattr(args, "platform", None)
        plat_cfgs = cfg.get("platforms", {})

        scrapers_to_run: list[Any] = []
        if target_platform:
            platforms = [target_platform.lower()]
        else:
            platforms = [p for p, pcfg in plat_cfgs.items() if pcfg.get("enabled", True)]
            if not platforms:
                platforms = ["ponisha", "parscoders", "freelancer"]

        for plat in platforms:
            delay = plat_cfgs.get(plat, {}).get("rate_limit_delay_sec", 2.0)
            if plat == "ponisha":
                scrapers_to_run.append(PonishaScraper(rate_limit_delay_sec=delay))
            elif plat == "parscoders":
                scrapers_to_run.append(ParscodersScraper(rate_limit_delay_sec=delay))
            elif plat == "freelancer":
                scrapers_to_run.append(FreelancerScraper(rate_limit_delay_sec=delay))

        for scraper in scrapers_to_run:
            try:
                fetched = scraper.fetch_projects()
                raw_projects.extend(fetched)
            except Exception as e:
                logger.error(f"Scraper error: {e}")

    # Deduplicate via DB is_seen
    unseen_projects: list[dict[str, Any]] = []
    for p in raw_projects:
        j_hash = p.get("job_hash", "")
        if j_hash and not db.is_seen(j_hash):
            unseen_projects.append(p)

    processed_projects: list[dict[str, Any]] = []

    # Triage and Architect
    for p in unseen_projects:
        triage_info = evaluate_project(p, config=cfg)
        p.update(triage_info)

        if not p.get("is_scam") and p.get("tier") in ("A", "B"):
            arch_info = generate_architecture(p, config=cfg)
            p.update(arch_info)

        if not getattr(args, "dry_run", False):
            db.save_project(p)
            saved = db.get_project(p.get("job_hash", ""))
            if saved:
                p["id"] = saved.get("id")

        processed_projects.append(p)

    # Markdown daily report
    reports_dir = cfg.get("reports", {}).get("directory", "reports")
    today_str = datetime.now().strftime("%Y-%m-%d")
    report_file = f"{reports_dir}/{today_str}.md"
    try:
        build_markdown_report(processed_projects, output_path=report_file)
    except Exception as e:
        logger.warning(f"Could not write daily report: {e}")

    # Telegram notification
    if getattr(args, "notify", False) and not getattr(args, "dry_run", False):
        tg_cfg = cfg.get("telegram", {})
        token = os.getenv("TELEGRAM_BOT_TOKEN") or tg_cfg.get("bot_token")
        chat_id = os.getenv("TELEGRAM_CHAT_ID") or tg_cfg.get("chat_id")
        notify_tiers = tg_cfg.get("notify_tiers", ["A"])

        if token and chat_id:
            for p in processed_projects:
                if p.get("tier") in notify_tiers and not p.get("is_scam"):
                    send_project_alert(p, token=token, chat_id=chat_id)

    print(f"Scan complete: {len(processed_projects)} new projects processed.")
    return processed_projects


def run_list(
    args: argparse.Namespace,
    db: DB | None = None,
) -> list[dict[str, Any]]:
    """Fetch and display projects from database."""
    if db is None:
        cfg = _load_config()
        db_path = cfg.get("database", {}).get("path", "data/hunter.db")
        db = DB(db_path)
        db.init_schema()

    tier = getattr(args, "tier", None)
    if tier:
        tier = tier.upper()
    status = getattr(args, "status", None)
    limit = getattr(args, "limit", None)

    projects = db.list_projects(tier=tier, status=status)
    if limit and limit > 0:
        projects = projects[:limit]

    print(f"\n--- Stored Projects ({len(projects)}) ---")
    if not projects:
        print("No projects found matching criteria.")
        return []

    print(
        f"{'ID':<6} | {'Tier':<4} | {'Platform':<11} | {'Status':<9} | {'Scope':<12} | {'Title'}"
    )
    print("-" * 75)
    for p in projects:
        p_id = str(p.get("id") or "-")
        p_tier = str(p.get("tier") or "-")
        p_plat = str(p.get("platform") or "-")
        p_stat = str(p.get("status") or "-")
        p_scope = str(p.get("scope") or "-")
        p_title = str(p.get("title") or "")[:35]
        print(
            f"{p_id:<6} | {p_tier:<4} | {p_plat:<11} | {p_stat:<9} | {p_scope:<12} | {p_title}"
        )

    return projects


def run_apply(
    args: argparse.Namespace,
    db: DB | None = None,
) -> dict[str, Any]:
    """Retrieve project and populate application form with Playwright."""
    if db is None:
        cfg = _load_config()
        db_path = cfg.get("database", {}).get("path", "data/hunter.db")
        db = DB(db_path)
        db.init_schema()

    job_id = args.job_id
    project = db.get_project(job_id)
    if not project:
        print(f"Error: Project '{job_id}' not found in database.")
        return {"status": "error", "message": f"Project '{job_id}' not found"}

    dry_run = getattr(args, "dry_run", True)
    headless = getattr(args, "headless", False)

    print(
        f"Applying to project #{project.get('id')} [{project.get('platform')}]: {project.get('title')}"
    )
    print(f"Mode: {'DRY RUN (preview only)' if dry_run else 'SUBMIT (live submission)'}")

    res = fill_application(project, dry_run=dry_run, headless=headless)

    if not dry_run and (res.get("submitted") or res.get("status") == "success"):
        db.update_status(project["id"], "applied")
        db.save_application(
            {
                "project_id": project["id"],
                "bid_amount": project.get("suggested_bid"),
                "delivery_days": project.get("delivery_days"),
                "proposal_text": project.get("proposal"),
                "status": "submitted",
            }
        )
        print("Application submitted and recorded in database.")
    elif res.get("status") == "success":
        print("Form filled successfully in preview mode (dry-run).")
    else:
        print(f"Form filler result: {res.get('status')} - {res.get('details')}")

    return res


def run_auth(args: argparse.Namespace) -> Any:
    """Launch browser for user authentication and save platform session."""
    platform = args.platform
    headless = getattr(args, "headless", False)
    print(f"Initiating authentication for {platform}...")
    session_path = interactive_login(platform=platform, headless=headless)
    print(f"Session saved at: {session_path}")
    return session_path


def run_bot(
    args: argparse.Namespace,
    config: dict[str, Any] | None = None,
    db: DB | None = None,
) -> list[dict[str, Any]]:
    """Run Telegram bot interaction listener."""
    cfg = config if config is not None else _load_config()
    if db is None:
        db_path = cfg.get("database", {}).get("path", "data/hunter.db")
        db = DB(db_path)
        db.init_schema()

    token = os.getenv("TELEGRAM_BOT_TOKEN") or cfg.get("telegram", {}).get("bot_token")
    if not token:
        print("Error: TELEGRAM_BOT_TOKEN not configured in environment or config.yaml")
        return []

    once = getattr(args, "once", False)
    if once:
        print("Polling Telegram bot updates once...")
        handled = poll_updates(token=token, db=db, limit=10)
        print(f"Completed poll. Handled {len(handled)} updates.")
        return handled

    print("Starting Telegram bot polling loop. Press Ctrl+C to exit...")
    offset = None
    all_handled: list[dict[str, Any]] = []
    try:
        while True:
            updates = poll_updates(token=token, db=db, offset=offset, limit=10, timeout=5)
            if updates:
                max_id = max(
                    (u.get("update_id", 0) for u in updates if u.get("update_id")),
                    default=0,
                )
                if max_id:
                    offset = max_id + 1
                all_handled.extend(updates)
            time.sleep(2)
    except KeyboardInterrupt:
        print("\nBot polling stopped by user.")
    return all_handled


def main(argv: list[str] | None = None) -> int:
    """Main CLI entrypoint."""
    parser = build_parser()
    args = parser.parse_args(argv)

    if not args.command:
        parser.print_help()
        return 0

    if args.command == "scan":
        run_scan(args)
    elif args.command == "list":
        run_list(args)
    elif args.command == "apply":
        run_apply(args)
    elif args.command == "auth":
        run_auth(args)
    elif args.command == "bot":
        run_bot(args)
    else:
        parser.print_help()

    return 0
