"""Build reports/REPORT.md and reports/summary.json from the cache. Makes no model calls;
same cache in → byte-identical report out."""

import json
import random
import statistics
import sys
from collections import Counter, defaultdict

from harness import routing
from harness.cache import Cache
from harness.prompt import ROOT, SKILL_COMMIT, input_hash, load_cases, prompt_version
from harness.score import score

MODELS = ["haiku", "sonnet", "opus"]
MAX_DROP = 0.02  # routing target: within 2 pp of Sonnet-only accuracy
# Labels a model argued convincingly against after the run. Labels stay frozen; the
# report shows accuracy with these alternates accepted as a sensitivity check.
DISPUTED = {"C03": ["missing_data"]}


def load_scored(cache_root=ROOT / "cache", cases=None):
    cases = {c["id"]: c for c in (cases or load_cases())}
    pv = {v: prompt_version(v) for v in ("main", "no_json")}
    ih = {cid: input_hash(c) for cid, c in cases.items()}
    rows, records = [], []
    for p in sorted(Cache(cache_root).root.glob("*/*.json")):
        rec = json.loads(p.read_text())
        if (rec["case_id"] not in cases or rec["prompt_version"] != pv[rec["variant"]]
                or rec["input_hash"] != ih[rec["case_id"]]):
            continue  # stale: prompt or case changed since this reply was cached
        records.append(rec)
        rows.append(score(rec, cases[rec["case_id"]]))
    rows.sort(key=lambda r: (r["variant"], r["model"], r["case_id"], r["repeat"]))
    return rows, records, cases


def grid_of(rows, variant="main"):
    g = defaultdict(lambda: defaultdict(list))
    for r in rows:
        if r["variant"] == variant:
            g[r["model"]][r["case_id"]].append(r)
    return g


def case_bootstrap_ci(per_case_values, n=2000, seed=0):
    ids = sorted(per_case_values)
    rng = random.Random(seed)
    means = sorted(
        statistics.fmean(per_case_values[rng.choice(ids)] for _ in ids) for _ in range(n)
    )
    return means[int(0.025 * n)], means[int(0.975 * n) - 1]


def pct(x):
    return f"{100 * x:.1f}%"


def money(x):
    return f"${x:.4f}"


