from datetime import datetime
import json
from pathlib import Path
import sqlite3
from typing import Any


class DB:
    # ponytail: sqlite3 stdlib over ORM; ceiling ~100k jobs, upgrade to asyncpg/SQLAlchemy if distributed.
    # ponytail: JSON serialized text columns for roadmap/tech_stack; upgrade to normalized tables if querying steps.
    PROJECT_COLUMNS = {
        "job_hash",
        "platform",
        "platform_id",
        "title",
        "url",
        "budget_min",
        "budget_max",
        "currency",
        "description",
        "scope",
        "tier",
        "fit_score",
        "status",
        "suggested_bid",
        "delivery_days",
        "tech_stack",
        "roadmap",
        "proposal",
        "rejection_reason",
        "skills",
        "claude_leverage",
        "win_probability",
        "difficulty",
        "pricing_strategy",
        "prerequisites",
        "technical_hook",
        "clarifying_question",
        "client_risk",
        "red_flags",
        "arbitrage_score",
        "scope_shield",
    }

    APPLICATION_COLUMNS = {
        "project_id",
        "bid_amount",
        "delivery_days",
        "proposal_text",
        "status",
        "error_message",
        "submitted_at",
    }

    def __init__(self, db_path: str = "data/hunter.db"):
        self.db_path = str(db_path)
        if self.db_path != ":memory:":
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON;")

    def init_schema(self) -> None:
        """Create projects and applications tables and indexes."""
        cursor = self.conn.cursor()
        cursor.executescript(
            """
            CREATE TABLE IF NOT EXISTS projects (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_hash TEXT UNIQUE NOT NULL,
                platform TEXT,
                platform_id TEXT,
                title TEXT,
                url TEXT,
                budget_min REAL,
                budget_max REAL,
                currency TEXT,
                description TEXT,
                scope TEXT,
                tier TEXT,
                fit_score REAL,
                status TEXT DEFAULT 'new',
                suggested_bid REAL,
                delivery_days INTEGER,
                tech_stack TEXT,
                roadmap TEXT,
                proposal TEXT,
                rejection_reason TEXT,
                skills TEXT,
                claude_leverage INTEGER,
                win_probability REAL,
                difficulty TEXT,
                pricing_strategy TEXT,
                prerequisites TEXT,
                technical_hook TEXT,
                clarifying_question TEXT,
                client_risk TEXT,
                red_flags TEXT,
                arbitrage_score REAL,
                scope_shield TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS applications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                bid_amount REAL,
                delivery_days INTEGER,
                proposal_text TEXT,
                status TEXT DEFAULT 'pending',
                error_message TEXT,
                submitted_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """
        )
        self.conn.commit()
        try:
            self.conn.execute("ALTER TABLE projects ADD COLUMN skills TEXT;")
            self.conn.commit()
        except sqlite3.OperationalError:
            pass
        # Migration for existing databases: add new Phase 1 fields
        new_columns = {
            "claude_leverage": "INTEGER",
            "win_probability": "REAL",
            "difficulty": "TEXT",
            "pricing_strategy": "TEXT",
            "prerequisites": "TEXT",
            "technical_hook": "TEXT",
            "clarifying_question": "TEXT",
            "client_risk": "TEXT",
            "red_flags": "TEXT",
            "arbitrage_score": "REAL",
            "scope_shield": "TEXT",
        }
        cursor = self.conn.execute("PRAGMA table_info(projects)")
        existing_cols = {row[1] for row in cursor.fetchall()}
        for col_name, col_type in new_columns.items():
            if col_name not in existing_cols:
                try:
                    self.conn.execute(
                        f"ALTER TABLE projects ADD COLUMN {col_name} {col_type};"
                    )
                    self.conn.commit()
                except sqlite3.OperationalError:
                    pass
        # Create indexes after all columns exist (safe for pre-existing and new schemas)
        for idx_sql in [
            "CREATE INDEX IF NOT EXISTS idx_projects_job_hash ON projects(job_hash);",
            "CREATE INDEX IF NOT EXISTS idx_projects_tier ON projects(tier);",
            "CREATE INDEX IF NOT EXISTS idx_projects_status ON projects(status);",
            "CREATE INDEX IF NOT EXISTS idx_applications_project_id ON applications(project_id);",
        ]:
            try:
                self.conn.execute(idx_sql)
            except sqlite3.OperationalError:
                pass
        self.conn.commit()

    def save_project(self, proj_dict: dict[str, Any]) -> bool:
        """Save a new project to the database.

        Returns True if inserted, False if duplicate job_hash or invalid.
        """
        if not proj_dict or "job_hash" not in proj_dict:
            return False

        if self.is_seen(proj_dict["job_hash"]):
            return False

        cols: list[str] = []
        vals: list[Any] = []
        placeholders: list[str] = []

        for k, v in proj_dict.items():
            if k in self.PROJECT_COLUMNS:
                cols.append(k)
                if isinstance(v, (list, dict)):
                    vals.append(json.dumps(v, ensure_ascii=False))
                else:
                    vals.append(v)
                placeholders.append("?")

        if not cols:
            return False

        sql = f"INSERT INTO projects ({', '.join(cols)}) VALUES ({', '.join(placeholders)})"
        try:
            self.conn.execute(sql, vals)
            self.conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False

    def is_seen(self, job_hash: str) -> bool:
        """Check if a project hash already exists in database."""
        cursor = self.conn.execute(
            "SELECT 1 FROM projects WHERE job_hash = ? LIMIT 1", (job_hash,)
        )
        return cursor.fetchone() is not None

    def get_project(self, job_id: int | str) -> dict[str, Any] | None:
        """Retrieve a project by integer ID or string job_hash."""
        if isinstance(job_id, bool):
            return None
        if isinstance(job_id, int) and not isinstance(job_id, bool):
            cursor = self.conn.execute(
                "SELECT * FROM projects WHERE id = ?", (job_id,)
            )
            row = cursor.fetchone()
        else:
            # Check by job_hash first
            cursor = self.conn.execute(
                "SELECT * FROM projects WHERE job_hash = ?", (str(job_id),)
            )
            row = cursor.fetchone()
            if not row and str(job_id).isdigit():
                cursor = self.conn.execute(
                    "SELECT * FROM projects WHERE id = ?", (int(job_id),)
                )
                row = cursor.fetchone()

        if not row:
            return None
        return self._row_to_dict(row)

    def list_projects(
        self, tier: str | None = None, status: str | None = None
    ) -> list[dict[str, Any]]:
        """List projects with optional tier and status filters."""
        query = "SELECT * FROM projects"
        conditions: list[str] = []
        params: list[Any] = []

        if tier is not None:
            conditions.append("tier = ?")
            params.append(tier)
        if status is not None:
            conditions.append("status = ?")
            params.append(status)

        if conditions:
            query += " WHERE " + " AND ".join(conditions)

        query += " ORDER BY id DESC"
        cursor = self.conn.execute(query, params)
        return [self._row_to_dict(row) for row in cursor.fetchall()]

    def get_projects_by_date(
        self, date_str: str | None = None
    ) -> list[dict[str, Any]]:
        """Retrieve all projects created on a given date (defaults to today YYYY-MM-DD)."""
        if date_str is None:
            date_str = datetime.now().strftime("%Y-%m-%d")
        date_val = str(date_str).strip()[:10]
        cursor = self.conn.execute(
            "SELECT * FROM projects WHERE date(created_at) = ? ORDER BY id ASC",
            (date_val,),
        )
        return [self._row_to_dict(row) for row in cursor.fetchall()]

    def update_status(self, job_id: int | str, status: str) -> bool:
        """Update the status of a project.

        Returns True if row was updated, False otherwise.
        """
        if isinstance(job_id, bool):
            return False
        if isinstance(job_id, int) and not isinstance(job_id, bool):
            cursor = self.conn.execute(
                "UPDATE projects SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (status, job_id),
            )
        else:
            cursor = self.conn.execute(
                "UPDATE projects SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE job_hash = ?",
                (status, str(job_id)),
            )
            if cursor.rowcount == 0 and str(job_id).isdigit():
                cursor = self.conn.execute(
                    "UPDATE projects SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                    (status, int(job_id)),
                )

        self.conn.commit()
        return cursor.rowcount > 0

    def save_application(self, app_dict: dict[str, Any]) -> int | None:
        """Save a new application record.

        Returns the inserted ID or None.
        """
        cols: list[str] = []
        vals: list[Any] = []
        placeholders: list[str] = []

        for k, v in app_dict.items():
            if k in self.APPLICATION_COLUMNS:
                cols.append(k)
                vals.append(v)
                placeholders.append("?")

        if not cols:
            return None

        sql = f"INSERT INTO applications ({', '.join(cols)}) VALUES ({', '.join(placeholders)})"
        try:
            cursor = self.conn.execute(sql, vals)
            self.conn.commit()
            return cursor.lastrowid
        except sqlite3.IntegrityError:
            return None

    def _row_to_dict(self, row: sqlite3.Row) -> dict[str, Any]:
        """Convert a sqlite3.Row to a dictionary, unpacking JSON fields."""
        d = dict(row)
        for field in ("tech_stack", "roadmap", "skills", "prerequisites", "red_flags"):
            val = d.get(field)
            if isinstance(val, str) and val.startswith(("[", "{")):
                try:
                    d[field] = json.loads(val)
                except (json.JSONDecodeError, TypeError):
                    pass
        if isinstance(d.get("red_flags"), str):
            d["red_flags"] = []
        if d.get("red_flags") is None and "red_flags" in d:
            d["red_flags"] = []
        return d

    def close(self) -> None:
        """Close the database connection."""
        self.conn.close()

    def __enter__(self) -> "DB":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()


if __name__ == "__main__":
    with DB(":memory:") as test_db:
        test_db.init_schema()
        assert test_db.save_project({"job_hash": "test", "title": "Test", "skills": ["Python", "SQLite"]}) is True
        assert test_db.is_seen("test") is True
        assert test_db.save_project({"job_hash": "test", "title": "Test"}) is False
        proj = test_db.get_project("test")
        assert proj["title"] == "Test"
        assert proj["skills"] == ["Python", "SQLite"]
        assert test_db.get_project(True) is None
        assert test_db.update_status(False, "evaluated") is False
        assert test_db.update_status("test", "evaluated") is True
        assert test_db.list_projects(status="evaluated")[0]["job_hash"] == "test"
        assert len(test_db.get_projects_by_date()) == 1
    print("All DB self-checks passed.")

