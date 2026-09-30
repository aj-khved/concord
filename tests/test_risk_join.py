from concord.risk.join import GoldenVendorLike, RiskFeedRow, join_risk_feed_to_golden_vendors


def _risk_row(tax_id: str) -> RiskFeedRow:
    return RiskFeedRow(
        tax_id=tax_id,
        legal_name="Acme Inc.",
        sanctions_flag=False,
        country_risk_tier="Low",
        financial_stability_score=90,
        notes="No adverse findings.",
    )


def test_matches_by_tax_id():
    risk_rows = [_risk_row("123456789")]
    golden_vendors = [GoldenVendorLike(id="g1", tax_id="123456789")]
    result = join_risk_feed_to_golden_vendors(risk_rows, golden_vendors)
    assert result.matched == [("g1", risk_rows[0])]
    assert result.unmatched_tax_ids == []


def test_reports_unmatched_when_no_golden_vendor_has_that_tax_id():
    risk_rows = [_risk_row("999999999")]
    golden_vendors = [GoldenVendorLike(id="g1", tax_id="123456789")]
    result = join_risk_feed_to_golden_vendors(risk_rows, golden_vendors)
    assert result.matched == []
    assert result.unmatched_tax_ids == ["999999999"]


def test_golden_vendors_with_no_tax_id_are_ignored_not_matched():
    risk_rows = [_risk_row("123456789")]
    golden_vendors = [GoldenVendorLike(id="g1", tax_id=None)]
    result = join_risk_feed_to_golden_vendors(risk_rows, golden_vendors)
    assert result.matched == []
    assert result.unmatched_tax_ids == ["123456789"]
