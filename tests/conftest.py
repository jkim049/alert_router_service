import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.main import app
from app.database import Base, get_db


@pytest.fixture
def client():
    """
    Provides a TestClient backed by a fresh in-memory SQLite database.
    StaticPool ensures all ORM operations share the same connection,
    which is required for in-memory SQLite to persist data across requests.
    Lifespan is not triggered — tables are created manually below.
    """
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()


# --- Payload factories ---
# These return minimal valid payloads. Override individual fields in tests
# to exercise specific behaviours without repeating boilerplate.

def route_payload(**overrides) -> dict:
    base = {
        "id": "route-1",
        "conditions": {"severity": ["critical"]},
        "target": {"type": "slack", "channel": "#oncall"},
        "priority": 10,
    }
    base.update(overrides)
    return base


def alert_payload(**overrides) -> dict:
    base = {
        "id": "alert-1",
        "severity": "critical",
        "service": "payment-api",
        "group": "backend",
        "timestamp": "2026-03-25T14:30:00Z",
    }
    base.update(overrides)
    return base
