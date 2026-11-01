"""Zero-LLM sentiment scoring for chat turns. @obs-good is explicit and wins;
praise phrasing is a heuristic candidate for retroactive clips."""
import re

EXPLICIT_RE = re.compile(r"@obs-good\b")

# (score, pattern) — first match wins, ordered by specificity/confidence.
PRAISE_PATTERNS = [
    (90, re.compile(r"so beautif\w*", re.I)),
    (85, re.compile(r"that'?s (great|beautiful|perfect)", re.I)),
    (80, re.compile(r"\b(excellent|perfect|amazing|brilliant)\b", re.I)),
    (70, re.compile(r"let it sink", re.I)),
    (65, re.compile(r"now le?t'?s move|move on to", re.I)),
    (60, re.compile(r"ahhh+ i see|oh,? it is", re.I)),
    (50, re.compile(r"\bgot it\b|makes sense|understood", re.I)),
    (40, re.compile(r"^\s*(thanks|thank you)\b", re.I)),
]

MAX_PRAISE_CHARS = 400


NEUTRAL = {"explicit": False, "marker": None, "score": 0, "matched": []}


def score_turn(turn):
    """Return {"explicit","marker","score","matched"} for a user turn.
    Praise heuristics only apply to short turns (praise is brief; long turns are
    new questions, not reactions).

    Model turns always score 0: the assistant's own stock enthusiasm ("Excellent!",
    "Perfect.") otherwise trips the praise patterns, which measures the model's
    register rather than the user's reaction."""
    role = getattr(turn, "role", "user")
    if role == "model":
        return dict(NEUTRAL)

    text = turn.text if hasattr(turn, "text") else turn
    explicit = bool(EXPLICIT_RE.search(text))
    if explicit:
        return {"explicit": True, "marker": "@obs-good", "score": 100, "matched": ["@obs-good"]}

    if len(text) > MAX_PRAISE_CHARS:
        return dict(NEUTRAL)

    matched = []
    best = 0
    for score, pattern in PRAISE_PATTERNS:
        m = pattern.search(text)
        if m:
            matched.append(m.group(0))
            best = max(best, score)
    return {"explicit": False, "marker": None, "score": best, "matched": matched}


def landed_well(turns):
    """For each user turn with signal.score > 0, credit the nearest PRECEDING
    model turn — that's the answer that earned the reaction."""
    out = []
    for i, turn in enumerate(turns):
        if turn.role != "user" or not turn.signal or turn.signal["score"] <= 0:
            continue
        credited = None
        for j in range(i - 1, -1, -1):
            if turns[j].role == "model":
                credited = turns[j]
                break
        if credited is None:
            continue
        out.append({
            "praise_node": turn.hash,
            "credited_node": credited.hash,
            "score": turn.signal["score"],
            "matched": turn.signal["matched"],
            "explicit": turn.signal["explicit"],
        })
    return out
