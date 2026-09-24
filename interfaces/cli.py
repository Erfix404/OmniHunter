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
from core.scrapers.bitjob import BitjobScraper
from core.scrapers.karlancer import KarlancerScraper
from core.scrapers.guru import GuruScraper
from core.scrapers.laborx import LaborXScraper
from core.scrapers.kaya import KayaScraper
from core.scrapers.query_builder import build_search_queries
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
    scan_parser.add_argument(
        "--max-queries",
        type=int,
        default=0,
        help=(
            "Maximum search queries per platform. Default 0 = search every "
            "keyword of every enabled scope; a finite value caps requests per "
            "platform and costs coverage."
        ),
    )
    scan_parser.add_argument(
        "--scope",
        type=str,
        default=None,
        help="Comma-separated scope keys to scan (e.g. bots,excel)",
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

    # browser
    browser_parser = subparsers.add_parser("browser", help="Manage browser profiles and connections")
    browser_parser.add_argument("--list", action="store_true", help="List Chrome profiles")
    browser_parser.add_argument("--status", action="store_true", help="Check CDP port status")

    # review
    review_parser = subparsers.add_parser("review", help="Review top unapplied / shortlisted projects")
    review_parser.add_argument(
        "--limit",
        type=int,
        default=10,
        help="Maximum number of projects to display",
    )
    review_parser.add_argument(
        "--shortlisted",
        action="store_true",
        default=False,
        help="Show only shortlisted projects",
    )
    review_parser.add_argument(
        "--sort",
        type=str,
        default="roi",
        choices=["roi", "win_probability", "claude_leverage", "arbitrage"],
        help="Metric to sort by (default: roi)",
    )

    # pick
    pick_parser = subparsers.add_parser("pick", help="Shortlist projects for action")
    pick_parser.add_argument("ids", nargs="+", help="Project ID(s) or job hash(es) to shortlist")

    # blueprint
    blueprint_parser = subparsers.add_parser("blueprint", help="Show senior-freelancer dossier for a project")
    blueprint_parser.add_argument("job_id", help="Target project ID or job hash")

    # fill
    fill_parser = subparsers.add_parser("fill", help="Populate bid form via CDP or isolated browser")
    fill_parser.add_argument("job_id", help="Target project ID or job hash")
    fill_parser.add_argument(
        "--cdp",
        type=str,
        default=None,
        nargs="?",
        const="default",
        help="Attach to live Chrome (optionally pass CDP URL, e.g. ws://127.0.0.1:9222/...)",
    )
    fill_parser.add_argument(
        "--confirm",
        action="store_true",
        default=False,
        help="Confirm live submission (default fills without submitting)",
    )

    # handover
    handover_parser = subparsers.add_parser(
        "handover", help="Generate client handover & escrow release pack"
    )
    handover_parser.add_argument("id", help="Target project ID or job hash")
    handover_parser.add_argument(
        "--output-dir",
        type=str,
        default=None,
        help="Custom output directory for the handover pack",
    )

    return parser


def _dropped_scopes(
    cfg: dict[str, Any],
    platform: str,
    only_scopes: list[str] | None,
    dropped_queries: list[str],
) -> list[str]:
    """Return the scope keys whose keywords were truncated away.

    Only called on the rare truncated path, so the extra per-scope query
    builds are cheap.
    """
    scopes_cfg = cfg.get("scopes")
    if not isinstance(scopes_cfg, dict):
        return []
    dropped = set(dropped_queries)
    keys = only_scopes if only_scopes is not None else list(scopes_cfg.keys())
    return sorted(
        key
        for key in keys
        if dropped
        & set(build_search_queries(cfg, platform, only_scopes=[key], limit=0))
    )


def run_scan(
    args: argparse.Namespace,
    config: dict[str, Any] | None = None,
    db: DB | None = None,
) -> list[dict[str, Any]]:
    """Execute end-to-end scanning pipeline."""
    cfg = config if config is not None else _load_config()
    owns_db = False

    if db is None:
        db_path = cfg.get("database", {}).get("path", "data/hunter.db")
        db = DB(db_path)
        db.init_schema()
        owns_db = True

    try:
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
                    platforms = ["ponisha", "parscoders", "freelancer", "bitjob", "karlancer", "guru", "laborx", "kaya"]

            for plat in platforms:
                delay = plat_cfgs.get(plat, {}).get("rate_limit_delay_sec", 2.0)
                if plat == "ponisha":
                    scrapers_to_run.append(PonishaScraper(rate_limit_delay_sec=delay))
                elif plat == "parscoders":
                    scrapers_to_run.append(ParscodersScraper(rate_limit_delay_sec=delay))
                elif plat == "freelancer":
                    scrapers_to_run.append(FreelancerScraper(rate_limit_delay_sec=delay))
                elif plat == "bitjob":
                    scrapers_to_run.append(BitjobScraper(rate_limit_delay_sec=delay))
                elif plat == "karlancer":
                    scrapers_to_run.append(KarlancerScraper(rate_limit_delay_sec=delay))
                elif plat == "guru":
                    scrapers_to_run.append(GuruScraper(rate_limit_delay_sec=delay))
                elif plat == "laborx":
                    scrapers_to_run.append(LaborXScraper(rate_limit_delay_sec=delay))
                elif plat == "kaya":
                    scrapers_to_run.append(KayaScraper(rate_limit_delay_sec=delay))

            only_scopes = None
            raw_scope_arg = getattr(args, "scope", None)
            if raw_scope_arg:
                only_scopes = [s.strip() for s in raw_scope_arg.split(",") if s.strip()]

            max_queries = getattr(args, "max_queries", 0)

            scopes_cfg = cfg.get("scopes")
            scopes_configured = isinstance(scopes_cfg, dict) and bool(scopes_cfg)

            # Projects are deduped in-batch by job_hash so a project returned by
            # several queries is triaged, billed and alerted only once.
            seen_hashes: set[str] = set()

            for scraper in scrapers_to_run:
                platform = getattr(scraper, "platform", "")
                queries = build_search_queries(
                    cfg,
                    platform,
                    only_scopes=only_scopes,
                    limit=max_queries,
                )
                if not queries:
                    if only_scopes is not None or scopes_configured:
                        logger.warning(
                            "No search queries for platform '%s'; skipping.", platform
                        )
                        continue
                    # No scopes configured at all: fall back to the legacy
                    # unfiltered fetch so a scope-less config still scans.
                    queries = [""]

                if max_queries and max_queries > 0:
                    full_queries = build_search_queries(
                        cfg,
                        platform,
                        only_scopes=only_scopes,
                        limit=0,
                    )
                    if len(full_queries) > len(queries):
                        dropped_scopes = _dropped_scopes(
                            cfg,
                            platform,
                            only_scopes,
                            full_queries[len(queries):],
                        )
                        logger.warning(
                            "--max-queries %d truncated platform '%s' to %d of %d "
                            "queries; unscanned scopes: %s",
                            max_queries,
                            platform,
                            len(queries),
                            len(full_queries),
                            ", ".join(dropped_scopes) if dropped_scopes else "unknown",
                        )

                for query in queries:
                    try:
                        fetched = scraper.fetch_projects(query)
                    except Exception as e:
                        logger.error("Scraper error on '%s' query '%s': %s", platform, query, e)
                        continue
                    for project in fetched:
                        j_hash = project.get("job_hash", "")
                        if j_hash and j_hash in seen_hashes:
                            continue
                        if j_hash:
                            seen_hashes.add(j_hash)
                        raw_projects.append(project)

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
            report_projects = processed_projects
            if not getattr(args, "dry_run", False) and db is not None:
                saved_today = db.get_projects_by_date(today_str)
                if saved_today:
                    report_projects = saved_today
            build_markdown_report(report_projects, output_path=report_file)
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
    finally:
        if owns_db and db is not None:
            db.close()


def run_list(
    args: argparse.Namespace,
    db: DB | None = None,
) -> list[dict[str, Any]]:
    """Fetch and display projects from database."""
    owns_db = False
    if db is None:
        cfg = _load_config()
        db_path = cfg.get("database", {}).get("path", "data/hunter.db")
        db = DB(db_path)
        db.init_schema()
        owns_db = True

    try:
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
    finally:
        if owns_db and db is not None:
            db.close()


def run_apply(
    args: argparse.Namespace,
    db: DB | None = None,
) -> dict[str, Any]:
    """Retrieve project and populate application form with Playwright."""
    owns_db = False
    if db is None:
        cfg = _load_config()
        db_path = cfg.get("database", {}).get("path", "data/hunter.db")
        db = DB(db_path)
        db.init_schema()
        owns_db = True

    try:
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
    finally:
        if owns_db and db is not None:
            db.close()


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
    owns_db = False
    cfg = config if config is not None else _load_config()
    if db is None:
        db_path = cfg.get("database", {}).get("path", "data/hunter.db")
        db = DB(db_path)
        db.init_schema()
        owns_db = True

    try:
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
                time.sleep(0.5)
        except KeyboardInterrupt:
            print("\nBot polling stopped by user.")
        return all_handled
    finally:
        if owns_db and db is not None:
            db.close()


def run_browser(args: argparse.Namespace) -> None:
    if getattr(args, "list", False):
        from core.browser.profiles import get_chrome_profiles
        profiles = get_chrome_profiles()
        print(f"{'DIR NAME':<14} {'DISPLAY NAME':<20} EMAIL")
        print("-" * 60)
        for k, v in sorted(profiles.items()):
            email = v.get("email") or "-"
            marker = " *" if v.get("is_last_used") else ""
            print(f"{k:<14} {v.get('name'):<20} {email}{marker}")
    elif getattr(args, "status", False):
        from core.browser.connection import get_active_port
        port_info = get_active_port()
        if port_info:
            print(f"Approval Mode Active. Listening on port: {port_info[0]}")
        else:
            print("Approval Mode NOT Active. No DevToolsActivePort found.")
    else:
        print("Please specify --list or --status")


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
    elif args.command == "browser":
        run_browser(args)
    elif args.command == "review":
        run_review(args)
    elif args.command == "pick":
        run_pick(args)
    elif args.command == "blueprint":
        run_blueprint(args)
    elif args.command == "fill":
        run_fill(args)
    elif args.command == "handover":
        run_handover(args)
    else:
        parser.print_help()

    return 0


def _get_agent_api(db: DB | None = None) -> Any:
    """Build an OmniHunterAgentAPI sharing an existing DB connection when given."""
    from core.agent_api import OmniHunterAgentAPI

    api = OmniHunterAgentAPI.__new__(OmniHunterAgentAPI)
    api.config_path = "config.yaml"
    api.config = _load_config()
    if db is not None:
        api.db = db
        api.db_path = getattr(db, "db_path", "")
        api._owns_db = False
    else:
        db_path = str(api.config.get("database", {}).get("path", "data/hunter.db"))
        api.db_path = db_path
        api.db = DB(db_path)
        api.db.init_schema()
        api._owns_db = True
    from core.profile import FreelancerProfile

    api.profile = FreelancerProfile()
    api.scrapers = api._build_scrapers()
    return api


def run_review(
    args: argparse.Namespace,
    db: DB | None = None,
) -> list[dict[str, Any]]:
    """Display top unapplied / shortlisted projects in a terminal table.

    Reads from the local database only (no live scraping) so review is
    instant and never burns rate limit.
    """
    owns_db = False
    if db is None:
        cfg = _load_config()
        db_path = cfg.get("database", {}).get("path", "data/hunter.db")
        db = DB(db_path)
        db.init_schema()
        owns_db = True
    try:
        limit = getattr(args, "limit", 10) or 10
        only_shortlisted = getattr(args, "shortlisted", False)
        sort_by = getattr(args, "sort", "roi") or "roi"

        key_map = {
            "roi": "roi_score",
            "win_probability": "win_probability",
            "claude_leverage": "claude_leverage",
            "arbitrage": "arbitrage_score",
        }
        sort_field = key_map.get(sort_by, "roi_score")

        if only_shortlisted:
            projects = db.list_projects(status="shortlisted")
        else:
            # Unapplied pool: everything not yet applied/rejected.
            projects = [
                p
                for p in db.list_projects()
                if (p.get("status") or "new") not in ("applied", "rejected")
            ]
        projects.sort(
            key=lambda p: (
                float(p.get(sort_field) or 0),
                float(p.get("fit_score") or 0),
            ),
            reverse=True,
        )
        projects = projects[:limit]

        print(f"\n--- Review ({len(projects)}) ---")
        if not projects:
            print("No projects to review. Run `hunter scan --mock` first.")
            return []
        print(
            f"{'ID':<6} | {'Tier':<4} | {'ROI':<10} | {'Win%':<6} | {'Claude':<6} | {'Status':<11} | {'Title'}"
        )
        print("-" * 90)
        for p in projects:
            p_id = str(p.get("id") or "-")
            p_tier = str(p.get("tier") or "-")
            roi = p.get("roi_score")
            roi_s = f"{float(roi):.0f}" if roi is not None else "-"
            win = p.get("win_probability")
            win_s = f"{float(win):.0%}" if win is not None else "-"
            lev = p.get("claude_leverage")
            lev_s = str(lev) if lev is not None else "-"
            p_stat = str(p.get("status") or "new")
            p_title = str(p.get("title") or "")[:35]
            print(
                f"{p_id:<6} | {p_tier:<4} | {roi_s:<10} | {win_s:<6} | {lev_s:<6} | {p_stat:<11} | {p_title}"
            )
        return projects
    finally:
        if owns_db and db is not None:
            db.close()


def run_handover(
    args: argparse.Namespace,
    db: DB | None = None,
) -> dict[str, Any]:
    """Generate the client handover & escrow release pack for a project."""
    api = _get_agent_api(db)
    try:
        output_dir = getattr(args, "output_dir", None)
        job_ref = getattr(args, "id", None) or getattr(args, "job_id", None)
        res = api.create_handover_pack(job_ref, output_dir=output_dir)
        print(f"Handover pack created at: {res.get('output_dir')}")
        print(f"Files: {', '.join(res.get('files', []))}")
        message = str(res.get("handover_message") or "")
        preview = message[:300] + ("..." if len(message) > 300 else "")
        print(f"\n[Delivery Message Preview]\n{preview}")
        return res
    finally:
        if getattr(api, "_owns_db", True):
            try:
                api.db.close()
            except Exception:
                pass


def run_pick(
    args: argparse.Namespace,
    db: DB | None = None,
) -> list[str]:
    """Shortlist one or more projects by ID or job hash."""
    owns_db = False
    if db is None:
        cfg = _load_config()
        db_path = cfg.get("database", {}).get("path", "data/hunter.db")
        db = DB(db_path)
        db.init_schema()
        owns_db = True
    try:
        picked: list[str] = []
        for job_id in getattr(args, "ids", []) or []:
            ok = db.update_status(job_id, "shortlisted")
            status = "shortlisted" if ok else "NOT FOUND"
            print(f"{job_id}: {status}")
            if ok:
                picked.append(str(job_id))
        return picked
    finally:
        if owns_db and db is not None:
            db.close()


def run_blueprint(
    args: argparse.Namespace,
    db: DB | None = None,
) -> dict[str, Any]:
    """Display the full senior-freelancer dossier for a project."""
    api = _get_agent_api(db)
    try:
        dossier = api.get_blueprint(args.job_id)
        project = dossier.get("project", {})
        triage = dossier.get("triage", {})
        blueprint = dossier.get("blueprint", {})
        print(f"\n=== Blueprint: {project.get('title')} ===")
        print(f"Platform: {project.get('platform')} | Tier: {triage.get('tier')} | Scope: {triage.get('scope')}")
        print(f"\n[Technical Hook]\n{blueprint.get('technical_hook')}")
        print("\n[Prerequisites]")
        for item in blueprint.get("prerequisites") or []:
            print(f"  - {item}")
        print(f"\n[Clarifying Question]\n{blueprint.get('clarifying_question')}")
        print(f"\n[Roadmap]")
        for step in blueprint.get("roadmap") or []:
            print(f"  {step}")
        pricing = blueprint.get("pricing_breakdown") or {}
        print(
            f"\n[Pricing] bid={blueprint.get('suggested_bid')} "
            f"days={blueprint.get('delivery_days')} "
            f"currency={pricing.get('currency')}"
        )
        print(f"\n[Proposal]\n{blueprint.get('proposal')}")
        return dossier
    finally:
        if getattr(api, "_owns_db", True):
            try:
                api.db.close()
            except Exception:
                pass


def run_fill(
    args: argparse.Namespace,
    db: DB | None = None,
) -> dict[str, Any]:
    """Populate the bid form via live CDP tab or isolated browser."""
    api = _get_agent_api(db)
    try:
        cdp_opt = getattr(args, "cdp", None)
        confirm = bool(getattr(args, "confirm", False))
        # --cdp absent -> isolated browser; --cdp [--cdp URL] -> live Chrome
        # (auto-discovery when no URL is given).
        if cdp_opt is None:
            cdp_url = None
        elif cdp_opt == "default":
            cdp_url = ""
        else:
            cdp_url = str(cdp_opt)
        res = api.fill_tab(args.job_id, cdp_url=cdp_url, confirm_submit=confirm)
        print(f"fill result: {res.get('status')} (submitted={res.get('submitted')})")
        if res.get("details"):
            print(res["details"])
        return res
    finally:
        if getattr(api, "_owns_db", True):
            try:
                api.db.close()
            except Exception:
                pass
