"""Execute the eval grid against a backend, filling the cache. Cached cells are never re-called."""

import argparse
import datetime as dt
import json
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

from harness.backends import ClaudeCLIBackend
from harness.budget import Budget, BudgetExceeded
from harness.cache import Cache, cache_key
from harness.prompt import ROOT, input_hash, load_cases, prompt_version, system_prompt, user_message

# Conservative per-call reservations (list-price USD); actual cost settles after the call.
ESTIMATE = {"haiku": 0.015, "sonnet": 0.05, "opus": 0.09}


def plan(cases, models, repeats, variant):
    pv = prompt_version(variant)
    jobs = []
    for case in cases:
        ih = input_hash(case)
        for model in models:
            for r in range(repeats):
                jobs.append({
                    "key": cache_key(model, pv, ih, r),
                    "case_id": case["id"], "model": model, "variant": variant,
                    "prompt_version": pv, "input_hash": ih, "repeat": r, "case": case,
                })
    return jobs


def spent_so_far(cache):
    total = 0.0
    for p in cache.root.glob("*/*.json"):
        total += json.loads(p.read_text()).get("cost_usd") or 0.0
    return total


def execute(jobs, backend, cache, budget, workers=6, log=print):
    todo = [j for j in jobs if cache.get(j["key"]) is None]
    log(f"{len(jobs)} cells, {len(jobs) - len(todo)} cached, {len(todo)} to call; "
        f"budget spent ${budget.spent:.2f} of ${budget.cap:.2f}")

    def one(job):
        est = ESTIMATE[job["model"]]
        budget.reserve(est)
        try:
            resp = backend.call(job["model"], system_prompt(job["variant"]), user_message(job["case"]))
        except Exception:
            budget.settle(est, 0.0)
            raise
        budget.settle(est, resp["cost_usd"])
        record = {k: v for k, v in job.items() if k != "case"}
        record.update(resp)
        record["created_at"] = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
        cache.put(job["key"], record)
        return job

    done = failed = 0
    stopped = False
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(one, j) for j in todo]
        for fut in as_completed(futures):
            try:
                fut.result()
                done += 1
            except BudgetExceeded as e:
                if not stopped:
                    log(f"STOP: {e}")
                    stopped = True
                for f in futures:
                    f.cancel()
            except Exception as e:  # keep going; failed cells stay uncached and are retried next time
                failed += 1
                log(f"call failed: {e}")
            if done and done % 20 == 0:
                log(f"  {done}/{len(todo)} done, spent ${budget.spent:.2f}")
    log(f"finished: {done} called, {failed} failed, spent ${budget.spent:.2f}")
    return done, failed


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", default="haiku,sonnet")
    ap.add_argument("--repeats", type=int, default=5)
    ap.add_argument("--variant", default="main", choices=["main", "no_json"])
    ap.add_argument("--cases", default="", help="comma-separated case ids (default: all)")
    ap.add_argument("--cap", type=float, default=25.0, help="hard cap, list-price USD, across the whole cache")
    ap.add_argument("--workers", type=int, default=6)
    args = ap.parse_args(argv)

    cases = load_cases()
    if args.cases:
        wanted = set(args.cases.split(","))
        cases = [c for c in cases if c["id"] in wanted]
    cache = Cache(ROOT / "cache")
    budget = Budget(args.cap, spent_usd=spent_so_far(cache))
    jobs = plan(cases, args.models.split(","), args.repeats, args.variant)
    _, failed = execute(jobs, ClaudeCLIBackend(), cache, budget, workers=args.workers)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
