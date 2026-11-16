import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.core.database import Base
from backend.main import app
from backend.models import *  # noqa: F403


@pytest.fixture
def db(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}")
    from sqlalchemy import event
    @event.listens_for(engine, "connect")
    def _fk(dbapi_connection, _record):
        dbapi_connection.execute("PRAGMA foreign_keys=ON")
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def client(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'client-test.db'}")
    from sqlalchemy import event

    @event.listens_for(engine, "connect")
    def _enable_foreign_keys(dbapi_connection, _record):
        dbapi_connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    testing_sessions = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    def override_get_db():
        session = testing_sessions()
        try:
            yield session
        finally:
            session.close()

    from backend.api.detectors import get_db as detector_get_db
    from backend.api.documents import get_db as documents_get_db

    app.dependency_overrides[detector_get_db] = override_get_db
    app.dependency_overrides[documents_get_db] = override_get_db
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()
        engine.dispose()
