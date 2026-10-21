from code_as_action import SCRIPT, demo, make_api, make_cluster, measure_code, measure_direct, run_code_action


def test_code_moves_data_out_of_context():
    api = make_api(make_cluster())
    direct, code = measure_direct(api), measure_code(api)
    assert direct["tool_calls"] == 1 + 6 + 6 * 48
    assert code["context_tokens"] * 50 < direct["context_tokens"]
    assert direct["cumulative_input_tokens"] > 100 * direct["context_tokens"]


def test_script_finds_the_needles():
    out, err = run_code_action(SCRIPT, make_api(make_cluster()))
    assert not err and "('group-03', 17, 52000)" in out and "('group-05', 2, 14500)" in out


def test_errors_and_output_caps_are_actionable():
    api = make_api(make_cluster())
    out, err = run_code_action("kafka_partition_lag('nope', 0)", api)
    assert err and "KeyError" in out and "Available functions" in out
    out, err = run_code_action("print('x' * 10000)", api, max_output_chars=100)
    assert not err and "output truncated" in out
    out, err = run_code_action("import os", api)
    assert err  # no __import__ in the trimmed builtins (still not a sandbox)
    assert run_code_action("x = 1", api)[0].startswith("(script printed nothing")


def test_agent_fixes_its_script_from_the_error():
    r = demo()["agent"]
    assert [t["is_error"] for t in r.tool_log] == [True, False]
    assert "consumer_lag" in r.tool_log[0]["content"] and "group-03" in r.final_text
