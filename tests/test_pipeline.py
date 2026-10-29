"""Cache, budget, the run loop and report determinism, against a fake backend."""

import threading

import pytest

from harness import report
from harness.budget import Budget, BudgetExceeded
from harness.cache import Cache, cache_key
from harness.prompt import load_cases
from harness.run import execute, plan


class FakeBackend:
    """Answers with the ground truth for even repeats and a wrong label for odd ones."""

    name = "fake"

    def __init__(self):
        self.calls = 0
        self.lock = threading.Lock()

    def call(self, model, system, user):
        with self.lock:
            self.calls += 1
        case = next(c for c in load_cases() if c["run"]["run_id"] in user)
        mode = case["ground_truth"]["failure_mode"]
        if self.calls % 2 == 0 and model == "haiku":
            mode = "named_pattern" if mode != "named_pattern" else "missing_data"
        text = (
            f"**Failure mode:** {mode}\n**Where it went wrong:** step 1\n"
            f"**Evidence:** \"{case['ground_truth']['decision_point']}\"\n**Fix:** x\n**Next step:** y\n"
            f'{{"failure_mode": "{mode}", "fix_target": "{case["ground_truth"]["fix_target"]}", "confidence": 0.8}}'
        )
        return {
            "text": text, "canonical_model": f"fake-{model}", "cost_usd": 0.001 if model == "haiku" else 0.004,
            "duration_api_ms": 1000, "wall_ms": 1100, "backend": self.name,
            "usage": {"input_tokens": 1, "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0,
                      "output_tokens": 10, "thinking_tokens": 0},
        }


def quiet(*_):
    pass


def test_cache_key_depends_on_every_component():
    base = cache_key("haiku", "pv1", "ih1", 0)
    assert base == cache_key("haiku", "pv1", "ih1", 0)
    assert len({base, cache_key("sonnet", "pv1", "ih1", 0), cache_key("haiku", "pv2", "ih1", 0),
                cache_key("haiku", "pv1", "ih2", 0), cache_key("haiku", "pv1", "ih1", 1)}) == 5


def test_budget_refuses_calls_past_the_cap():
    b = Budget(cap_usd=0.10)
    b.reserve(0.06)
    with pytest.raises(BudgetExceeded):
        b.reserve(0.05)
    b.settle(0.06, 0.02)
    b.reserve(0.05)
    assert b.spent == pytest.approx(0.02)


def test_budget_stops_the_run_and_keeps_completed_cells(tmp_path):
    cases = load_cases()[:5]
    cache = Cache(tmp_path)
    done, failed = execute(plan(cases, ["sonnet"], 1, "main"), FakeBackend(), cache,
                           Budget(cap_usd=0.06), workers=1, log=quiet)
    assert failed == 0 and 0 < done < 5
    assert len(list(tmp_path.glob("*/*.json"))) == done


def test_second_run_is_fully_cached(tmp_path):
    cases = load_cases()[:4]
    jobs = plan(cases, ["haiku", "sonnet"], 2, "main")
    cache, backend = Cache(tmp_path), FakeBackend()
    execute(jobs, backend, cache, Budget(10), log=quiet)
    first = backend.calls
    execute(jobs, backend, cache, Budget(10), log=quiet)
    assert first == len(jobs) and backend.calls == first


def test_report_is_byte_identical_from_the_same_cache(tmp_path):
    cases = load_cases()[:8]
    execute(plan(cases, ["haiku", "sonnet"], 3, "main"), FakeBackend(), Cache(tmp_path), Budget(10), log=quiet)
    _, md1 = report.build(tmp_path, cases)
    _, md2 = report.build(tmp_path, cases)
    assert md1 == md2
    assert "## 4. Routing" in md1


def test_report_ignores_replies_for_changed_inputs(tmp_path):
    cases = load_cases()[:2]
    execute(plan(cases, ["sonnet"], 1, "main"), FakeBackend(), Cache(tmp_path), Budget(10), log=quiet)
    edited = [dict(cases[0], aop=cases[0]["aop"] + "\n5. New step."), cases[1]]
    rows, _, _ = report.load_scored(tmp_path, edited)
    assert [r["case_id"] for r in rows] == [cases[1]["id"]]
