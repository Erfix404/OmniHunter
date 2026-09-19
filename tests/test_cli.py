from argparse import Namespace
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

from core.db import DB
from interfaces.cli import (
    build_parser,
    main,
    run_apply,
    run_auth,
    run_bot,
    run_list,
    run_scan,
)
from interfaces.telegram_bot import (
    answer_callback_query,
    poll_updates,
    send_project_alert,
)


def test_cli_parser_all_commands():
    parser = build_parser()

    # scan
    args = parser.parse_args(["scan", "--mock", "--dry-run", "--platform", "ponisha", "--notify"])
    assert args.command == "scan"
    assert args.mock is True
    assert args.dry_run is True
    assert args.platform == "ponisha"
    assert args.notify is True

    # list
    args = parser.parse_args(["list", "--tier", "A", "--status", "new", "--limit", "10"])
    assert args.command == "list"
    assert args.tier == "A"
    assert args.status == "new"
    assert args.limit == 10

    # apply default (dry_run=True, headless=False)
    args = parser.parse_args(["apply", "101"])
    assert args.command == "apply"
    assert args.job_id == "101"
    assert args.dry_run is True
    assert args.headless is False

    # apply with submit and headless
    args = parser.parse_args(["apply", "101", "--submit", "--headless"])
    assert args.command == "apply"
    assert args.dry_run is False
    assert args.headless is True

    # auth
    args = parser.parse_args(["auth", "parscoders", "--headless"])
    assert args.command == "auth"
    assert args.platform == "parscoders"
    assert args.headless is True

    # bot
    args = parser.parse_args(["bot", "--once"])
    assert args.command == "bot"
    assert args.once is True


def test_run_scan_mock_mode_and_deduplication(tmp_path):
    db_file = tmp_path / "scan_hunter.db"
    db = DB(str(db_file))
    db.init_schema()

    reports_dir = tmp_path / "reports"
    cfg = {
        "database": {"path": str(db_file)},
        "reports": {"directory": str(reports_dir)},
        "telegram": {"bot_token": "mock_tok", "chat_id": "123", "notify_tiers": ["A"]},
    }

    args = Namespace(command="scan", mock=True, dry_run=False, notify=False, platform=None)

    # First scan: should process all 4 mock projects
    processed = run_scan(args, config=cfg, db=db)
    assert len(processed) == 4

    # Check triage and architect applied
    scam_p = next(p for p in processed if p["platform_id"] == "mock_4")
    assert scam_p["is_scam"] is True
    assert scam_p["tier"] == "C"

    bot_p = next(p for p in processed if p["platform_id"] == "mock_1")
    assert bot_p["tier"] == "A"
    assert bot_p["scope"] == "bots"
    assert len(bot_p["roadmap"]) >= 3
    assert bot_p["suggested_bid"] is not None

    # Check projects are in DB
    stored_jobs = db.list_projects()
    assert len(stored_jobs) == 4

    # Second scan: deduplication should filter all out (0 unseen)
    second_processed = run_scan(args, config=cfg, db=db)
    assert len(second_processed) == 0


def test_run_scan_dry_run_does_not_persist(tmp_path):
    db_file = tmp_path / "dry_hunter.db"
    db = DB(str(db_file))
    db.init_schema()

    cfg = {"reports": {"directory": str(tmp_path / "reports")}}
    args = Namespace(command="scan", mock=True, dry_run=True, notify=False, platform=None)

    processed = run_scan(args, config=cfg, db=db)
    assert len(processed) == 4

    # DB should be empty
    assert len(db.list_projects()) == 0


def test_run_scan_with_notify_calls_telegram(tmp_path):
    db_file = tmp_path / "notify_hunter.db"
    db = DB(str(db_file))
    db.init_schema()

    cfg = {
        "reports": {"directory": str(tmp_path / "reports")},
        "telegram": {"bot_token": "test_token", "chat_id": "9999", "notify_tiers": ["A"]},
    }
    args = Namespace(command="scan", mock=True, dry_run=False, notify=True, platform=None)

    with patch("interfaces.cli.send_project_alert") as mock_alert:
        mock_alert.return_value = {"ok": True}
        processed = run_scan(args, config=cfg, db=db)
        assert len(processed) == 4
        # send_project_alert should be called for Tier A projects
        assert mock_alert.call_count >= 1


