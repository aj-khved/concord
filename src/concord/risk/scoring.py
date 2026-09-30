"""Deterministic risk scoring (FR9). This is the actual risk decision — the
LLM (concord/risk/summarizer.py) only ever narrates a score computed here; it
never influences the score or level itself. That separation is the whole
security story for this module: a misleading or adversarial note can affect
generated wording, never the underlying categorization."""

from dataclasses import dataclass

_COUNTRY_RISK_POINTS = {"Low": 0, "Medium": 15, "High": 30}
_SANCTIONS_PENALTY = 50


@dataclass
class RiskAssessment:
    risk_score: int
    risk_level: str


def compute_risk(
    sanctions_flag: bool, country_risk_tier: str, financial_stability_score: int
) -> RiskAssessment:
    score = (100 - financial_stability_score) + _COUNTRY_RISK_POINTS.get(country_risk_tier, 0)
    if sanctions_flag:
        score += _SANCTIONS_PENALTY
    score = max(0, min(100, score))

    if sanctions_flag or score >= 85:
        level = "Critical"
    elif score >= 60:
        level = "High"
    elif score >= 30:
        level = "Medium"
    else:
        level = "Low"

    return RiskAssessment(risk_score=score, risk_level=level)
