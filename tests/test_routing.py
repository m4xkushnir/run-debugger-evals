import pytest

from harness import routing


def reply(correct, cost, conf=0.9, mode="m", lat=1000):
    return {"correct": correct, "cost_usd": cost, "latency_ms": lat, "confidence": conf,
            "json_ok": True, "pred_mode": mode}


def grid_two_cases():
    # case a: haiku right and confident; case b: haiku wrong and unsure, sonnet right.
    return {
        "haiku": {"a": [reply(True, 0.01, 0.95, "x")] * 2,
                  "b": [reply(False, 0.01, 0.40, "y"), reply(False, 0.01, 0.40, "z")]},
        "sonnet": {"a": [reply(True, 0.04)] * 2, "b": [reply(True, 0.04)] * 2},
    }


def test_single_model():
    g = grid_two_cases()
    s = routing.summarize(routing.per_case(routing.single("haiku"), g, ["a", "b"], 2))
    assert s["accuracy"] == 0.5 and s["cost_per_run"] == pytest.approx(0.01)


def test_confidence_gate_escalates_only_low_confidence_and_pays_for_both():
    g = grid_two_cases()
    pc = routing.per_case(routing.confidence_gate(0.8), g, ["a", "b"], 2)
    assert pc["a"] == {"acc": 1.0, "cost": 0.01, "lat": [1000, 1000], "esc": 0.0}
    assert pc["b"]["acc"] == 1.0 and pc["b"]["cost"] == pytest.approx(0.05) and pc["b"]["lat"] == [2000, 2000]


def test_agreement_gate_escalates_on_disagreement():
    g = grid_two_cases()
    pc = routing.per_case(routing.agreement_gate(), g, ["a", "b"], 2)
    assert pc["a"]["esc"] == 0.0 and pc["a"]["cost"] == pytest.approx(0.02)
    assert pc["b"]["esc"] == 1.0 and pc["b"]["acc"] == 1.0


def test_unparsed_cheap_reply_always_escalates():
    g = grid_two_cases()
    g["haiku"]["a"] = [dict(reply(True, 0.01, 0.99), json_ok=False)] * 2
    assert routing.per_case(routing.confidence_gate(0.5), g, ["a"], 2)["a"]["esc"] == 1.0


def test_bootstrap_is_deterministic_and_brackets_the_point_estimate():
    g = grid_two_cases()
    a = routing.per_case(routing.single("haiku"), g, ["a", "b"], 2)
    b = routing.per_case(routing.single("sonnet"), g, ["a", "b"], 2)
    assert routing.bootstrap_delta(a, b) == routing.bootstrap_delta(a, b)
    (lo, hi), (slo, shi) = routing.bootstrap_delta(a, b)
    assert lo <= -0.5 <= hi and slo == pytest.approx(0.75) == shi


def test_cross_fit_never_scores_on_training_cases():
    seen = []

    def factory(train):
        seen.append(set(train))
        return routing.single("haiku")

    ids = [f"c{i}" for i in range(10)]
    g = {m: {c: [reply(True, 0.01)] for c in ids} for m in ("haiku", "sonnet")}
    held, _ = routing.cross_fit(g, ids, 1, [factory], routing.single("sonnet"), 0.02)
    assert set(held) == set(ids)
    assert seen[0].isdisjoint(seen[1]) and seen[0] | seen[1] == set(ids)


def test_weak_categories():
    g = {
        "haiku": {"a": [reply(False, 0, mode="platform_infra")] * 3, "b": [reply(True, 0, mode="missing_data")] * 3},
        "sonnet": {"a": [reply(True, 0)] * 3, "b": [reply(True, 0)] * 3},
    }
    assert routing.weak_categories(g, ["a", "b"]) == {"platform_infra"}