def test_run_scan_live_scrapers_mocked(tmp_path):
    db_file = tmp_path / "live_hunter.db"
    db = DB(str(db_file))
    db.init_schema()

    cfg = {
        "reports": {"directory": str(tmp_path / "reports")},
        "platforms": {
            "ponisha": {"enabled": True},
            "parscoders": {"enabled": True},
            "freelancer": {"enabled": False},
        },
    }
    args = Namespace(command="scan", mock=False, dry_run=False, notify=False, platform=None)

    mock_project = {
        "platform": "ponisha",
        "platform_id": "live_1",
        "job_hash": "ponisha_live_1",
        "title": "طراحی ربات تلگرام با پایتون",
        "url": "https://ponisha.ir/project/live_1",
        "budget_min": 2000000,
        "budget_max": 4000000,
        "currency": "IRT",
        "description": "پروژه ربات تلگرام",
        "skills": ["python"],
    }

    with patch("interfaces.cli.PonishaScraper.fetch_projects", return_value=[mock_project]), \
         patch("interfaces.cli.ParscodersScraper.fetch_projects", return_value=[]):
        processed = run_scan(args, config=cfg, db=db)
        assert len(processed) == 1
        assert processed[0]["job_hash"] == "ponisha_live_1"


def test_run_list_formatting_and_filters(tmp_path, capsys):
    db_file = tmp_path / "list_hunter.db"
    db = DB(str(db_file))
    db.init_schema()

    # Empty list
    args = Namespace(tier=None, status=None, limit=None)
    res = run_list(args, db=db)
    assert res == []
    captured = capsys.readouterr().out
    assert "No projects found" in captured

    # Populate projects
    db.save_project({"job_hash": "h1", "title": "Job 1", "tier": "A", "status": "new", "platform": "ponisha", "scope": "bots"})
    db.save_project({"job_hash": "h2", "title": "Job 2", "tier": "B", "status": "applied", "platform": "parscoders", "scope": "scripting"})
    db.save_project({"job_hash": "h3", "title": "Job 3", "tier": "A", "status": "applied", "platform": "freelancer", "scope": "automation"})

    # Filter by tier A
    args_tier = Namespace(tier="a", status=None, limit=None)
    res_tier = run_list(args_tier, db=db)
    assert len(res_tier) == 2
    assert all(p["tier"] == "A" for p in res_tier)

    # Filter by status applied and limit 1
    args_stat = Namespace(tier=None, status="applied", limit=1)
    res_stat = run_list(args_stat, db=db)
    assert len(res_stat) == 1
    assert res_stat[0]["status"] == "applied"


def test_run_apply_not_found(tmp_path, capsys):
    db_file = tmp_path / "apply_hunter.db"
    db = DB(str(db_file))
    db.init_schema()

    args = Namespace(job_id="9999", dry_run=True, headless=False)
    res = run_apply(args, db=db)
    assert res["status"] == "error"
    captured = capsys.readouterr().out
    assert "not found" in captured


def test_run_apply_dry_run_and_submit(tmp_path):
    db_file = tmp_path / "apply_hunter.db"
    db = DB(str(db_file))
    db.init_schema()

    proj = {
        "job_hash": "apply_proj_1",
        "platform": "ponisha",
        "platform_id": "p1",
        "title": "Telegram Bot",
        "url": "https://ponisha.ir/project/p1",
        "budget_min": 2000000,
        "suggested_bid": 2500000,
        "delivery_days": 3,
        "proposal": "Clean proposal text.",
        "status": "new",
    }
    db.save_project(proj)
    saved_p = db.get_project("apply_proj_1")
    p_id = saved_p["id"]

    # 1. Test Dry Run: fill_application is called with dry_run=True
    with patch("interfaces.cli.fill_application") as mock_fill:
        mock_fill.return_value = {
            "status": "success",
            "platform": "ponisha",
            "url": proj["url"],
            "bid": 2500000,
            "delivery_days": 3,
            "submitted": False,
            "details": "Dry run completed successfully",
        }
        args_dry = Namespace(job_id=str(p_id), dry_run=True, headless=False)
        res = run_apply(args_dry, db=db)
        assert res["status"] == "success"
        # Status in DB should remain 'new'
        assert db.get_project(p_id)["status"] == "new"

    # 2. Test Submit: fill_application called with dry_run=False, DB updated to 'applied'
    with patch("interfaces.cli.fill_application") as mock_fill:
        mock_fill.return_value = {
            "status": "success",
            "platform": "ponisha",
            "url": proj["url"],
            "bid": 2500000,
            "delivery_days": 3,
            "submitted": True,
            "details": "Application submitted successfully",
        }
        args_submit = Namespace(job_id=str(p_id), dry_run=False, headless=True)
        res = run_apply(args_submit, db=db)
        assert res["status"] == "success"
        # Status in DB should be updated to 'applied'
        assert db.get_project(p_id)["status"] == "applied"


