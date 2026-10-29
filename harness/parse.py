"""Parse a run-debugger reply: the five labelled sections and the trailing JSON line."""

import json
import re

from harness.prompt import FAILURE_MODES, FIX_TARGETS

SECTIONS = ["Failure mode", "Where it went wrong", "Evidence", "Fix", "Next step"]

# Prose label → canonical id, for the no-JSON variant and for cross-checking.
MODE_ALIASES = [
    ("named_pattern", r"named pattern"),
    ("not_a_failure", r"^none\b|not (a )?fail|paused|waiting on (a )?human|no failure|working as (designed|intended)"),
    ("platform_infra", r"platform|infra"),
    ("missing_terminal_closure", r"terminal closure|terminal action"),
    ("missing_hitl", r"\bhitl\b|human[- ]in[- ]the[- ]loop"),
    ("batch_leak", r"batch|iteration leak"),
    ("wrong_decomposition", r"decomposition"),
    ("missing_data", r"missing data"),
    ("aop_ambiguity", r"ambigu"),
    ("connection_failure", r"connection failure|connection"),
]

# A section header starts a line, may carry Markdown (#, >, -, *, **), and is followed by
# a colon inside or outside the bold, a dash, or the end of the line. Seen in replies:
# "**Failure mode:** x", "**Failure mode**\nx", "## Failure mode", "**Fix** — x".
_SECTION_RE = re.compile(
    r"^[ \t]*(?:[#>\-*][ \t#>\-*]*)?\**[ \t]*(" + "|".join(re.escape(s) for s in SECTIONS) + r")"
    r"[ \t]*(?::[ \t]*\**|\**[ \t]*[:—–-]|\**[ \t]*$)",
    re.IGNORECASE | re.MULTILINE,
)


def sections(text):
    """Return {section: body} in order of appearance (first occurrence wins)."""
    hits = [(m.start(), m.end(), m.group(1).lower()) for m in _SECTION_RE.finditer(text)]
    out = {}
    for i, (_, end, name) in enumerate(hits):
        stop = hits[i + 1][0] if i + 1 < len(hits) else len(text)
        canon = next(s for s in SECTIONS if s.lower() == name)
        out.setdefault(canon, text[end:stop].strip())
    return out


def section_order_ok(text):
    found = [m.group(1).lower() for m in _SECTION_RE.finditer(text)]
    seen = []
    for f in found:
        if f not in seen:
            seen.append(f)
    return seen == [s.lower() for s in SECTIONS]


def trailing_json(text):
    for line in reversed(text.strip().splitlines()):
        line = line.strip().strip("`")
        if line.startswith("{") and line.endswith("}"):
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                return None
            mode = obj.get("failure_mode")
            fix = obj.get("fix_target")
            conf = obj.get("confidence")
            return {
                "failure_mode": mode if mode in FAILURE_MODES else None,
                "fix_target": fix if fix in FIX_TARGETS else None,
                "confidence": float(conf) if isinstance(conf, (int, float)) else None,
            }
        if line:
            return None
    return None


def mode_from_prose(text):
    body = sections(text).get("Failure mode", "")
    head = body.splitlines()[0] if body else ""
    # Only the leading label counts: "AOP ambiguity. The Run completed without a
    # platform error..." must not match "platform".
    head = re.split(r"\.\s|:|,|\(|\s[—–-]\s", head.replace("*", "").strip(), maxsplit=1)[0]
    for mode, pattern in MODE_ALIASES:
        if re.search(pattern, head, re.IGNORECASE):
            return mode
    return "named_pattern" if head else None


def _norm(s):
    """Lower-case, collapse whitespace, unify quotes, drop Markdown emphasis/code marks."""
    s = s.replace("\u2019", "'").replace("\u201c", '"').replace("\u201d", '"')
    s = s.replace("*", "").replace("`", "").replace("'", '"')
    return re.sub(r"\s+", " ", s).strip().lower()


_SPAN_PATTERNS = [
    (re.compile(r"^[ \t]*>[ \t]*(.+)$", re.MULTILINE)),
    (re.compile(r"`([^`\n]+)`")),
    (re.compile(r"\u201c([^\u201d\n]+)\u201d")),
    (re.compile(r"\"([^\"\n]+)\"")),
]


def evidence_quotes(text):
    """Quoted spans in the Evidence section (blockquote lines, `code`, "..." and \u201c...\u201d
    on one line). Only outermost spans are kept, so a `code` span inside a quoted line
    is not counted again."""
    body = sections(text).get("Evidence", "")
    spans = []
    for pattern in _SPAN_PATTERNS:
        for m in pattern.finditer(body):
            spans.append((m.start(1), m.end(1), m.group(1)))
    spans.sort(key=lambda x: (x[0], -x[1]))
    quotes, reach = [], -1
    for start, end, q in spans:
        if end <= reach:
            continue  # nested inside an earlier, wider span
        reach = max(reach, end)
        q = q.strip().strip("`\"\u201c\u201d").strip()
        if not re.search(r"\s", q):
            continue  # a bare identifier (`fail_case`, `Sites.Read.All`) names a thing; it isn't a quote
        if len(q) >= 8:
            quotes.append(q)
    return quotes


_TURN_PREFIX = re.compile(r"^\[\d+\]\s*(?:[\w.]+\s*:\s*)?")


def _fragment_in(q, src):
    # A quoted transcript line may be re-labelled ("[6] update_case: ERROR ...") while its
    # content is verbatim; accept it if the content after the turn prefix matches.
    stripped = _TURN_PREFIX.sub("", q)
    return _fragments_in(q, src) or (stripped != q and _fragments_in(stripped, src))


def _fragments_in(q, src):
    # "..." or "\u2026" inside a quote marks an elision: every fragment must appear, in order.
    pos = 0
    for frag in re.split(r"\.\.\.|\u2026", q):
        frag = frag.strip(" .,;:")
        if not frag:
            continue
        i = src.find(frag, pos)
        if i < 0:
            return False
        pos = i + len(frag)
    return True


def evidence_grounded(text, source):
    """True if every quoted evidence span appears verbatim in the input the model was
    given, ignoring whitespace, quote style, Markdown marks and marked elisions.
    None if no quote was found."""
    quotes = evidence_quotes(text)
    if not quotes:
        return None
    src = _norm(source)
    return all(_fragment_in(_norm(q), src) for q in quotes)


def ungrounded_quotes(text, source):
    src = _norm(source)
    return [q for q in evidence_quotes(text) if not _fragment_in(_norm(q), src)]
