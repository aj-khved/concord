from concord.observability.cost import estimate_cost_usd


def test_zero_tokens_costs_nothing():
    assert estimate_cost_usd(0, 0) == 0.0


def test_cost_scales_with_tokens():
    small = estimate_cost_usd(1000, 100)
    large = estimate_cost_usd(10000, 1000)
    assert large > small


def test_output_tokens_cost_more_per_token_than_input():
    input_only = estimate_cost_usd(1_000_000, 0)
    output_only = estimate_cost_usd(0, 1_000_000)
    assert output_only > input_only
