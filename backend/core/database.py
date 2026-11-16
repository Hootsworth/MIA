import os
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker

ROOT = Path(__file__).resolve().parents[2]
DATABASE_URL = os.getenv("MIA_DATABASE_URL", f"sqlite:///{ROOT / 'data' / 'mia.db'}")
connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args)
if DATABASE_URL.startswith("sqlite"):
    @event.listens_for(engine, "connect")
    def enable_foreign_keys(dbapi_connection, _connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    pass


def init_db():
    from backend.models import Base as _  # register model tables
    Base.metadata.create_all(bind=engine)
    if engine.dialect.name == "sqlite":
        # create_all creates new tables but does not add fields to the v1 table.
        additions = {
            "started_at": "DATETIME",
            "finished_at": "DATETIME",
            "completed_items": "INTEGER NOT NULL DEFAULT 0",
            "total_items": "INTEGER NOT NULL DEFAULT 0",
            "cancel_requested": "BOOLEAN NOT NULL DEFAULT 0",
            "interruption_reason": "TEXT",
        }
        with engine.begin() as connection:
            columns = {row["name"] for row in connection.exec_driver_sql("PRAGMA table_info(experiments)").mappings()}
            for name, definition in additions.items():
                if name not in columns:
                    connection.exec_driver_sql(f"ALTER TABLE experiments ADD COLUMN {name} {definition}")
