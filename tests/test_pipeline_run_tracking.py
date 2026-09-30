import pytest
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import sessionmaker

from concord.config import settings
from concord.db.models import Base, PipelineRun
from concord.observability.pipeline_run import track_pipeline_run

TEST_DB_NAME = "concord_test_pipeline_run"


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


def test_records_a_successful_run(db_session):
    with track_pipeline_run(db_session, "ingestion") as run:
        run.summary = {"records_ingested": 42}

    row = db_session.execute(
        select(PipelineRun).where(PipelineRun.run_type == "ingestion")
    ).scalar_one()
    assert row.status == "success"
    assert row.summary == {"records_ingested": 42}
    assert row.error_message is None
    assert row.duration_ms >= 0


def test_records_a_failed_run_and_reraises(db_session):
    with pytest.raises(ValueError, match="boom"):
        with track_pipeline_run(db_session, "matching"):
            raise ValueError("boom")

    row = db_session.execute(
        select(PipelineRun).where(PipelineRun.run_type == "matching")
    ).scalar_one()
    assert row.status == "failed"
    assert row.error_message == "boom"
