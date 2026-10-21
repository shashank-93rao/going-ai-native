from cache_incident import CachingFakeClient, simulate


def test_timestamp_in_prefix_kills_cache_and_multiplies_cost():
    good, bad = simulate("v14", n=300), simulate("v15", n=300)
    assert good["cache_hit_rate"] > 0.99 and bad["cache_hit_rate"] == 0
    assert bad["cost_per_request_usd"] > 3 * good["cost_per_request_usd"]


def test_ttl_expiry_and_minimum_length():
    t = {"now": 0.0}
    c = CachingFakeClient(lambda: t["now"])
    msg = [{"role": "user", "content": "hi"}]
    sysp = "x" * 4000  # 1000 tokens
    assert c.complete(msg, system=sysp).usage.cache_creation_input_tokens == 1000
    t["now"] = 299
    assert c.complete(msg, system=sysp).usage.cache_read_input_tokens == 1000  # read refreshes TTL
    t["now"] = 598
    assert c.complete(msg, system=sysp).usage.cache_read_input_tokens == 1000
    t["now"] = 1000
    assert c.complete(msg, system=sysp).usage.cache_creation_input_tokens == 1000  # expired
    short = c.complete(msg, system="tiny")
    assert short.usage.cache_creation_input_tokens == 0 and short.usage.cache_read_input_tokens == 0
