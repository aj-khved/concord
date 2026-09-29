"""Orchestrates blocking -> scoring -> tiering for a set of normalized
vendor records. Pure function over VendorRecordView objects — no database
dependency, so it's directly unit-testable and directly evaluable against
the M1 ground truth."""

from concord.matching.blocking import generate_candidate_pairs
from concord.matching.schema import MatchResult, MatchTier, VendorRecordView
from concord.matching.scoring import AUTO_MERGE_THRESHOLD, AUTO_REJECT_THRESHOLD, score_pair


def tier_for_score(score: float) -> MatchTier:
    if score >= AUTO_MERGE_THRESHOLD:
        return MatchTier.AUTO_MERGE
    if score <= AUTO_REJECT_THRESHOLD:
        return MatchTier.AUTO_REJECT
    return MatchTier.PENDING_REVIEW


def run_matching(records: list[VendorRecordView]) -> list[MatchResult]:
    by_id = {r.id: r for r in records}
    pairs = generate_candidate_pairs(records)

    results = []
    for id_a, id_b in pairs:
        pair_score = score_pair(by_id[id_a], by_id[id_b])
        results.append(
            MatchResult(
                record_id_1=id_a,
                record_id_2=id_b,
                score=pair_score.score,
                tier=tier_for_score(pair_score.score),
                features=pair_score.features,
            )
        )
    return results
