"""Offline routing simulation over cached replies. No model calls.

grid[model][case_id] is a list of scored replies (one per repeat). A policy maps one
case + repeat index to (correct, cost, latency, escalated). Results are averaged over
repeats, so each case contributes its expected outcome under the policy.
"""

import hashlib
import random
import statistics


def _rep(rows, r):
    return rows[r % len(rows)]


def single(model):
    def policy(grid, cid, r):
        x = _rep(grid[model][cid], r)
        return x["correct"], x["cost_usd"], x["latency_ms"], False
    policy.label = f"{model} only"
    return policy


def confidence_gate(tau, cheap="haiku", strong="sonnet"):
    """Cheap model first; escalate when its self-reported confidence < tau or its reply didn't parse."""
    def policy(grid, cid, r):
        a = _rep(grid[cheap][cid], r)
        if a["json_ok"] and a["confidence"] is not None and a["confidence"] >= tau:
            return a["correct"], a["cost_usd"], a["latency_ms"], False
        b = _rep(grid[strong][cid], r)
        return b["correct"], a["cost_usd"] + b["cost_usd"], a["latency_ms"] + b["latency_ms"], True
    policy.label = f"{cheap} → {strong} if confidence < {tau:.2f}"
    return policy


def agreement_gate(cheap="haiku", strong="sonnet"):
    """Two cheap samples in parallel; escalate when they disagree on the failure mode."""
    def policy(grid, cid, r):
        rows = grid[cheap][cid]
        a, b = _rep(rows, r), _rep(rows, r + 1)
        cost = a["cost_usd"] + b["cost_usd"]
        lat = max(a["latency_ms"], b["latency_ms"])
        if a["json_ok"] and b["json_ok"] and a["pred_mode"] == b["pred_mode"]:
            return a["correct"], cost, lat, False
        s = _rep(grid[strong][cid], r)
        return s["correct"], cost + s["cost_usd"], lat + s["latency_ms"], True
    policy.label = f"2× {cheap}, → {strong} on disagreement"
    return policy


def category_gate(weak, cheap="haiku", strong="sonnet"):
    """Escalate when the cheap model's predicted failure mode is in a set it's weak on."""
    weak = frozenset(weak)

    def policy(grid, cid, r):
        a = _rep(grid[cheap][cid], r)
        if a["json_ok"] and a["pred_mode"] not in weak:
            return a["correct"], a["cost_usd"], a["latency_ms"], False
        b = _rep(grid[strong][cid], r)
        return b["correct"], a["cost_usd"] + b["cost_usd"], a["latency_ms"] + b["latency_ms"], True
    policy.label = f"{cheap} → {strong} if predicted ∈ {{{', '.join(sorted(weak))}}}"
    return policy


def per_case(policy, grid, case_ids, repeats):
    out = {}
    for cid in case_ids:
        rs = [policy(grid, cid, r) for r in range(repeats)]
        out[cid] = {
            "acc": sum(x[0] for x in rs) / repeats,
            "cost": sum(x[1] for x in rs) / repeats,
            "lat": [x[2] for x in rs],
            "esc": sum(x[3] for x in rs) / repeats,
        }
    return out


def summarize(pc):
    ids = sorted(pc)
    lats = sorted(l for c in ids for l in pc[c]["lat"])
    return {
        "accuracy": statistics.fmean(pc[c]["acc"] for c in ids),
        "cost_per_run": statistics.fmean(pc[c]["cost"] for c in ids),
        "p50_ms": lats[len(lats) // 2],
        "p95_ms": lats[min(len(lats) - 1, int(0.95 * len(lats)))],
        "escalation_rate": statistics.fmean(pc[c]["esc"] for c in ids),
    }


def bootstrap_delta(pc_a, pc_b, n=2000, seed=0):
    """Case-level bootstrap of (accuracy A − accuracy B) and (1 − cost A / cost B)."""
    ids = sorted(pc_a)
    rng = random.Random(seed)
    d_acc, savings = [], []
    for _ in range(n):
        s = [rng.choice(ids) for _ in ids]
        acc_a = sum(pc_a[c]["acc"] for c in s)
        acc_b = sum(pc_b[c]["acc"] for c in s)
        cost_a = sum(pc_a[c]["cost"] for c in s)
        cost_b = sum(pc_b[c]["cost"] for c in s)
        d_acc.append((acc_a - acc_b) / len(s))
        savings.append(1 - cost_a / cost_b)
    d_acc.sort()
    savings.sort()
    lo, hi = int(0.025 * n), int(0.975 * n) - 1
    return (d_acc[lo], d_acc[hi]), (savings[lo], savings[hi])


def fold_of(case_id):
    return int(hashlib.sha256(case_id.encode()).hexdigest(), 16) % 2


def cross_fit(grid, case_ids, repeats, candidates, target_policy, max_drop):
    """Choose a policy on one half of the cases, evaluate it on the other half, then swap.

    `candidates` are factories: f(train_case_ids) -> policy, so data-dependent policies
    (e.g. the weak-category set) are fitted on the training half only.

    Rule: the cheapest candidate whose train accuracy is within `max_drop` of the target
    policy's train accuracy; if none qualifies, the most accurate candidate. Returns the
    combined held-out per-case results and the choice made on each fold.
    """
    folds = [[c for c in case_ids if fold_of(c) == k] for k in (0, 1)]
    held_out, choices = {}, []
    for k in (0, 1):
        train, test = folds[k], folds[1 - k]
        target = summarize(per_case(target_policy, grid, train, repeats))["accuracy"]
        policies = [f(train) for f in candidates]
        scored = [(summarize(per_case(p, grid, train, repeats)), p) for p in policies]
        ok = [(s, p) for s, p in scored if s["accuracy"] >= target - max_drop]
        s, p = min(ok, key=lambda x: x[0]["cost_per_run"]) if ok else max(scored, key=lambda x: x[0]["accuracy"])
        choices.append(p.label)
        held_out.update(per_case(p, grid, test, repeats))
    return held_out, choices


def weak_categories(grid, case_ids, cheap="haiku", strong="sonnet", min_n=3):
    """Predicted labels where the cheap model's precision is below the strong model's
    accuracy on the same cases (computed on the given cases only)."""
    by_pred = {}
    for cid in case_ids:
        for a, b in zip(grid[cheap][cid], grid[strong][cid]):
            if a["pred_mode"] is None:
                continue
            by_pred.setdefault(a["pred_mode"], []).append((a["correct"], b["correct"]))
    weak = set()
    for label, pairs in by_pred.items():
        if len(pairs) >= min_n:
            cheap_acc = sum(p[0] for p in pairs) / len(pairs)
            strong_acc = sum(p[1] for p in pairs) / len(pairs)
            if cheap_acc < strong_acc:
                weak.add(label)
    return weak