def test_run_auth_mocked():
    with patch("interfaces.cli.interactive_login", return_value=Path("data/sessions/ponisha.json")) as mock_auth:
        args = Namespace(platform="ponisha", headless=True)
        res = run_auth(args)
        assert str(res) == str(Path("data/sessions/ponisha.json"))
        mock_auth.assert_called_once_with(platform="ponisha", headless=True)


def test_run_bot_once_and_token_checks(tmp_path, capsys):
    db_file = tmp_path / "bot_hunter.db"
    db = DB(str(db_file))
    db.init_schema()

    # Case 1: No token
    cfg_no_tok = {"database": {"path": str(db_file)}, "telegram": {}}
    args_once = Namespace(once=True)
    res_no_tok = run_bot(args_once, config=cfg_no_tok, db=db)
    assert res_no_tok == []
    captured = capsys.readouterr().out
    assert "TELEGRAM_BOT_TOKEN not configured" in captured

    # Case 2: With token and --once
    cfg_with_tok = {"database": {"path": str(db_file)}, "telegram": {"bot_token": "tok123"}}
    with patch("interfaces.cli.poll_updates", return_value=[{"action": "apply", "job_id": "1"}]) as mock_poll:
        res = run_bot(args_once, config=cfg_with_tok, db=db)
        assert len(res) == 1
        mock_poll.assert_called_once()


def test_main_cli_dispatch():
    with patch("interfaces.cli.run_scan") as mock_scan:
        assert main(["scan", "--mock"]) == 0
        mock_scan.assert_called_once()

    with patch("interfaces.cli.run_list") as mock_list:
        assert main(["list"]) == 0
        mock_list.assert_called_once()

    with patch("interfaces.cli.run_apply") as mock_apply:
        assert main(["apply", "101"]) == 0
        mock_apply.assert_called_once()

    with patch("interfaces.cli.run_auth") as mock_auth:
        assert main(["auth", "ponisha"]) == 0
        mock_auth.assert_called_once()

    with patch("interfaces.cli.run_bot") as mock_bot:
        assert main(["bot", "--once"]) == 0
        mock_bot.assert_called_once()

    # Empty command prints help and returns 0
    assert main([]) == 0


def test_telegram_bot_send_alert():
    # Missing credentials
    assert send_project_alert({}, "", "") == {"ok": False, "error": "Missing token or chat_id"}
    assert send_project_alert({}, "tok", "123") == {"ok": False, "error": "Invalid project data"}

    proj = {
        "id": 42,
        "title": "Telegram Bot Project",
        "url": "https://ponisha.ir/42",
        "platform": "ponisha",
        "budget_min": 1000000,
        "budget_max": 2000000,
        "suggested_bid": 1500000,
        "delivery_days": 2,
        "roadmap": ["Step 1", "Step 2"],
        "proposal": "Proposal text",
    }

    # Successful post
    with patch("requests.post") as mock_post:
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"ok": True, "result": {"message_id": 99}}
        mock_post.return_value = mock_resp

        res = send_project_alert(proj, token="tok_abc", chat_id="chat_xyz")
        assert res["ok"] is True
        assert res["result"]["message_id"] == 99

        # Verify inline keyboard payload
        _, kwargs = mock_post.call_args
        payload = kwargs["json"]
        assert payload["chat_id"] == "chat_xyz"
        keyboard = payload["reply_markup"]["inline_keyboard"][0]
        assert keyboard[0]["callback_data"] == "apply:42"
        assert keyboard[1]["callback_data"] == "reject:42"

    # Network exception handling
    with patch("requests.post", side_effect=Exception("Connection refused")):
        res_err = send_project_alert(proj, token="tok_abc", chat_id="chat_xyz")
        assert res_err["ok"] is False
        assert "Connection refused" in res_err["error"]


