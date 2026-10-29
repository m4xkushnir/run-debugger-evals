"""System prompt (the skill, verbatim) and the paste-mode user message."""

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKILL_PATH = ROOT / "prompts" / "run-debugger.SKILL.md"
SKILL_COMMIT = "04dc3407d4c5a36eb15f384931ed32671f1aa34f"

FAILURE_MODES = [
    "connection_failure",
    "aop_ambiguity",
    "missing_terminal_closure",
    "missing_hitl",
    "missing_data",
    "batch_leak",
    "wrong_decomposition",
    "platform_infra",
    "named_pattern",
    "not_a_failure",
]
FIX_TARGETS = [
    "aop_change",
    "connection_change",
    "setup_or_file",
    "decomposition",
    "escalate_to_duvo",
    "none",
]

# Appended after the skill. Single-turn eval needs a diagnosis without follow-up
# questions, and scoring/routing need a machine-readable line. Its effect on
# behaviour is measured by the no-suffix A/B variant.
HARNESS_SUFFIX = f"""

---

Evaluation harness note (not part of the skill): this is paste mode and the user
message contains everything that is available. Do not ask follow-up questions;
give your best diagnosis in the labelled sections. Then end your reply with exactly
one line of JSON and nothing after it:
{{"failure_mode": "<one of {", ".join(FAILURE_MODES)}>", "fix_target": "<one of {", ".join(FIX_TARGETS)}>", "confidence": <number 0-1>}}
"""

NO_SUFFIX = """

---

Evaluation harness note (not part of the skill): this is paste mode and the user
message contains everything that is available. Do not ask follow-up questions;
give your best diagnosis in the labelled sections.
"""

VARIANTS = {"main": HARNESS_SUFFIX, "no_json": NO_SUFFIX}


def system_prompt(variant="main"):
    return SKILL_PATH.read_text() + VARIANTS[variant]


def sha(text):
    return hashlib.sha256(text.encode()).hexdigest()


def prompt_version(variant="main"):
    return sha(system_prompt(variant))[:16]


def render_transcript(transcript):
    lines = []
    for i, turn in enumerate(transcript, 1):
        kind = turn[0]
        if kind == "agent":
            lines.append(f"[{i}] Agent: {turn[1]}")
        elif kind == "call":
            lines.append(f"[{i}] Tool call → {turn[1]} {turn[2]}")
        elif kind == "result":
            lines.append(f"[{i}] Tool result ← {turn[1]}: {turn[2]}")
        elif kind == "system":
            lines.append(f"[{i}] System: {turn[1]}")
        else:
            raise ValueError(f"unknown turn kind {kind!r}")
    return "\n".join(lines)


def user_message(case):
    run = case["run"]
    meta = [f"Run ID: {run['run_id']}", f"Run status: {run['status']}", f"Build ID: {run['build_id']}"]
    if run.get("error_summary"):
        meta.append(f"Error summary: {run['error_summary']}")
    if run.get("case_id"):
        meta.append(f"Case ID: {run['case_id']}")
        meta.append(f"Case state: {run['case_state']}")
    parts = [
        "Why did this Run fail? Everything I have is below.",
        "\n".join(meta),
        "AOP in effect for this Run (from the Build above):\n\n" + case["aop"],
        "Transcript:\n" + render_transcript(case["transcript"]),
    ]
    if case["context"]:
        parts.append("Other context:\n" + "\n".join(f"- {c}" for c in case["context"]))
    return "\n\n".join(parts)


def input_hash(case):
    return sha(user_message(case))[:16]


def load_cases(path=ROOT / "data" / "cases.jsonl"):
    return [json.loads(line) for line in Path(path).read_text().splitlines() if line.strip()]
