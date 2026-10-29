# Dataset: 40 synthetic failed Runs

**Every case here is synthetic.** None of it comes from a real Duvo Run, customer or workspace. Each case is marked `"synthetic": true` and carries a `provenance` string.

## How it was built

1. I wrote each case by hand in `build_dataset.py`: a retail/ops setting, the AOP that was "in effect", a short transcript (Agent turns, tool calls, tool results, system events), any extra context a user would paste, and the ground truth.
2. The failure modes and their discriminators come from the public `run-debugger` skill (`duvoai/skills` @ `04dc340`). The settings (AP invoice intake, freight audit, supplier reminders, store replenishment, returns, DESADV exceptions, supplier portals behind Okta) come from the public skills and the kind of work Duvo describes.
3. No language model wrote, edited or labelled any case.
4. `python data/build_dataset.py` regenerates `cases.jsonl` byte-for-byte.

## Ground truth

| Field | Meaning |
|---|---|
| `failure_mode` | the intended primary label: one of the skill's 8 categories, `named_pattern` (the skill's "don't force-fit" escape hatch) or `not_a_failure` (e.g. a Run paused on Human in the loop) |
| `acceptable` | labels a careful reviewer would also accept; used for the main accuracy metric (`strict` uses `failure_mode` only) |
| `fix_target` / `fix_acceptable` | which artifact the fix should change: `aop_change`, `connection_change`, `setup_or_file`, `decomposition`, `escalate_to_duvo`, `none` |
| `decision_point` | the transcript or AOP text where the Run took the wrong path; a test asserts it is visible in the model's input |

## Slices

| Slice | n | Purpose |
|---|---|---|
| `clean` | 24 | 3 per taxonomy category |
| `trap` | 6 | a loud symptom (401, timeout, 429, validation error) whose real cause is elsewhere |
| `discriminator` | 3 | Connection failure vs Platform/infra: the skill's own "fails again right after a clean reauthentication" rule |
| `not_a_failure` | 2 | a paused Run; a Run that correctly took an early-return branch |
| `ambiguity` | 5 | page-layout change, rate limit, portal timeout, partial completion, wrong field extracted. These are cases the taxonomy doesn't cleanly cover, so `acceptable` is wider |

## Guarding against leakage

`tests/test_dataset.py` checks that no case's rendered input contains taxonomy wording ("terminal closure", "decomposition", "batch", "root cause", …). System events are rendered as `System:` rather than `Platform:`, so the label can't hint at `platform_infra`.

## Known weaknesses

- One author wrote both the cases and the labels. The `acceptable` sets are my judgement and are the most debatable part; per-case labels are in `cases.jsonl` for anyone to disagree with.
- The transcripts are short (3–9 turns) and clean. Real Runs are longer and noisier, so absolute accuracy here is likely an **upper bound**; the comparison *between* models is the more transferable result.
- 40 cases give wide confidence intervals. Differences of a few points are not significant, and the report shows the intervals.
