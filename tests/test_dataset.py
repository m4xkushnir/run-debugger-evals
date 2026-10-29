from collections import Counter

from harness.prompt import FAILURE_MODES, FIX_TARGETS, load_cases, user_message

CASES = load_cases()
TAXONOMY_PHRASES = [
    "connection failure", "aop ambiguity", "ambiguous", "terminal closure", "missing hitl",
    "missing data", "iteration leak", "batch", "decomposition", "platform / infra", "infra failure",
    "failure mode", "taxonomy", "root cause",
]


def test_size_and_ids():
    assert 30 <= len(CASES) <= 50
    assert len({c["id"] for c in CASES}) == len(CASES)


def test_every_case_is_marked_synthetic():
    for c in CASES:
        assert c["synthetic"] is True
        assert "synthetic" in c["provenance"]


def test_labels_are_valid():
    for c in CASES:
        gt = c["ground_truth"]
        assert gt["failure_mode"] in FAILURE_MODES
        assert gt["failure_mode"] in gt["acceptable"]
        assert set(gt["acceptable"]) <= set(FAILURE_MODES)
        assert gt["fix_target"] in gt["fix_acceptable"]
        assert set(gt["fix_acceptable"]) <= set(FIX_TARGETS)


def test_each_taxonomy_category_has_at_least_three_cases():
    counts = Counter(c["ground_truth"]["failure_mode"] for c in CASES)
    for mode in FAILURE_MODES[:8]:
        assert counts[mode] >= 3, mode


def test_decision_point_is_visible_in_the_input():
    for c in CASES:
        assert c["ground_truth"]["decision_point"] in user_message(c), c["id"]


def test_no_label_leakage_into_the_input():
    for c in CASES:
        msg = user_message(c).lower()
        for phrase in TAXONOMY_PHRASES:
            assert phrase not in msg, (c["id"], phrase)
