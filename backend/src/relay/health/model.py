"""Transparent, configurable account-risk scoring.

This is a demo score, not a calibrated probability. Every factor is computed
from graph traversals (see relay.health.risk) and combined here with visible
weights, so anyone can see exactly why an account scored what it did.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

# Windows, in days before the as-of date.
SIGNAL_WINDOW_DAYS = 60       # conversations and tickets considered "recent"
DEPARTURE_WINDOW_DAYS = 90    # champion departures considered "recent"
MIN_LINK_CONFIDENCE = 0.70    # ticket -> bug links below this are "possible", never causal
MIN_SIGNAL_CONFIDENCE = 0.60
WALLET_LOW_INR = 5000         # below this the wallet is about to run dry

# Usage windows as week indexes over the 26-week series (25 = most recent complete week).
N_WEEKS = 26
BASELINE_WEEKS = (12, 19)     # 8 weeks before the recent change window
CURRENT_WEEKS = (22, 25)      # last 4 complete weeks

WEIGHTS = {
    "base": 6,
    "champion_departed": 18,
    "unresolved_bug_ticket": 6,     # per ticket
    "unresolved_bug_ticket_max": 3,
    "wau_decline_per_100pct": 25,   # applied when decline >= 10%
    "wau_decline_min_pct": 10,
    "wau_decline_cap": 15,
    "feature_decline_per_100pct": 15,  # applied when decline >= 20%
    "feature_decline_min_pct": 20,
    "feature_decline_cap": 12,
    "competitor_signal": 12,
    "budget_signal": 6,
    "frustration_signal": 4,        # per signal
    "frustration_cap": 8,
    "positive_signal": -6,          # per signal
    "positive_cap": -12,
    "late_payment": 3,              # latest invoice more than 7 days late
    "late_payment_min_days": 7,
    "promise_at_risk": 5,           # per promise whose dependency slipped past its due date
    "promise_at_risk_cap": 10,
    "internal_owner_leaving": 6,    # a Cheerio person this account depends on is leaving
    "wallet_low": 4,
}
RISK_FLOOR, RISK_CEILING = 5, 95
SILENT_RISK_CRM_MIN = 70
SILENT_RISK_RISK_MIN = 60


@dataclass
class RiskInputs:
    champion_departed: bool = False
    champion_name: str | None = None
    unresolved_bug_tickets: int = 0
    top_bug_keyword: str | None = None
    wau_decline_pct: int = 0
    top_feature: str | None = None
    top_feature_decline_pct: int = 0
    competitor_signals: int = 0
    budget_signals: int = 0
    frustration_signals: int = 0
    positive_signals: int = 0
    latest_invoice_days_late: int = 0
    recovered_usage: bool = False
    fixed_bug_tickets: int = 0
    promises_at_risk: list[str] = field(default_factory=list)
    owners_leaving: list[str] = field(default_factory=list)
    wallet_balance: int | None = None


@dataclass
class Factor:
    key: str
    label: str
    points: int
    detail: str


def _count(n: int, noun: str) -> str:
    return f"{n} {noun}{'' if n == 1 else 's'}"


def _scaled(pct: int, per_100: int) -> int:
    # Integer half-up rounding so the score is stable across platforms.
    return (pct * per_100 + 50) // 100


def score(inputs: RiskInputs) -> tuple[int, list[Factor]]:
    w = WEIGHTS
    factors: list[Factor] = []
    if inputs.champion_departed:
        factors.append(Factor("champion_departed", "Main contact left", w["champion_departed"],
                              f"{inputs.champion_name or 'The main contact'} left within {DEPARTURE_WINDOW_DAYS} days"))
    if inputs.unresolved_bug_tickets:
        n = min(inputs.unresolved_bug_tickets, w["unresolved_bug_ticket_max"])
        kw = f" {inputs.top_bug_keyword}" if inputs.top_bug_keyword else ""
        noun = "ticket" if inputs.unresolved_bug_tickets == 1 else "tickets"
        factors.append(Factor("unresolved_bug_tickets", f"{inputs.unresolved_bug_tickets} unresolved{kw} {noun}",
                              n * w["unresolved_bug_ticket"],
                              f"{inputs.unresolved_bug_tickets} {noun} in the last {SIGNAL_WINDOW_DAYS} days "
                              f"{'points' if inputs.unresolved_bug_tickets == 1 else 'point'} to open bugs"))
    if inputs.wau_decline_pct >= w["wau_decline_min_pct"]:
        factors.append(Factor("wau_decline", f"Active users down {inputs.wau_decline_pct}%",
                              min(_scaled(inputs.wau_decline_pct, w["wau_decline_per_100pct"]), w["wau_decline_cap"]),
                              "Last 4 weeks compared with an earlier 8-week average"))
    if inputs.top_feature and inputs.top_feature_decline_pct >= w["feature_decline_min_pct"]:
        factors.append(Factor("feature_decline", f"{inputs.top_feature} usage down {inputs.top_feature_decline_pct}%",
                              min(_scaled(inputs.top_feature_decline_pct, w["feature_decline_per_100pct"]), w["feature_decline_cap"]),
                              "The biggest drop of any feature, last 4 weeks compared with an earlier 8-week average"))
    if inputs.competitor_signals:
        factors.append(Factor("competitor_signal", "Evaluating competitors", w["competitor_signal"],
                              f"{_count(inputs.competitor_signals, 'competitor mention')} in the last {SIGNAL_WINDOW_DAYS} days"))
    if inputs.budget_signals:
        factors.append(Factor("budget_signal", "Budget worry", w["budget_signal"],
                              f"{_count(inputs.budget_signals, 'mention')} of budget worries in the last {SIGNAL_WINDOW_DAYS} days"))
    if inputs.frustration_signals:
        factors.append(Factor("frustration_signal", "Frustration in conversations",
                              min(inputs.frustration_signals * w["frustration_signal"], w["frustration_cap"]),
                              f"{_count(inputs.frustration_signals, 'sign')} of frustration in the last {SIGNAL_WINDOW_DAYS} days"))
    if inputs.positive_signals:
        factors.append(Factor("positive_signal", "Positive signs",
                              max(inputs.positive_signals * w["positive_signal"], w["positive_cap"]),
                              f"{_count(inputs.positive_signals, 'positive sign')} in the last {SIGNAL_WINDOW_DAYS} days"))
    if inputs.latest_invoice_days_late > w["late_payment_min_days"]:
        factors.append(Factor("late_payment", f"Invoice paid {inputs.latest_invoice_days_late} days late",
                              w["late_payment"], "The most recent invoice"))
    if inputs.promises_at_risk:
        n = len(inputs.promises_at_risk)
        factors.append(Factor("promise_at_risk", f"{n} promise{'s' if n > 1 else ''} at risk",
                              min(n * w["promise_at_risk"], w["promise_at_risk_cap"]),
                              " · ".join(inputs.promises_at_risk)))
    if inputs.owners_leaving:
        factors.append(Factor("internal_owner_leaving", f"{inputs.owners_leaving[0].split(' (')[0]} is leaving",
                              w["internal_owner_leaving"], " · ".join(inputs.owners_leaving)))
    if inputs.wallet_balance is not None and inputs.wallet_balance < WALLET_LOW_INR:
        factors.append(Factor("wallet_low", "Wallet nearly empty", w["wallet_low"],
                              f"Wallet balance ₹{inputs.wallet_balance:,} (below ₹{WALLET_LOW_INR:,})"))
    total = w["base"] + sum(f.points for f in factors)
    return max(RISK_FLOOR, min(RISK_CEILING, total)), factors


def hint(inputs: RiskInputs, risk: int, factors: list[Factor], crm_score: int) -> str:
    """One-line explanation for the Risk Radar card."""
    risky = sorted((f for f in factors if f.points > 0), key=lambda f: -f.points)
    if risk >= 40 and risky:
        return " · ".join(f.label for f in risky[:2])
    counter = []
    if inputs.fixed_bug_tickets:
        counter.append("Recent tickets point to a bug that is fixed")
    if inputs.recovered_usage:
        counter.append("usage back to normal")
    if inputs.positive_signals:
        counter.append("positive signs")
    if risk < 25 and crm_score < 60 and counter:
        return " · ".join(counter[:2]).capitalize()
    if risky:
        return " · ".join(f.label for f in risky[:2])
    return "No warning signs"


def factors_as_dicts(factors: list[Factor]) -> list[dict]:
    return [asdict(f) for f in factors]


def band(risk: int) -> str:
    return "critical" if risk >= 80 else "high" if risk >= 60 else "watch" if risk >= 40 else "healthy"
