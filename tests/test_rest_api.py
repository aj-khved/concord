"""Integration tests for the JSON REST API (M7/FR10), using FastAPI's
TestClient with the get_session dependency overridden to a dedicated,
throwaway database — same isolation pattern as the other DB integration
tests in this suite, so these never touch the real dev database."""

import uuid

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from concord.config import settings
from concord.db.models import Base, GoldenVendor, MatchCandidate, NormalizedVendorRecord
from concord.db.session import get_session

TEST_DB_NAME = "concord_test_rest_api"


def _server_url() -> str:
    return settings.database_url.rsplit("/", 1)[0]


@pytest.fixture(scope="module")
def test_engine():
    try:
        admin_engine = create_engine(f"{_server_url()}/postgres", isolation_level="AUTOCOMMIT")
        with admin_engine.connect() as conn:
            exists = conn.execute(
                text("SELECT 1 FROM pg_database WHERE datname = :name"), {"name": TEST_DB_NAME}
            ).scalar()
            if not exists:
                conn.execute(text(f"CREATE DATABASE {TEST_DB_NAME}"))
    except Exception as exc:
        pytest.skip(f"Postgres not reachable at {_server_url()}: {exc}")

    engine = create_engine(f"{_server_url()}/{TEST_DB_NAME}")
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()
    admin_engine = create_engine(f"{_server_url()}/postgres", isolation_level="AUTOCOMMIT")
    with admin_engine.connect() as conn:
        conn.execute(text(f"DROP DATABASE IF EXISTS {TEST_DB_NAME}"))


@pytest.fixture
def db_session(test_engine):
    session_factory = sessionmaker(bind=test_engine, expire_on_commit=False)
    session = session_factory()
    yield session
    session.close()


@pytest.fixture
def client(test_engine):
    from fastapi.testclient import TestClient

    from concord.api.app import app

    session_factory = sessionmaker(bind=test_engine, expire_on_commit=False)

    def override_get_session():
        session = session_factory()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_session] = override_get_session
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def _seed_golden_vendor(session, legal_name="Acme Inc.", tax_id="123456789") -> GoldenVendor:
    record = NormalizedVendorRecord(
        source="A",
        source_record_id=f"A-{uuid.uuid4().hex[:8]}",
        legal_name=legal_name,
        city="Springfield",
        category="Manufacturing",
        tax_id=tax_id,
    )
    session.add(record)
    session.flush()

    vendor = GoldenVendor(
        legal_name=legal_name,
        city="Springfield",
        category="Manufacturing",
        tax_id=tax_id,
        member_count=1,
    )
    session.add(vendor)
    session.flush()
    record.golden_vendor_id = vendor.id
    session.commit()
    return vendor


def test_list_vendors_returns_seeded_vendor(client, db_session):
    _seed_golden_vendor(db_session, legal_name="Unique Test Vendor Co.")

    response = client.get("/api/vendors", params={"search": "Unique Test Vendor"})

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["legal_name"] == "Unique Test Vendor Co."


def test_get_vendor_detail_includes_members(client, db_session):
    vendor = _seed_golden_vendor(db_session, legal_name="Detail Test Vendor")

    response = client.get(f"/api/vendors/{vendor.id}")

    assert response.status_code == 200
    body = response.json()
    assert body["legal_name"] == "Detail Test Vendor"
    assert len(body["members"]) == 1
    assert body["members"][0]["source"] == "A"


def test_get_vendor_not_found_returns_404(client):
    response = client.get(f"/api/vendors/{uuid.uuid4()}")
    assert response.status_code == 404


def test_review_decision_creates_review_and_updates_golden_vendors(client, db_session):
    record_a = NormalizedVendorRecord(
        source="A", source_record_id="A-review-1", legal_name="Review Test A", category="Logistics"
    )
    record_b = NormalizedVendorRecord(
        source="B", source_record_id="B-review-1", legal_name="Review Test B", category="Logistics"
    )
    db_session.add_all([record_a, record_b])
    db_session.flush()

    candidate = MatchCandidate(
        batch_id=uuid.uuid4(),
        record_id_1=record_a.id,
        record_id_2=record_b.id,
        score=0.7,
        tier="pending_review",
        features={},
    )
    db_session.add(candidate)
    db_session.commit()

    response = client.post(
        f"/api/review/{candidate.id}/decide",
        json={"decision": "approve", "reviewer": "test-reviewer"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["already_reviewed"] is False

    # A second submission for the same candidate must be a no-op, not a
    # duplicate review or a constraint-violation error.
    response_2 = client.post(
        f"/api/review/{candidate.id}/decide",
        json={"decision": "reject", "reviewer": "someone-else"},
    )
    assert response_2.status_code == 200
    assert response_2.json()["already_reviewed"] is True


def test_review_decision_rejects_invalid_decision_value(client, db_session):
    record_a = NormalizedVendorRecord(
        source="A", source_record_id="A-invalid-1", legal_name="Invalid Test A"
    )
    record_b = NormalizedVendorRecord(
        source="B", source_record_id="B-invalid-1", legal_name="Invalid Test B"
    )
    db_session.add_all([record_a, record_b])
    db_session.flush()
    candidate = MatchCandidate(
        batch_id=uuid.uuid4(),
        record_id_1=record_a.id,
        record_id_2=record_b.id,
        score=0.7,
        tier="pending_review",
        features={},
    )
    db_session.add(candidate)
    db_session.commit()

    response = client.post(
        f"/api/review/{candidate.id}/decide",
        json={"decision": "maybe", "reviewer": "test-reviewer"},
    )
    assert response.status_code == 400


def test_pipeline_runs_endpoint_returns_list(client):
    response = client.get("/api/pipeline-runs")
    assert response.status_code == 200
    assert isinstance(response.json(), list)
