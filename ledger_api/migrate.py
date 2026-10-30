"""Apply unapplied SQL migration files in order.

Every file in ``migrations/`` that matches ``NNN_*.sql`` is executed in
numeric order.  A small ``schema_migrations`` table tracks which files
have already been applied so they are never re-run.

The runner is intentionally minimal (no Alembic dependency) and safe to
call on every startup — it's a no-op when the database is up to date.
"""
from __future__ import annotations

import logging
import re
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.engine import Engine

logger = logging.getLogger("ledger_api")

_MIGRATION_DIR = Path(__file__).resolve().parent.parent / "migrations"
_FILE_PATTERN = re.compile(r"^(\d+)_.+\.sql$")


def apply_migrations(engine: Engine, *, migration_dir: Path = _MIGRATION_DIR) -> int:
    """Run all pending SQL migrations and return the count applied."""
    with engine.begin() as conn:
        # Ensure the tracking table exists.
        conn.execute(
            text(
                "CREATE TABLE IF NOT EXISTS schema_migrations ("
                "  filename TEXT PRIMARY KEY,"
                "  applied_at TIMESTAMPTZ NOT NULL DEFAULT now()"
                ")"
            )
        )

        applied: set[str] = {
            row[0]
            for row in conn.execute(
                text("SELECT filename FROM schema_migrations")
            ).fetchall()
        }

        # Bootstrap: if the database already has the base schema (from a manual
        # run of 001_ledger_schema.sql before this runner existed) seed the
        # tracking table so 001 is never re-applied.
        if not applied:
            has_projects = conn.execute(
                text(
                    "SELECT EXISTS ("
                    "  SELECT 1 FROM information_schema.tables"
                    "  WHERE table_name = 'projects'"
                    ")"
                )
            ).scalar()
            if has_projects:
                conn.execute(
                    text(
                        "INSERT INTO schema_migrations (filename)"
                        " VALUES ('001_ledger_schema.sql')"
                        " ON CONFLICT DO NOTHING"
                    )
                )
                applied.add("001_ledger_schema.sql")
                logger.info(
                    "seeded schema_migrations with 001_ledger_schema.sql "
                    "(tables already exist)"
                )

        # Discover and sort migration files.
        files: list[tuple[int, Path]] = []
        for path in sorted(migration_dir.iterdir()):
            m = _FILE_PATTERN.match(path.name)
            if m:
                files.append((int(m.group(1)), path))
        files.sort(key=lambda t: t[0])

        count = 0
        for _seq, path in files:
            if path.name in applied:
                continue
            logger.info("applying migration %s", path.name)
            sql = path.read_text(encoding="utf-8")
            # Execute each statement individually so multi-statement files work.
            for stmt in sql.split(";"):
                clean_lines = [
                    line for line in stmt.splitlines()
                    if not line.strip().startswith("--")
                ]
                clean_stmt = "\n".join(clean_lines).strip()
                if clean_stmt:
                    conn.execute(text(clean_stmt))
            conn.execute(
                text("INSERT INTO schema_migrations (filename) VALUES (:f)"),
                {"f": path.name},
            )
            count += 1
            logger.info("migration %s applied", path.name)

    if count:
        logger.info("applied %d migration(s)", count)
    else:
        logger.debug("database schema is up to date")
    return count
