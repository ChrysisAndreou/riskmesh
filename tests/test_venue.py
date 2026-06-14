from decimal import Decimal

from riskmesh.contracts import ContractStatus
from riskmesh.venue import HEDGER_ID, VENUE_ID, RiskMeshVenue


def test_full_venue_lifecycle_moves_money_scores_agents_and_collects_fee() -> None:
    venue = RiskMeshVenue(start_tick=12)
    opening_equity = venue.ledger.total_equity
    contract = venue.open_contract(
        duration_ticks=6, notional=Decimal("25"), strike_offset=Decimal("20")
    )
    quote = venue.refresh_beliefs(use_gemini=False)
    match = venue.match_active()

    assert match.collateral_locked == contract.max_payout
    assert quote.fair_premium == contract.premium
    assert venue.ledger.account(match.risk_taker_id).locked == Decimal("25")

    while contract.status is not ContractStatus.SETTLED:
        venue.advance(use_gemini=False)

    assert contract.outcome is True
    assert contract.payout == Decimal("25")
    assert venue.ledger.account(VENUE_ID).available > 0
    assert venue.ledger.account(HEDGER_ID).available != Decimal("150")
    assert all(row["forecasts"] == 5 for row in venue.leaderboard_rows())
    assert venue.ledger.total_equity == opening_equity
    assert any(event.kind == "reputation" for event in venue.events)
