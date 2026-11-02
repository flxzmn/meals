import shutil
import sys
from contextlib import contextmanager
from pathlib import Path
from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.orm import declarative_base, sessionmaker
from config.settings import LEGACY_DB_FILE, settings

connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
# STDIO transport: stdout is reserved for MCP messages
print(str(settings.database_url), file=sys.stderr)
engine = create_engine(settings.database_url, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False, expire_on_commit=False)
Base = declarative_base()

if settings.database_url.startswith("sqlite"):
    @event.listens_for(engine, "connect")
    def enable_foreign_keys(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


@contextmanager
def session_scope():
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


# Columns added after a table was first released. create_all does not add columns to existing tables.
ADDED_COLUMNS = {
    "nutrition_cache": {"portions": "JSON"},
    "recipes": {
        "parent_id": "INTEGER REFERENCES recipes(id) ON DELETE CASCADE",
        "constraints": "JSON",
        "changes": "JSON",
        "updated_at": "DATETIME",
        "instructions_source": "VARCHAR(20)",
        "servings": "INTEGER",
    },
    "substitutions": {"quantity_ratio": "FLOAT", "quantity_note": "TEXT"},
    "substitution_suggestions": {"quantity_ratio": "FLOAT", "quantity_note": "TEXT"},
}


def init_db() -> None:
    from db import models  # noqa: F401
    if settings.database_url == settings.default_database_url:
        adopt_legacy_database(LEGACY_DB_FILE, settings.default_database_file)
    Base.metadata.create_all(bind=engine)
    add_missing_columns(engine)
    refresh_estimated_grams(engine)
    load_seed_substitutions(SessionLocal)


SEED_FILE = Path(__file__).resolve().parent.parent / "data" / "substitutions_seed.json"


def load_seed_substitutions(session_factory, seed_file: Path = SEED_FILE) -> int:
    """Start an unused knowledge base with the seed rules (milk -> oat milk, ...).

    Unused means no rules, suggestions or decisions yet, so a user who worked with the base is never
    given rules again. Deleting every rule without ever deciding a suggestion does bring them back.
    """
    import json
    from db.models import Substitution, SubstitutionFeedback, SubstitutionSuggestion
    from repo.substitution_repo import SubstitutionRepo

    if not seed_file.exists():
        return 0
    with session_factory() as session:
        if any(session.query(model).first() for model in (Substitution, SubstitutionSuggestion, SubstitutionFeedback)):
            return 0
        created = SubstitutionRepo(session).add_bulk(json.loads(seed_file.read_text(encoding="utf-8")))["created"]
        session.commit()
    print(f"Loaded {len(created)} seed substitutions", file=sys.stderr)
    return len(created)


def adopt_legacy_database(legacy: Path, target: Path) -> bool:
    """Create the data folder and, on the first start after v1.0, copy the old database into it."""
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() or not legacy.exists():
        return False
    shutil.copy2(legacy, target)
    print(f"Copied database from {legacy} to {target}", file=sys.stderr)
    return True


def add_missing_columns(bind) -> None:
    columns_by_table = inspect(bind)
    with bind.begin() as connection:
        for table, columns in ADDED_COLUMNS.items():
            if not columns_by_table.has_table(table):
                continue
            existing = {column["name"] for column in columns_by_table.get_columns(table)}
            for name, column_type in columns.items():
                if name not in existing:
                    connection.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {column_type}"))


def refresh_estimated_grams(bind) -> int:
    """Recompute stored gram estimates, so parser fixes reach recipes saved by an older version."""
    from services.measure_service import estimate_grams
    changed = 0
    with bind.begin() as connection:
        rows = connection.execute(text("SELECT id, measure, estimated_grams FROM ingredients")).all()
        for row_id, measure, stored in rows:
            grams = estimate_grams(measure)
            if grams != stored:
                connection.execute(text("UPDATE ingredients SET estimated_grams = :grams WHERE id = :id"), {"grams": grams, "id": row_id})
                changed += 1
    if changed:
        print(f"Recomputed {changed} gram estimates", file=sys.stderr)
    return changed
