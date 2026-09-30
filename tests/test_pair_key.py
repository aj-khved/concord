from concord.matching.pair_key import pair_key


def test_pair_key_is_order_independent():
    assert pair_key("a", "b") == pair_key("b", "a")


def test_pair_key_returns_sorted_tuple():
    assert pair_key("b", "a") == ("a", "b")