def headline(grid, model):
    by_case = grid[model]
    rows = [r for rs in by_case.values() for r in rs]
    acc_by_case = {c: statistics.fmean(r["correct"] for r in rs) for c, rs in by_case.items()}
    lo, hi = case_bootstrap_ci(acc_by_case)
    grounded = [r["grounded"] for r in rows if r["grounded"] is not None]
    lats = sorted(r["latency_ms"] for r in rows)
    stable = [len({r["pred_mode"] for r in rs}) == 1 for rs in by_case.values()]
    return {
        "model": model,
        "replies": len(rows),
        "repeats": max(len(rs) for rs in by_case.values()),
        "accuracy": statistics.fmean(acc_by_case.values()),
        "accuracy_ci": [lo, hi],
        "strict_accuracy": statistics.fmean(r["strict_correct"] for r in rows),
        "fix_accuracy": statistics.fmean(r["fix_correct"] for r in rows),
        "json_ok": statistics.fmean(r["json_ok"] for r in rows),
        "sections_ok": statistics.fmean(r["sections_ok"] for r in rows),
        "grounded": statistics.fmean(grounded) if grounded else None,
        "stable_cases": statistics.fmean(stable),
        "cost_per_run": statistics.fmean(r["cost_usd"] for r in rows),
        "p50_ms": lats[len(lats) // 2],
        "p95_ms": lats[min(len(lats) - 1, int(0.95 * len(lats)))],
        "output_tokens": statistics.fmean(r["output_tokens"] for r in rows),
    }


def breakdown(grid, models, key, cases):
    """Accuracy per value of `key` (a case field or ground-truth mode) per model."""
    groups = defaultdict(list)
    for cid, c in cases.items():
        groups[c["slice"] if key == "slice" else c["ground_truth"]["failure_mode"]].append(cid)
    table = {}
    for g, ids in sorted(groups.items()):
        table[g] = {"n": len(ids)}
        for m in models:
            vals = [r["correct"] for cid in ids for r in grid[m].get(cid, [])]
            table[g][m] = statistics.fmean(vals) if vals else None
    return table


def sensitivity(grid, models):
    out = {}
    for m in models:
        vals = []
        for cid, rs in grid[m].items():
            for r in rs:
                vals.append(r["correct"] or r["pred_mode"] in DISPUTED.get(cid, []))
        out[m] = statistics.fmean(vals)
    return out


def confusions(grid, model, top=8):
    cnt = Counter()
    for rs in grid[model].values():
        for r in rs:
            if not r["correct"]:
                cnt[(r["gt_mode"], r["pred_mode"] or "unparsed")] += 1
    return cnt.most_common(top)


def calibration(grid, model):
    buckets = defaultdict(list)
    for rs in grid[model].values():
        for r in rs:
            if r["confidence"] is None:
                continue
            c = r["confidence"]
            b = "<0.6" if c < 0.6 else "0.6–0.8" if c < 0.8 else "0.8–0.9" if c < 0.9 else "≥0.9"
            buckets[b].append(r["correct"])
    order = ["<0.6", "0.6–0.8", "0.8–0.9", "≥0.9"]
    return [(b, len(buckets[b]), statistics.fmean(buckets[b])) for b in order if buckets[b]]


def routing_section(grid, cases):
    ids = sorted(cid for cid in cases if all(cid in grid[m] for m in ("haiku", "sonnet")))
    reps = min(len(grid[m][c]) for m in ("haiku", "sonnet") for c in ids)
    sonnet = routing.single("sonnet")
    sonnet_pc = routing.per_case(sonnet, grid, ids, reps)
    taus = [0.6, 0.7, 0.8, 0.85, 0.9, 0.95]
    in_sample = [routing.single("haiku"), sonnet]
    if "opus" in grid and all(c in grid["opus"] for c in ids):
        in_sample.append(routing.single("opus"))
    in_sample += [routing.confidence_gate(t) for t in taus]
    in_sample += [routing.agreement_gate()]

    def row(label, pc, kind):
        s = routing.summarize(pc)
        (dlo, dhi), (slo, shi) = routing.bootstrap_delta(pc, sonnet_pc)
        s.update({"policy": label, "kind": kind, "delta_acc_ci": [dlo, dhi], "savings_ci": [slo, shi],
                  "savings": 1 - s["cost_per_run"] / routing.summarize(sonnet_pc)["cost_per_run"]})
        return s

    out = []
    for p in in_sample:
        r = reps if "opus" not in p.label else min(len(grid["opus"][c]) for c in ids)
        out.append(row(p.label, routing.per_case(p, grid, ids, r), "in-sample"))

    candidates = [lambda train, t=t: routing.confidence_gate(t) for t in taus]
    candidates += [lambda train: routing.agreement_gate()]
    candidates += [lambda train: routing.category_gate(routing.weak_categories(grid, train))]
    held, choices = routing.cross_fit(grid, ids, reps, candidates, sonnet, MAX_DROP)
    out.append(row("cross-fitted pick (held-out)", held, "held-out"))
    cat_held, cat_choices = routing.cross_fit(
        grid, ids, reps, [lambda train: routing.category_gate(routing.weak_categories(grid, train))],
        sonnet, 1.0)
    out.append(row("category gate, weak set fitted per fold (held-out)", cat_held, "held-out"))
    return out, {"pick": choices, "category": cat_choices}, reps


def ab_section(rows):
    """JSON-suffix A/B: main-variant repeat 0 vs the no_json variant, same cases."""
    main = {(r["model"], r["case_id"]): r for r in rows if r["variant"] == "main" and r["repeat"] == 0}
    nojs = {(r["model"], r["case_id"]): r for r in rows if r["variant"] == "no_json"}
    out = []
    for m in MODELS:
        keys = sorted(k for k in nojs if k[0] == m and k in main)
        if not keys:
            continue
        a = statistics.fmean(main[k]["correct"] for k in keys)
        b = statistics.fmean(nojs[k]["correct"] for k in keys)
        # within the main variant: does the JSON label agree with the prose label?
        agree = statistics.fmean(main[k]["pred_mode"] == main[k]["prose_mode"] for k in keys)
        out.append({"model": m, "n": len(keys), "with_json": a, "without_json": b, "json_prose_agree": agree})
    return out


def spend(records):
    by = defaultdict(lambda: {"calls": 0, "cost": 0.0, "cache_write": 0, "cache_read": 0, "out": 0})
    for r in records:
        b = by[r["model"]]
        b["calls"] += 1
        b["cost"] += r["cost_usd"] or 0.0
        b["cache_write"] += r["usage"]["cache_creation_input_tokens"]
        b["cache_read"] += r["usage"]["cache_read_input_tokens"]
        b["out"] += r["usage"]["output_tokens"]
    return dict(sorted(by.items()))


def build(cache_root=ROOT / "cache", cases=None):
    rows, records, cases = load_scored(cache_root, cases)
    grid = grid_of(rows)
    models = [m for m in MODELS if m in grid]
    heads = [headline(grid, m) for m in models]
    canon = sorted({r["canonical_model"] for r in records if r.get("canonical_model")})
    summary = {
        "skill_commit": SKILL_COMMIT,
        "prompt_version": prompt_version("main"),
        "canonical_models": canon,
        "backends": sorted({r["backend"] for r in records}),
        "cases": len(cases),
        "headline": heads,
        "by_slice": breakdown(grid, models, "slice", cases),
        "by_mode": breakdown(grid, models, "mode", cases),
        "confusions": {m: confusions(grid, m) for m in models},
        "disputed": DISPUTED,
        "sensitivity": sensitivity(grid, models),
        "calibration": {m: calibration(grid, m) for m in models},
        "ab": ab_section(rows),
        "spend": spend(records),
    }
    if "haiku" in grid and "sonnet" in grid:
        summary["routing"], summary["routing_choices"], summary["routing_repeats"] = routing_section(grid, cases)
    return summary, render(summary)


def render(s):
    L = []
    w = L.append
    w("# run-debugger eval report\n")
    w("Generated from `cache/` by `python -m harness.report`. All cases are **synthetic** (see `data/README.md`).\n")
    w(f"- Skill: `duvoai/skills` run-debugger `SKILL.md` @ `{s['skill_commit'][:7]}`, used verbatim as the system prompt")
    w(f"- Prompt version (skill + harness suffix): `{s['prompt_version']}`")
    w(f"- Models (as reported by the API): {', '.join(f'`{m}`' for m in s['canonical_models'])}")
    w(f"- Backend: {', '.join(s['backends'])}; cost = list-price USD as reported per call")
    w(f"- Cases: {s['cases']}\n")

    w("## 1. Headline\n")
    w("| Model | Replies | Accuracy (95% CI) | Strict | Fix target | Evidence grounded | Stable across repeats | Format OK | Cost / diagnosis | p50 / p95 latency |")
    w("|---|---|---|---|---|---|---|---|---|---|")
    for h in s["headline"]:
        lo, hi = h["accuracy_ci"]
        g = pct(h["grounded"]) if h["grounded"] is not None else "–"
        w(f"| {h['model']} | {h['replies']} ({h['repeats']}×) | **{pct(h['accuracy'])}** ({pct(lo)}–{pct(hi)}) | "
          f"{pct(h['strict_accuracy'])} | {pct(h['fix_accuracy'])} | {g} | {pct(h['stable_cases'])} | "
          f"{pct(h['sections_ok'])} | {money(h['cost_per_run'])} | {h['p50_ms'] / 1000:.1f}s / {h['p95_ms'] / 1000:.1f}s |")
    w("")
    w("Sensitivity: accepting the disputed alternate label"
      f" ({', '.join(f'{c} → {v}' for c, vs in s['disputed'].items() for v in vs)}) gives "
      + ", ".join(f"{m} {pct(a)}" for m, a in s["sensitivity"].items()) + ".\n")
    w("*Accuracy*: failure mode in the case's acceptable set; CI is a case-level bootstrap. *Strict*: exact primary label. "
      "*Evidence grounded*: every quoted span in the Evidence section appears verbatim in the input. "
      "*Stable*: share of cases where all repeats gave the same failure mode. *Latency*: API time per call.\n")

    models = [h["model"] for h in s["headline"]]
    for title, key in (("2. Accuracy by slice", "by_slice"), ("3. Accuracy by ground-truth failure mode", "by_mode")):
        w(f"## {title}\n")
        w("| | n | " + " | ".join(models) + " |")
        w("|---|---|" + "---|" * len(models))
        for g, row in s[key].items():
            w(f"| {g} | {row['n']} | " + " | ".join(pct(row[m]) if row[m] is not None else "–" for m in models) + " |")
        w("")

    if "routing" in s:
        w("## 4. Routing: when is the cheap model good enough?\n")
        w(f"Policies replayed offline over the cached replies ({s['routing_repeats']} repeats per case, averaged). "
          f"Δ and savings are relative to Sonnet-only, with case-level bootstrap 95% CIs. "
          f"Held-out rows choose the policy on one half of the cases and score it on the other half (and swap), "
          f"with the rule: cheapest policy within {int(MAX_DROP * 100)} pp of Sonnet on the training half.\n")
        w("| Policy | Rows | Accuracy | Δ vs Sonnet (95% CI) | Cost / diagnosis | Savings vs Sonnet (95% CI) | Escalated | p50 / p95 |")
        w("|---|---|---|---|---|---|---|---|")
        for r in s["routing"]:
            dlo, dhi = r["delta_acc_ci"]
            slo, shi = r["savings_ci"]
            w(f"| {r['policy']} | {r['kind']} | {pct(r['accuracy'])} | {100 * (r['accuracy'] - s['routing'][1]['accuracy']):+.1f} pp "
              f"({100 * dlo:+.1f}…{100 * dhi:+.1f}) | {money(r['cost_per_run'])} | {pct(r['savings'])} ({pct(slo)}…{pct(shi)}) | "
              f"{pct(r['escalation_rate'])} | {r['p50_ms'] / 1000:.1f}s / {r['p95_ms'] / 1000:.1f}s |")
        w("")
        w(f"Held-out choices per fold: {'; '.join(s['routing_choices']['pick'])}. "
          f"Category-gate weak sets per fold: {'; '.join(s['routing_choices']['category'])}.\n")

    w("## 5. Most common mistakes\n")
    for m in models:
        items = ", ".join(f"{gt} → {pred} ×{n}" for (gt, pred), n in s["confusions"][m]) or "none"
        w(f"- **{m}**: {items}")
    w("")

    w("## 6. Is self-reported confidence usable?\n")
    w("| Model | Confidence | Replies | Accuracy |")
    w("|---|---|---|---|")
    for m in models:
        for b, n, a in s["calibration"][m]:
            w(f"| {m} | {b} | {n} | {pct(a)} |")
    w("")

    if s["ab"]:
        w("## 7. Does the harness's JSON line change the diagnosis?\n")
        w("Same cases, one reply each: with the JSON suffix (main run, repeat 0) vs. without it (label parsed from the prose *Failure mode* section).\n")
        w("| Model | n | With JSON line | Without | JSON label = prose label |")
        w("|---|---|---|---|---|")
        for a in s["ab"]:
            w(f"| {a['model']} | {a['n']} | {pct(a['with_json'])} | {pct(a['without_json'])} | {pct(a['json_prose_agree'])} |")
        w("")

    w("## 8. Spend\n")
    w("| Model | Calls | List-price cost | Cache-write tokens | Cache-read tokens | Output tokens |")
    w("|---|---|---|---|---|---|")
    total = 0.0
    for m, b in s["spend"].items():
        total += b["cost"]
        w(f"| {m} | {b['calls']} | ${b['cost']:.2f} | {b['cache_write']:,} | {b['cache_read']:,} | {b['out']:,} |")
    w(f"| **total** | | **${total:.2f}** | | | |")
    w("")
    return "\n".join(L)


def main():
    summary, md = build()
    out = ROOT / "reports"
    out.mkdir(exist_ok=True)
    (out / "REPORT.md").write_text(md + "\n")
    (out / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True, ensure_ascii=False) + "\n")
    print(md)


if __name__ == "__main__":
    sys.exit(main())
