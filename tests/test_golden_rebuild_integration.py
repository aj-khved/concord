"""Integration test against a real Postgres (dedicated throwaway database,
same pattern as test_pipeline_integration.py).

Regression test for a real bug found by manually testing the review UI in a
browser: match_candidates is append-only (one batch per matching-engine
run), and the golden-vendor rebuild must only consider the LATEST batch —
otherwise a record pair resolved in an older, superseded batch gets counted
alongside the current one, corrupting the match/non-match/needs-review
counts (this actually happened during development after re-running the
matching engine twice against the same data)."""

import datetime
import uuid

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from concord.config import settings
from concord.db.models import Base, MatchCandidate, NormalizedVendorRecord
from concord.golden.rebuild import rebuild_golden_vendors

TEST_DB_NAME = "concord_test_golden"


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


def _make_record(session, source, source_record_id, legal_name) -> NormalizedVendorRecord:
    record = NormalizedVendorRecord(
        source=source,
        source_record_id=source_record_id,
        legal_name=legal_name,
        category="Manufacturing",
    )
    session.add(record)
    session.flush()
    return record


def test_rebuild_only_uses_the_latest_batch(db_session):
    record_a = _make_record(db_session, "A", "A-1", "Acme Inc.")
    record_b = _make_record(db_session, "B", "B-1", "Acme LLC")
    db_session.commit()

    # Explicit, clearly-ordered timestamps rather than relying on wall-clock
    # `now()` defaults: two inserts in a fast test can land in the same
    # microsecond, and ORDER BY created_at DESC has no tiebreaker in that
    # case. Real matching-engine runs are never microseconds apart, so this
    # is a test-determinism fix, not a production concern.
    an_hour_ago = datetime.datetime.now(datetime.UTC) - datetime.timedelta(hours=1)
    now = datetime.datetime.now(datetime.UTC)

    # First (older, superseded) matching run: tier says non-match.
    old_batch_id = uuid.uuid4()
    db_session.add(
        MatchCandidate(
            batch_id=old_batch_id,
            record_id_1=record_a.id,
            record_id_2=record_b.id,
            score=0.2,
            tier="auto_reject",
            features={},
            created_at=an_hour_ago,
        )
    )
    db_session.commit()

    # Second (newer) matching run: tier says match. This is the one that
    # should count.
    new_batch_id = uuid.uuid4()
    db_session.add(
        MatchCandidate(
            batch_id=new_batch_id,
            record_id_1=record_a.id,
            record_id_2=record_b.id,
            score=0.95,
            tier="auto_merge",
            features={},
            created_at=now,
        )
    )
    db_session.commit()

    summary = rebuild_golden_vendors(db_session)

    # If the stale batch were also counted, these two records would each
    # form their own singleton golden vendor (2 total) instead of merging.
    assert summary.golden_vendor_count == 1
    assert summary.largest_cluster_size == 2
