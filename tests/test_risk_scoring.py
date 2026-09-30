from concord.risk.scoring import compute_risk


def test_clean_vendor_is_low_risk():
    result = compute_risk(
        sanctions_flag=False, country_risk_tier="Low", financial_stability_score=95
    )
    assert result.risk_level == "Low"
    assert result.risk_score == 5


def test_sanctions_flag_forces_critical_regardless_of_other_inputs():
    result = compute_risk(
        sanctions_flag=True, country_risk_tier="Low", financial_stability_score=95
    )
    assert result.risk_level == "Critical"


def test_high_country_tier_adds_points():
    low = compute_risk(sanctions_flag=False, country_risk_tier="Low", financial_stability_score=70)
    high = compute_risk(
        sanctions_flag=False, country_risk_tier="High", financial_stability_score=70
    )
    assert high.risk_score > low.risk_score


def test_poor_financial_stability_alone_can_reach_high_without_sanctions():
    result = compute_risk(
        sanctions_flag=False, country_risk_tier="Low", financial_stability_score=10
    )
    assert result.risk_score == 90
    assert result.risk_level in ("High", "Critical")


def test_score_is_clamped_to_0_100():
    result = compute_risk(
        sanctions_flag=True, country_risk_tier="High", financial_stability_score=0
    )
    assert 0 <= result.risk_score <= 100
