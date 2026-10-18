"""Expertise scoring policy.

A person's link to a system or customer is built from activity signals, each
decayed by age, then squashed into [0, 1):

    raw   = sum(weight[signal] * 0.5 ** (age_days / HALF_LIFE_DAYS)) + owner_bonus
    score = 1 - exp(-raw / K)

Links to decisions and workarounds come from the role a person played in the
source (proposed it, approved it, just acknowledged it...).
"""

from __future__ import annotations

import math
from datetime import datetime

HALF_LIFE_DAYS = 120.0
K = 10.0

SIGNAL_WEIGHTS = {
    "commit": 0.3,     # authored a commit in the system's repo
    "review": 0.3,     # reviewed a pull request in the repo
    "doc": 3.0,        # authored a doc labelled with the system/customer
    "answer": 0.6,     # substantive answer in a thread about the system/customer
    "ticket": 1.5,     # resolved a ticket on the system/customer
    "ticket_open": 0.75,  # currently assigned an open ticket
    "contact": 0.5,    # conversation with a customer's own people
}
OWNER_BONUS = 3.0      # named owner in the service catalog / CRM

ROLE_SCORES = {
    "proposer": 0.9,     # argued for it and gave the reasoning
    "author": 0.9,       # discovered / wrote the workaround
    "co-proposer": 0.85,
    "applier": 0.65,     # independently applied or explained it again
    "supporter": 0.55,   # argued for it with substance
    "approver": 0.35,    # signed off; knows *that*, not necessarily *why*
    "ack": 0.2,          # was told about it
}
REPEAT_BONUS = 0.03     # each extra source where the same role recurs

STRONG = 0.6            # "strong link" for the departing person
ALTERNATE = 0.4         # any other active person above this is a credible alternate
STALE_DAYS = 120        # last activity older than this marks the link stale


def decay(when: datetime, now: datetime) -> float:
    age = max((now - when).total_seconds() / 86400.0, 0.0)
    return 0.5 ** (age / HALF_LIFE_DAYS)


def squash(raw: float) -> float:
    return 1.0 - math.exp(-raw / K)


def role_score(roles: list[str]) -> float:
    """Best role, plus a small bonus for each additional source with a role."""
    if not roles:
        return 0.0
    best = max(ROLE_SCORES.get(r, 0.0) for r in roles)
    return min(best + REPEAT_BONUS * (len(roles) - 1), 0.98)
