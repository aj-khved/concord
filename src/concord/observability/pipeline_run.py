"""Wraps a pipeline script's execution to record a PipelineRun row —
duration, status, and a flexible summary dict — regardless of run type.
Records failures too (with the exception message) rather than only ever
seeing successful runs, since "did it fail, and how" is the more urgent
observability question in practice."""

import datetime
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from concord.db.models import PipelineRun


@dataclass
class PipelineRunContext:
    summary: dict = field(default_factory=dict)


@contextmanager
def track_pipeline_run(session: Session, run_type: str) -> Iterator[PipelineRunContext]:
    ctx = PipelineRunContext()
    started_at = datetime.datetime.now(datetime.UTC)
    error_message = None
    status = "success"
    try:
        yield ctx
    except Exception as exc:
        status = "failed"
        error_message = str(exc)
        raise
    finally:
        finished_at = datetime.datetime.now(datetime.UTC)
        duration_ms = int((finished_at - started_at).total_seconds() * 1000)
        session.add(
            PipelineRun(
                run_type=run_type,
                status=status,
                started_at=started_at,
                finished_at=finished_at,
                duration_ms=duration_ms,
                summary=ctx.summary,
                error_message=error_message,
            )
        )
        session.commit()
