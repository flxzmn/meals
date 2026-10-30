import sys
from contextlib import contextmanager
from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.orm import declarative_base, sessionmaker
from config.settings import settings

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
    },
    "substitutions": {"quantity_ratio": "FLOAT", "quantity_note": "TEXT"},
    "substitution_suggestions": {"quantity_ratio": "FLOAT", "quantity_note": "TEXT"},
}


def init_db() -> None:
    from db import models  # noqa: F401
    Base.metadata.create_all(bind=engine)
    add_missing_columns(engine)


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
