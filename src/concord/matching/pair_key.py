"""A consistently-ordered (record_id_1, record_id_2) key, used to look up an
LlmAdjudication or HumanReview for a given match_candidate regardless of
which order the two record IDs happen to be stored in. Blocking already
produces a consistent order (see blocking.py), but this normalizes
defensively rather than relying on that as an invariant callers must
remember."""


def pair_key(record_id_1: object, record_id_2: object) -> tuple[str, str]:
    a, b = str(record_id_1), str(record_id_2)
    return (a, b) if a < b else (b, a)
