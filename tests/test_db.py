import pytest
from core.db import DB


def test_db_init_and_deduplication(tmp_path):
    db_file = tmp_path / "test_hunter.db"
    db = DB(str(db_file))
    db.init_schema()

    project = {
        "job_hash": "hash_123",
        "platform": "ponisha",
        "platform_id": "101",
        "title": "Telegram Bot",
        "url": "https://ponisha.ir/project/101",
        "budget_min": 1000000,
        "budget_max": 2000000,
        "currency": "IRT",
        "description": "Build a bot",
        "scope": "bots",
        "tier": "A",
        "fit_score": 0.85,
        "status": "new",
    }

    saved = db.save_project(project)
    assert saved is True
    assert db.is_seen("hash_123") is True
    assert db.is_seen("non_existent") is False

    # Duplicate insert should return False
    assert db.save_project(project) is False


def test_get_project(tmp_path):
    db_file = tmp_path / "test_hunter.db"
    db = DB(str(db_file))
    db.init_schema()

    project = {
        "job_hash": "hash_get_1",
        "platform": "parscoders",
        "platform_id": "202",
        "title": "FastAPI Webhook",
        "url": "https://parscoders.com/project/202",
        "budget_min": 2000000,
        "budget_max": 3000000,
        "currency": "IRT",
        "description": "Build a webhook endpoint",
        "scope": "scripting",
        "tier": "A",
        "fit_score": 0.90,
        "status": "new",
    }
    db.save_project(project)

    # Fetch by hash
    fetched_by_hash = db.get_project("hash_get_1")
    assert fetched_by_hash is not None
    assert fetched_by_hash["title"] == "FastAPI Webhook"
    assert fetched_by_hash["platform_id"] == "202"

    # Fetch by id
    job_id = fetched_by_hash["id"]
    fetched_by_id = db.get_project(job_id)
    assert fetched_by_id is not None
    assert fetched_by_id["job_hash"] == "hash_get_1"

    # Non-existent project
    assert db.get_project("non_existent") is None
    assert db.get_project(99999) is None


def test_list_projects_filtering(tmp_path):
    db_file = tmp_path / "test_hunter.db"
    db = DB(str(db_file))
    db.init_schema()

    projects = [
        {"job_hash": "h1", "title": "Job 1", "tier": "A", "status": "new"},
        {"job_hash": "h2", "title": "Job 2", "tier": "A", "status": "evaluated"},
        {"job_hash": "h3", "title": "Job 3", "tier": "B", "status": "new"},
        {"job_hash": "h4", "title": "Job 4", "tier": "C", "status": "rejected"},
    ]
    for p in projects:
        db.save_project(p)

    all_jobs = db.list_projects()
    assert len(all_jobs) == 4

    tier_a_jobs = db.list_projects(tier="A")
    assert len(tier_a_jobs) == 2
    assert all(j["tier"] == "A" for j in tier_a_jobs)

    new_jobs = db.list_projects(status="new")
    assert len(new_jobs) == 2
    assert all(j["status"] == "new" for j in new_jobs)

    tier_a_evaluated = db.list_projects(tier="A", status="evaluated")
    assert len(tier_a_evaluated) == 1
    assert tier_a_evaluated[0]["job_hash"] == "h2"


def test_update_status(tmp_path):
    db_file = tmp_path / "test_hunter.db"
    db = DB(str(db_file))
    db.init_schema()

    project = {"job_hash": "h_status", "title": "Status test", "status": "new"}
    db.save_project(project)
    p = db.get_project("h_status")
    proj_id = p["id"]

    # Update to evaluated
    assert db.update_status(proj_id, "evaluated") is True
    assert db.get_project(proj_id)["status"] == "evaluated"

    # Update by job_hash
    assert db.update_status("h_status", "applied") is True
    assert db.get_project(proj_id)["status"] == "applied"

    # Update non-existent
    assert db.update_status(9999, "rejected") is False


def test_schema_creates_tables(tmp_path):
    db_file = tmp_path / "test_hunter.db"
    db = DB(str(db_file))
    db.init_schema()

    cursor = db.conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = {row[0] for row in cursor.fetchall()}
    assert "projects" in tables
    assert "applications" in tables


def test_json_fields_serialization(tmp_path):
    db_file = tmp_path / "test_hunter.db"
    db = DB(str(db_file))
    db.init_schema()

    project = {
        "job_hash": "h_json",
        "title": "Architected Job",
        "roadmap": ["Step 1", "Step 2", "Step 3"],
        "tech_stack": ["python", "aiogram"],
        "suggested_bid": 2500000,
        "delivery_days": 3,
        "proposal": "Here is my proposal.",
    }
    assert db.save_project(project) is True

    fetched = db.get_project("h_json")
    assert fetched["roadmap"] == ["Step 1", "Step 2", "Step 3"]
    assert fetched["tech_stack"] == ["python", "aiogram"]
    assert fetched["suggested_bid"] == 2500000
    assert fetched["delivery_days"] == 3


def test_save_application(tmp_path):
    db_file = tmp_path / "test_hunter.db"
    db = DB(str(db_file))
    db.init_schema()

    project = {"job_hash": "h_app_proj", "title": "Project for App"}
    db.save_project(project)
    p = db.get_project("h_app_proj")

    app = {
        "project_id": p["id"],
        "bid_amount": 1800000,
        "delivery_days": 2,
        "proposal_text": "Sample proposal",
        "status": "submitted",
    }
    app_id = db.save_application(app)
    assert app_id is not None
    assert app_id > 0


def test_config_yaml_validity():
    import yaml
    from pathlib import Path

    config_path = Path("config.yaml")
    assert config_path.exists()

    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    assert "database" in config
    assert "platforms" in config
    assert "scopes" in config
    assert "scam_filter" in config
    assert "telegram" in config

    # Check the 6 active scopes plus disabled formatting
    assert "bots" in config["scopes"]
    assert "automation" in config["scopes"]
    assert "translation" in config["scopes"]
    assert "excel" in config["scopes"]
    assert "scraping" in config["scopes"]
    assert "scripting" in config["scopes"]
    assert config["scopes"]["formatting"]["enabled"] is False

    # Check platforms
    assert "ponisha" in config["platforms"]
    assert "parscoders" in config["platforms"]
    assert "freelancer" in config["platforms"]

