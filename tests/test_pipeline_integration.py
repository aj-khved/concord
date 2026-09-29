"""Integration test against a real Postgres. Runs against a dedicated,
throwaway 'concord_test' database (created and dropped by this test) so it
never touches the dev database's data. Uses Base.metadata.create_all rather
than Alembic migrations, since this schema is ephemeral and test-only —
Alembic is for the real, versioned dev/prod schema (see migrations/).

Skips automatically if Postgres isn't reachable (e.g. `docker compose up`
hasn't been run).
"""

from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from concord.config import settings
from concord.db.models import Base
from concord.pipeline import run_ingestion

TEST_DB_NAME = "concord_test"


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
def tiny_data_dir(tmp_path):
    fixtures_dir = Path(__file__).parent / "fixtures" / "tiny_sources"
    for f in fixtures_dir.iterdir():
        (tmp_path / f.name).write_text(f.read_text(encoding="utf-8"), encoding="utf-8")
    return tmp_path


def test_ingestion_upserts_canonical_and_appends_raw(db_session, tiny_data_dir):
    summary_1 = run_ingestion(tiny_data_dir, db_session)
    summary_2 = run_ingestion(tiny_data_dir, db_session)

    total_records = sum(v["records_checked"] for v in summary_1.per_source.values())
    assert total_records == 4  # 2 from source A, 1 from B, 1 from C

    raw_count = db_session.execute(text("SELECT count(*) FROM raw_vendor_records")).scalar()
    normalized_count = db_session.execute(
        text("SELECT count(*) FROM normalized_vendor_records")
    ).scalar()

    assert raw_count == total_records * 2  # append-only: two runs, no dedup
    assert normalized_count == total_records  # upserted: no duplication on re-run
    assert summary_2.per_source == summary_1.per_source