def test_telegram_bot_answer_callback_query():
    assert answer_callback_query("", "cb1") == {"ok": False, "error": "Missing token or callback_query_id"}

    with patch("requests.post") as mock_post:
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"ok": True, "result": True}
        mock_post.return_value = mock_resp

        res = answer_callback_query("tok", "cb123", text="Done")
        assert res["ok"] is True

    with patch("requests.post", side_effect=Exception("Timeout")):
        res_err = answer_callback_query("tok", "cb123")
        assert res_err["ok"] is False
        assert "Timeout" in res_err["error"]


def test_telegram_bot_poll_updates(tmp_path):
    db_file = tmp_path / "poll_hunter.db"
    db = DB(str(db_file))
    db.init_schema()

    db.save_project({"job_hash": "job_1", "id": 1, "title": "P1", "status": "new"})
    db.save_project({"job_hash": "job_2", "id": 2, "title": "P2", "status": "new"})

    # Empty token returns []
    assert poll_updates("") == []

    mock_updates_resp = {
        "ok": True,
        "result": [
            {
                "update_id": 1001,
                "callback_query": {
                    "id": "cb_1",
                    "data": "apply:1",
                },
            },
            {
                "update_id": 1002,
                "callback_query": {
                    "id": "cb_2",
                    "data": "reject:2",
                },
            },
            {
                "update_id": 1003,
                "callback_query": {
                    "id": "cb_3",
                    "data": "unknown:something",
                },
            },
        ],
    }

    with patch("requests.get") as mock_get, \
         patch("requests.post") as mock_post:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = mock_updates_resp
        mock_get.return_value = mock_resp

        mock_post_resp = MagicMock()
        mock_post_resp.json.return_value = {"ok": True}
        mock_post.return_value = mock_post_resp

        actions = poll_updates(token="valid_token", db=db, limit=10)
        assert len(actions) == 3
        assert actions[0] == {"action": "apply", "job_id": "1", "update_id": 1001}
        assert actions[1] == {"action": "reject", "job_id": "2", "update_id": 1002}
        assert actions[2] == {"action": "unknown", "data": "unknown:something", "update_id": 1003}

        # Verify DB updates
        assert db.get_project(1)["status"] == "applied"
        assert db.get_project(2)["status"] == "rejected"

    # Network error handling
    with patch("requests.get", side_effect=Exception("Telegram unreachable")):
        assert poll_updates("valid_token", db=db) == []


def test_daily_report_aggregates_across_multiple_scans(tmp_path):
    from datetime import datetime

    db_file = tmp_path / "multi_scan.db"
    db = DB(str(db_file))
    db.init_schema()

    reports_dir = tmp_path / "reports"
    cfg = {
        "database": {"path": str(db_file)},
        "reports": {"directory": str(reports_dir)},
    }
    today_str = datetime.now().strftime("%Y-%m-%d")
    report_path = reports_dir / f"{today_str}.md"

    args = Namespace(command="scan", mock=True, dry_run=False, notify=False, platform=None)

    # First scan: processes 4 projects and creates report
    run_scan(args, config=cfg, db=db)
    assert report_path.exists()
    content_first = report_path.read_text(encoding="utf-8")
    assert "مجموع کل پروژه‌های اسکن‌شده | **4**" in content_first

    # Second scan: 0 new projects, but report aggregates all saved projects from today
    second_res = run_scan(args, config=cfg, db=db)
    assert len(second_res) == 0
    content_second = report_path.read_text(encoding="utf-8")
    assert "مجموع کل پروژه‌های اسکن‌شده | **4**" in content_second


