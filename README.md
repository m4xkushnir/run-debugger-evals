# run-debugger-evals

An eval harness for Duvo's public [`run-debugger`](https://github.com/duvoai/skills/tree/main/skills/run-debugger) agent skill: how accurately it diagnoses failed agent Runs on Haiku, Sonnet and Opus, what each costs, how stable each is, and which routing rule gives Sonnet-level diagnoses at Haiku-level cost.

> **The data is synthetic.** It's 40 hand-written failed Runs from retail/ops automation, with labels written before any model saw them. Nothing here comes from a real Duvo Run or account. See [`data/README.md`](data/README.md).
> Independent project, not affiliated with Duvo.

## Results

From [`reports/REPORT.md`](reports/REPORT.md): 560 calls (Haiku and Sonnet ×5 repeats, Opus ×2, plus a 40-case A/B for the harness's JSON line). Total cost **$5.58 at list prices**, as reported per call.

| | Haiku 5.5 | Sonnet 5.5 | Opus 5.5 |
|---|---|---|---|
| Diagnosis accuracy (95% CI) | **97.0%** (93.0–99.5) | **97.0%** (91.0–100) | **100%** (100–100) |
| Fix target correct | 94.0% | 94.0% | 100% |
| Evidence quotes verbatim in input | 97.0% | 96.0% | 100% |
| Same answer on all repeats | 85.0% of cases | 92.5% | 100% |
| Cost per diagnosis (list price) | **$0.0009** | $0.0111 | $0.0312 |
| Latency p50 / p95 (API time) | 8.7s / 12.2s | 8.0s / 14.5s | 10.3s / 15.4s |

**Routing**, replayed offline from the cached replies. Savings are relative to Sonnet-only, with case-level bootstrap 95% CIs:

| Policy | Accuracy | Cost / diagnosis | Savings vs Sonnet | Escalated | p95 |
|---|---|---|---|---|---|
| Sonnet only | 97.0% | $0.0111 | – | – | 14.5s |
| Haiku only | 97.0% | $0.0009 | **91.8%** (91.2–92.4) | 0% | 12.2s |
| **2× Haiku in parallel → Sonnet if they disagree** | **99.5%** | $0.0029 | **73.7%** (66.1–80.5) | 7.0% | 23.8s |
| Haiku → Sonnet if confidence < 0.85 *(threshold tuned in-sample)* | 99.5% | $0.0045 | 59.6% (45.5–74.4) | 26.0% | 25.8s |

### What this says

1. **For this skill, Haiku is good enough as the default.** It matches Sonnet's top-1 accuracy at 92% lower cost. Choosing the policy on half the cases and scoring it on the other half (cross-fitting) picks the confidence gate at τ = 0.60 on both folds. That gate never escalates on this data, so it is Haiku-only in effect.
2. **Haiku's real weakness is variance, not average accuracy.** It gives the same answer on all 5 repeats for 85% of cases, against 92.5% for Sonnet. That makes **self-consistency the best escalation signal**: two parallel Haiku samples, escalating only when they disagree, reach 99.5% accuracy at 74% below Sonnet's cost and escalate 7% of Runs. The rule has no tuned parameter, so its number isn't flattered by threshold fitting. The cost is tail latency: overall p95 goes from 14.5s to 23.8s, because escalated Runs make two calls in sequence.
3. **Where Haiku breaks: wrong decomposition (66.7% vs 100%).** When an Agent tries to wait days inside one Run, Haiku sometimes diagnoses the symptom (an expired browser session, a missing terminal action) instead of the cause, which is the AOP doing two Agents' work. That's exactly the skill's "symptom vs root cause" rule. A category gate fitted per fold escalates 5% of Runs and holds accuracy at 97.0%.
4. **Haiku's self-reported confidence is informative; Sonnet's isn't monotonic.** Haiku: 87.5% accurate at 0.6–0.8 confidence, 100% at ≥0.9. Sonnet: 96.8% at 0.6–0.8 but 91.7% at 0.8–0.9.
5. **Sonnet's only consistent miss is a disputed label.** On C03, Sonnet answers "missing data" on all 5 repeats where I labelled "Connection failure". It's a CZ-scoped Login used for an AT store, and its argument is defensible. Labels stayed frozen; accepting it lifts Sonnet to 99.5%. The run-debugger taxonomy has no "wrong scope/region" category, though the sibling `connection-doctor` skill does.
6. **Evidence grounding:** 12 quotes across 480 replies were not verbatim (all manually read): invented phrases, reformatted JSON, the skill's own wording quoted as evidence, and one quote that isn't in that case's input at all.

### What this does not say

- **The cases are too easy to separate the models on accuracy.** All three score 97–100% on short, clean transcripts. The differences that matter here are variance, cost and specific failure categories. Real Runs are longer and noisier, so absolute accuracy here is an upper bound.
- **40 cases give wide intervals.** "Haiku = Sonnet" means "no difference detectable at n=40" (Δ 0.0 pp, CI −5.5…+7.0), not "proven equal".
- **Single-turn paste mode.** The skill may ask the user for more data. The harness tells the model not to, so that path isn't tested.
- **Cost is list price via headless Claude Code (`claude -p`), not production API billing.** Token counts and API latency are real per call. Batch API discounts and cache-TTL control aren't modelled. An `anthropic-api` backend with the same cache format is included.
- **The harness adds one instruction:** a final JSON line `{failure_mode, fix_target, confidence}`. Without it (40 cases, 1 reply each), Haiku scored 90.0% vs 97.5% and Sonnet 97.5% vs 97.5%. That's within noise for one sample, but it suggests the structured line may help the smaller model commit.
- One author wrote the cases and the labels.

## How it works

```
data/build_dataset.py     40 hand-written cases → data/cases.jsonl
prompts/run-debugger.SKILL.md   the skill, verbatim (duvoai/skills @ 04dc340)
harness/prompt.py         system prompt = skill + harness note; paste-mode user message
harness/backends.py       claude -p (used) | Anthropic API (same interface, not run)
harness/cache.py          content-addressed replies: key = sha256(model, prompt version, input hash, repeat)
harness/budget.py         hard cap with per-call reservations (safe under concurrency)
harness/parse.py, score.py   deterministic scoring: label, fix target, sections, verbatim evidence
harness/routing.py        offline policy replay, cross-fitting, case-level bootstrap
harness/report.py         reports/REPORT.md + summary.json from the cache only
```

- **Unit under test:** the skill file unchanged, as the system prompt, in its documented paste mode (Run ID, AOP in effect, transcript, context).
- **Metrics:**
  - accuracy against an `acceptable` label set, plus strict accuracy against the primary label;
  - fix target;
  - five-section format;
  - **evidence grounding**: every quoted span must appear in the input, ignoring Markdown and marked elisions;
  - stability across repeats;
  - cost and API latency per call.
  No LLM judge.
- **Reproducibility:** the report reads only `cache/` and is byte-identical on rerun (tested). Changing the skill, the harness note or a case changes its key, and the report ignores stale entries (tested). Cached cells are never re-called.
- **Routing honesty:** τ and the weak-category set are chosen on one half of the cases and scored on the other (cross-fitting). Intervals resample cases, not replies, because the replies to one case aren't independent.

## Run it

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
make test      # 32 tests, no model calls
make report    # regenerate reports/ from the committed cache, no model calls
make run       # fill missing cells via `claude -p` (needs Claude Code logged in); --cap enforces a USD cap
```

## License

MIT. `prompts/run-debugger.SKILL.md` is © Duvo AI, MIT, included unchanged for reproducibility (see `NOTICE.md`).
