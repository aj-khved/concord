"""rekey llm_adjudications and human_reviews by record pair

Re-keys these two tables from match_candidate_id (an ephemeral per-batch id
that changes every time the matching engine re-runs) to (record_id_1,
record_id_2) -- the stable underlying pair identity. Backfills existing rows
by joining through match_candidates (which still has the old batch data)
before dropping the old column, so no existing adjudications/reviews are
lost. See the LlmAdjudication/HumanReview docstrings in db/models.py for why.

Revision ID: 6f45a225b727
Revises: dfaf652b5391
Create Date: 2026-09-29 21:38:27.752016

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "6f45a225b727"
down_revision: Union[str, Sequence[str], None] = "dfaf652b5391"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    for table in ("human_reviews", "llm_adjudications"):
        # Nullable at first -- existing rows don't have these values yet.
        op.add_column(table, sa.Column("record_id_1", sa.UUID(), nullable=True))
        op.add_column(table, sa.Column("record_id_2", sa.UUID(), nullable=True))

        op.execute(
            f"""
            UPDATE {table} t
            SET record_id_1 = mc.record_id_1,
                record_id_2 = mc.record_id_2
            FROM match_candidates mc
            WHERE mc.id = t.match_candidate_id
            """
        )

        op.alter_column(table, "record_id_1", nullable=False)
        op.alter_column(table, "record_id_2", nullable=False)

    op.drop_constraint("uq_reviewed_candidate", "human_reviews", type_="unique")
    op.drop_constraint(
        "human_reviews_match_candidate_id_fkey", "human_reviews", type_="foreignkey"
    )
    op.create_unique_constraint(
        "uq_reviewed_pair", "human_reviews", ["record_id_1", "record_id_2"]
    )
    op.create_foreign_key(
        None, "human_reviews", "normalized_vendor_records", ["record_id_1"], ["id"]
    )
    op.create_foreign_key(
        None, "human_reviews", "normalized_vendor_records", ["record_id_2"], ["id"]
    )
    op.drop_column("human_reviews", "match_candidate_id")

    op.drop_constraint("uq_adjudicated_candidate", "llm_adjudications", type_="unique")
    op.drop_constraint(
        "llm_adjudications_match_candidate_id_fkey", "llm_adjudications", type_="foreignkey"
    )
    op.create_unique_constraint(
        "uq_adjudicated_pair", "llm_adjudications", ["record_id_1", "record_id_2"]
    )
    op.create_foreign_key(
        None, "llm_adjudications", "normalized_vendor_records", ["record_id_1"], ["id"]
    )
    op.create_foreign_key(
        None, "llm_adjudications", "normalized_vendor_records", ["record_id_2"], ["id"]
    )
    op.drop_column("llm_adjudications", "match_candidate_id")


def downgrade() -> None:
    # Not a faithful inverse: multiple match_candidates rows (one per batch)
    # can reference the same record pair, so reconstructing a single
    # match_candidate_id per adjudication/review is ambiguous. This restores
    # the old column shape only, left NULL, for schema-only rollback.
    for table, constraint, fk_name in (
        ("llm_adjudications", "uq_adjudicated_pair", "llm_adjudications_match_candidate_id_fkey"),
        ("human_reviews", "uq_reviewed_pair", "human_reviews_match_candidate_id_fkey"),
    ):
        op.add_column(table, sa.Column("match_candidate_id", sa.UUID(), nullable=True))
        op.create_foreign_key(fk_name, table, "match_candidates", ["match_candidate_id"], ["id"])
        op.drop_constraint(constraint, table, type_="unique")
        op.drop_column(table, "record_id_1")
        op.drop_column(table, "record_id_2")
