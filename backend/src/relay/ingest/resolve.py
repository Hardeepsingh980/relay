"""Entity resolution: map free-text mentions ("recon service", "Acme") to graph ids.

Aliases come from the service catalog and CRM. Matching is case-insensitive,
on word boundaries, longest match first, without overlapping spans, so
"acme-sftp-bridge" resolves to the system and does not also count as "Acme".
"""

from __future__ import annotations

import re
from dataclasses import dataclass

ACK_RE = re.compile(
    r"^\s*(thanks|thank you|ty|thx|done|cleared|fixed|perfect|great|got it|ok|okay|makes sense|will do|"
    r"works now|yep|yes|ah|that (did|was) it|re-ran|ran it|that worked|👍|🙏)\b", re.I)


@dataclass(frozen=True)
class Alias:
    entity_id: str
    label: str      # "System" | "Account"
    text: str


class AliasMatcher:
    def __init__(self, aliases: list[Alias]):
        self.aliases = sorted(aliases, key=lambda a: -len(a.text))
        parts = [re.escape(a.text) for a in self.aliases]
        self._re = re.compile(r"(?<![\w-])(" + "|".join(parts) + r")(?![\w-])", re.I)
        self._by_text = {a.text.lower(): a for a in self.aliases}

    def find(self, text: str) -> list[tuple[Alias, str]]:
        """Return (alias, matched surface form) for each non-overlapping mention."""
        if not text:
            return []
        out = []
        for m in self._re.finditer(text):
            a = self._by_text.get(m.group(1).lower())
            if a:
                out.append((a, m.group(1)))
        return out

    def entities(self, text: str) -> set[tuple[str, str]]:
        return {(a.entity_id, a.label) for a, _ in self.find(text)}


def is_substantive(text: str) -> bool:
    """A reply that plausibly transfers knowledge: not an ack, not a question."""
    t = (text or "").strip()
    if len(t) < 40:
        return False
    if t.endswith("?"):
        return False
    if ACK_RE.match(t) and len(t) < 70:
        return False
    return True