def test_cli_owns_db_clean_closure(tmp_path):
    db_file = tmp_path / "closure_hunter.db"
    cfg = {"database": {"path": str(db_file)}, "reports": {"directory": str(tmp_path / "reports")}}

    args_scan = Namespace(command="scan", mock=True, dry_run=True, notify=False, platform=None)
    with patch("interfaces.cli.DB.close") as mock_close:
        run_scan(args_scan, config=cfg, db=None)
        mock_close.assert_called_once()

    args_list = Namespace(tier=None, status=None, limit=None)
    with patch("interfaces.cli.DB.close") as mock_close, \
         patch("interfaces.cli._load_config", return_value=cfg):
        run_list(args_list, db=None)
        mock_close.assert_called_once()


def test_scan_parser_has_query_flags():
    parser = build_parser()
    args = parser.parse_args(["scan", "--mock", "--max-queries", "3", "--scope", "bots,excel"])
    assert args.max_queries == 3
    assert args.scope == "bots,excel"


def test_scan_parser_query_flag_defaults():
    parser = build_parser()
    args = parser.parse_args(["scan"])
    assert args.max_queries == 8
    assert args.scope is None


def test_run_scan_queries_each_scraper_per_keyword(monkeypatch, tmp_path):
    """Each scraper must be called once per keyword, not once total."""
    from interfaces import cli

    calls = []

    class FakeScraper:
        platform = "freelancer"

        def __init__(self, *a, **kw):
            pass

        def fetch_projects(self, query=""):
            calls.append(query)
            return []

    monkeypatch.setattr(cli, "FreelancerScraper", FakeScraper)
    monkeypatch.setattr(cli, "PonishaScraper", FakeScraper)
    monkeypatch.setattr(cli, "ParscodersScraper", FakeScraper)

    cfg = {
        "database": {"path": str(tmp_path / "t.db")},
        "platforms": {"freelancer": {"enabled": True, "rate_limit_delay_sec": 0}},
        "scopes": {"bots": {"enabled": True, "keywords": ["telegram bot", "aiogram"]}},
    }

    args = cli.build_parser().parse_args(["scan", "--platform", "freelancer"])
    cli.run_scan(args, config=cfg)

    assert calls == ["telegram bot", "aiogram"]


def test_run_scan_max_queries_truncates(monkeypatch, tmp_path):
    from interfaces import cli

    calls = []

    class FakeScraper:
        platform = "freelancer"

        def __init__(self, *a, **kw):
            pass

        def fetch_projects(self, query=""):
            calls.append(query)
            return []

    monkeypatch.setattr(cli, "FreelancerScraper", FakeScraper)
    monkeypatch.setattr(cli, "PonishaScraper", FakeScraper)
    monkeypatch.setattr(cli, "ParscodersScraper", FakeScraper)

    cfg = {
        "database": {"path": str(tmp_path / "t.db")},
        "platforms": {"freelancer": {"enabled": True, "rate_limit_delay_sec": 0}},
        "scopes": {"bots": {"enabled": True, "keywords": ["a", "b", "c"]}},
    }

    args = cli.build_parser().parse_args(
        ["scan", "--platform", "freelancer", "--max-queries", "2"]
    )
    cli.run_scan(args, config=cfg)

    assert calls == ["a", "b"]


def test_run_scan_scope_flag_narrows_scopes(monkeypatch, tmp_path):
    from interfaces import cli

    calls = []

    class FakeScraper:
        platform = "freelancer"

        def __init__(self, *a, **kw):
            pass

        def fetch_projects(self, query=""):
            calls.append(query)
            return []

    monkeypatch.setattr(cli, "FreelancerScraper", FakeScraper)
    monkeypatch.setattr(cli, "PonishaScraper", FakeScraper)
    monkeypatch.setattr(cli, "ParscodersScraper", FakeScraper)

    cfg = {
        "database": {"path": str(tmp_path / "t.db")},
        "platforms": {"freelancer": {"enabled": True, "rate_limit_delay_sec": 0}},
        "scopes": {
            "bots": {"enabled": True, "keywords": ["telegram bot"]},
            "excel": {"enabled": True, "keywords": ["excel"]},
        },
    }

    args = cli.build_parser().parse_args(
        ["scan", "--platform", "freelancer", "--scope", "excel"]
    )
    cli.run_scan(args, config=cfg)

    assert calls == ["excel"]

