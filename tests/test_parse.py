from harness.parse import (
    evidence_grounded,
    evidence_quotes,
    mode_from_prose,
    section_order_ok,
    sections,
    trailing_json,
)

REPLY = """**Failure mode:** Connection failure — Gmail token expired.

**Where it went wrong:** Step 1, transcript turns [1]–[2].

**Evidence:**
> `ERROR 401: {"error": "invalid_grant", "error_description": "Token has been expired or revoked."}`

The Connection was last authorised 91 days ago. The `invalid_grant` error and the Agent's statement ("Gmail rejected the request") agree.

**Fix:** Re-authenticate the **Gmail** Connection in Setup.

**Next step:** Refresh the Gmail Connection in Setup.

```json
{"failure_mode": "connection_failure", "fix_target": "connection_change", "confidence": 0.93}
```
"""

SOURCE = (
    '[2] Tool result ← gmail.search_messages: ERROR 401: {"error": "invalid_grant", '
    '"error_description": "Token has been expired or revoked."}\n[3] Agent: Gmail rejected the request'
)


def test_sections_found_in_order():
    s = sections(REPLY)
    assert list(s) == ["Failure mode", "Where it went wrong", "Evidence", "Fix", "Next step"]
    assert section_order_ok(REPLY)


def test_header_styles_seen_in_real_replies():
    # Regression: Sonnet/Opus mostly put the label alone on its line; the first parser
    # required a colon and scored those replies as malformed.
    bold_alone = REPLY.replace("**Failure mode:** ", "**Failure mode**\n").replace("**Evidence:**", "**Evidence**") \
        .replace("**Where it went wrong:** ", "**Where it went wrong**\n").replace("**Fix:** ", "**Fix**\n") \
        .replace("**Next step:** ", "**Next step**\n")
    atx = bold_alone.replace("**Failure mode**", "## Failure mode").replace("**Evidence**", "## Evidence") \
        .replace("**Where it went wrong**", "## Where it went wrong").replace("**Fix**", "## Fix") \
        .replace("**Next step**", "## Next step")
    dash = REPLY.replace("**Fix:**", "**Fix** —")
    for text in (bold_alone, atx, dash):
        assert section_order_ok(text), text[:80]
        assert mode_from_prose(text) == "connection_failure"
        assert evidence_grounded(text, SOURCE) is True


def test_prose_lines_are_not_headers():
    text = "**Failure mode:** Missing data\nFix the Setup input first, then rerun.\n**Evidence:** x"
    assert "Fix" not in sections(text)


def test_section_order_violation_detected():
    swapped = REPLY.replace("**Fix:**", "**TMP:**").replace("**Evidence:**", "**Fix:**").replace("**TMP:**", "**Evidence:**")
    assert not section_order_ok(swapped)


def test_trailing_json_inside_code_fence():
    assert trailing_json(REPLY) == {"failure_mode": "connection_failure", "fix_target": "connection_change", "confidence": 0.93}


def test_trailing_json_rejects_unknown_labels_and_trailing_prose():
    assert trailing_json('{"failure_mode": "gremlins", "fix_target": "none", "confidence": 1}')["failure_mode"] is None
    assert trailing_json('{"failure_mode": "missing_data"}\nHope this helps!') is None


def test_prose_mode_aliases():
    assert mode_from_prose(REPLY) == "connection_failure"
    assert mode_from_prose("**Failure mode:** Platform / infra failure\n**Evidence:** x") == "platform_infra"
    assert mode_from_prose("**Failure mode:** Not a failure — the Run is paused on Human in the loop.") == "not_a_failure"
    assert mode_from_prose("**Failure mode:** Portal layout change (named pattern)") == "named_pattern"


def test_prose_label_uses_only_the_leading_label():
    # Regression: the first mapper searched the whole line and hit "platform" here.
    cases = {
        "AOP ambiguity. The Run completed without a platform error, but the outcome was wrong.": "aop_ambiguity",
        "**Batch / iteration leak.** The Run completed without a platform error.": "batch_leak",
        "Missing terminal closure, triggered by a Connection failure. The Gmail 503 is transient.": "missing_terminal_closure",
        "Named pattern: upstream portal UI change. The Connection was healthy.": "named_pattern",
        "Connection failure (transient upstream 5xx from Gmail).": "connection_failure",
        "Missing HITL on a high-stakes action. The Run completed cleanly.": "missing_hitl",
        "Missing data, with a missing terminal closure on the branch that handles it.": "missing_data",
        "None. The Run did not fail. It completed as the AOP specifies.": "not_a_failure",
    }
    for head, mode in cases.items():
        assert mode_from_prose(f"**Failure mode**\n{head}\n**Evidence**\nx") == mode, head


def test_evidence_quotes_use_matched_pairs():
    # Regression: an early extractor paired a quote with a backtick on another line.
    qs = evidence_quotes(REPLY)
    assert 'ERROR 401: {"error": "invalid_grant", "error_description": "Token has been expired or revoked."}' in qs
    assert "Gmail rejected the request" in qs
    assert all("\n" not in q for q in qs)


def test_grounded_and_hallucinated_quotes():
    assert evidence_grounded(REPLY, SOURCE) is True
    fake = REPLY.replace("Token has been expired or revoked.", "Token was deleted by an admin.")
    assert evidence_grounded(fake, SOURCE) is False
    assert evidence_grounded("**Evidence:** none quoted\n**Fix:** x", SOURCE) is None


def test_grounding_tolerates_markdown_elisions_and_nesting():
    src = 'AOP step 2. Use **Snowflake** to check every store\'s stock level and reorder. [5] call `complete_case` and stop.'
    reply = (
        "**Evidence**\n"
        "> Use Snowflake to check **every store's** stock level ... reorder\n"
        '- AOP: "call `complete_case` and stop."\n'
        "**Fix**\nx"
    )
    assert evidence_grounded(reply, src) is True
    assert evidence_grounded(reply.replace("reorder", "cancel"), src) is False


def test_elision_fragments_must_appear_in_order():
    src = "alpha beta gamma delta"
    assert evidence_grounded('**Evidence**\n"alpha beta ... delta"\n**Fix**\nx', src) is True
    assert evidence_grounded('**Evidence**\n"delta stuff ... alpha beta"\n**Fix**\nx', src) is False


def test_relabelled_turns_quote_style_and_identifiers():
    src = "[6] Tool result ← update_case: ERROR 500 Internal Server Error\nfor each open return marked \"approved\""
    reply = (
        "**Evidence**\n"
        "- `[6] update_case: ERROR 500 Internal Server Error`\n"
        "- AOP: \"for each open return marked 'approved'\"\n"
        "- The AOP never calls `postpone_case`.\n"
        "**Fix**\nx"
    )
    assert evidence_quotes(reply) == ["[6] update_case: ERROR 500 Internal Server Error",
                                      "for each open return marked 'approved'"]
    assert evidence_grounded(reply, src) is True
    assert evidence_grounded(reply.replace("ERROR 500", "ERROR 503"), src) is False
