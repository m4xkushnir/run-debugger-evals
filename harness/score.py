"""Score one cached reply against its case's ground truth. Deterministic, no model calls."""

from harness.parse import evidence_grounded, mode_from_prose, section_order_ok, trailing_json
from harness.prompt import user_message


def score(record, case):
    text = record["text"]
    gt = case["ground_truth"]
    js = trailing_json(text)
    prose_mode = mode_from_prose(text)
    mode = js["failure_mode"] if js and js["failure_mode"] else None
    if record["variant"] == "no_json":
        mode = prose_mode
    fix = js["fix_target"] if js else None
    return {
        "case_id": case["id"],
        "slice": case["slice"],
        "gt_mode": gt["failure_mode"],
        "model": record["model"],
        "variant": record["variant"],
        "repeat": record["repeat"],
        "pred_mode": mode,
        "prose_mode": prose_mode,
        "pred_fix": fix,
        "confidence": js["confidence"] if js else None,
        "json_ok": js is not None and js["failure_mode"] is not None,
        "correct": mode in gt["acceptable"],
        "strict_correct": mode == gt["failure_mode"],
        "fix_correct": fix in gt["fix_acceptable"],
        "sections_ok": section_order_ok(text),
        "grounded": evidence_grounded(text, user_message(case)),
        "cost_usd": record["cost_usd"] or 0.0,
        "latency_ms": record["duration_api_ms"] or 0,
        "wall_ms": record["wall_ms"] or 0,
        "output_tokens": record["usage"]["output_tokens"],
    }
