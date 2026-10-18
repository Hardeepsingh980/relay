"""Rule-based signal extraction over customer conversation text (method "rules-v1").

Deterministic on purpose: the hero demo must be repeatable. Each signal keeps the
exact sentence it came from so the evidence drawer can quote it verbatim. The
Ingest agent can swap in Gemini extraction; the graph shape stays the same.
"""

from __future__ import annotations

import re

METHOD = "rules-v1"

RULES: list[tuple[str, str, float]] = [
    # (signal type, regex, confidence)
    ("competitor_evaluation", r"evaluating (?:a couple of )?(?:other|alternative) (?:tools|platforms)", 0.92),
    ("competitor_evaluation", r"look at alternatives", 0.85),
    ("competitor_evaluation", r"demo from another (?:vendor|platform)", 0.9),
    ("competitor_evaluation", r"comparing options", 0.7),
    ("competitor_evaluation", r"platforms? we looked at", 0.8),
    ("frustration", r"frustrat\w*", 0.8),
    ("frustration", r"losing patience", 0.85),
    ("frustration", r"unacceptable", 0.85),
    ("budget_pressure", r"cut software costs", 0.85),
    ("budget_pressure", r"budgets? (?:are )?tight", 0.8),
    ("budget_pressure", r"reduce seats", 0.8),
    ("price_objection", r"(?:quite a bit |a lot |much )?cheaper", 0.75),
    ("renewal_positive", r"roll cheerio out to", 0.85),
    ("renewal_positive", r"more (?:agent )?seats", 0.8),
    ("praise", r"big hit", 0.75),
    ("praise", r"really happy", 0.75),
    ("praise", r"running smoothly", 0.75),
    ("praise", r"loves the", 0.7),
    ("praise", r"paid for itself", 0.75),
]

# Wider patterns for lines typed or spoken in a live call. They are not used to score the sample data.
LIVE_RULES: list[tuple[str, str, float]] = [
    ("competitor_evaluation", r"(?:other|another|different|cheaper) (?:vendors?|providers?|tools?|platforms?|options?)", 0.8),
    ("competitor_evaluation", r"\b(?:switch(?:ing)? to|move to|alternatives?|competitors?)\b", 0.75),
    ("frustration", r"\b(?:fed up|annoyed|disappointed|not happy|tired of|keeps? (?:failing|breaking))\b", 0.75),
    ("budget_pressure", r"\b(?:budget|too expensive|costs? too much|cost cutting|cut costs)\b", 0.75),
    ("renewal_positive", r"\b(?:renew|expand|add more seats|happy to continue)\b", 0.7),
]

POSITIVE_TYPES = ("renewal_positive", "praise")


def _sentence_around(text: str, start: int, end: int) -> str:
    left = max(text.rfind(". ", 0, start), text.rfind("? ", 0, start), text.rfind("! ", 0, start))
    left = 0 if left < 0 else left + 2
    right_candidates = [i for i in (text.find(". ", end), text.find("? ", end), text.find("! ", end)) if i >= 0]
    right = min(right_candidates) + 1 if right_candidates else len(text)
    sentence = text[left:right].strip().strip("'\"")
    return re.sub(r"^[A-Z][\w .&]{0,40}: ", "", sentence)  # drop a leading "Speaker: " label


def extract(text: str, broad: bool = False) -> list[dict]:
    """Return one signal per type found in the text (the strongest rule wins). `broad` adds the live-call rules."""
    best: dict[str, dict] = {}
    for sig_type, pattern, confidence in RULES + (LIVE_RULES if broad else []):
        m = re.search(pattern, text, flags=re.IGNORECASE)
        if not m:
            continue
        current = best.get(sig_type)
        if current and current["confidence"] >= confidence:
            continue
        best[sig_type] = {
            "type": sig_type, "phrase": m.group(0), "quote": _sentence_around(text, m.start(), m.end()),
            "confidence": confidence, "method": METHOD,
        }
    return list(best.values())
