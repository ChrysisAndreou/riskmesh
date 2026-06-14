from decimal import Decimal

import pytest

from riskmesh.contracts import BinaryContract, ContractError, ContractStatus, TriggerDirection
from riskmesh.ledger import AccountRole, Ledger
from riskmesh.market import ReplayPriceFeed
from riskmesh.settlement import ReplayOracle, SettlementEngine


def matched_contract(feed: ReplayPriceFeed, strike_offset: Decimal) -> BinaryContract:
    expiry_tick = 2
    contract = BinaryContract(
        underlying="BTCUSDT",
        strike=feed.point_at(expiry_tick).close + strike_offset,
        created_tick=0,
        expiry_tick=expiry_tick,
        notional=Decimal("25"),
        hedger_id="hedger",
        direction=TriggerDirection.ABOVE,
    )
    contract.mark_matched(
        risk_taker_id="taker",
        fair_probability=Decimal("0.50"),
        premium=Decimal("12.50"),
        venue_fee=Decimal("0.10"),
    )
    return contract


def settlement_engine(feed: ReplayPriceFeed) -> tuple[Ledger, SettlementEngine]:
    ledger = Ledger()
    ledger.create_account("hedger", "Hedger", AccountRole.HEDGER, "100")
    ledger.create_account("taker", "Taker", AccountRole.RISK_TAKER, "100")
    ledger.lock("taker", "25", note="test collateral", tick=0)
    return ledger, SettlementEngine(ledger, ReplayOracle(feed))


def test_triggered_contract_pays_from_locked_collateral() -> None:
    feed = ReplayPriceFeed.from_csv()
    ledger, engine = settlement_engine(feed)
    contract = matched_contract(feed, Decimal("-1"))

    result = engine.settle(contract, current_tick=2)

    assert result.outcome is True
    assert result.payout == Decimal("25")
    assert ledger.account("hedger").available == Decimal("125")
    assert ledger.account("taker").locked == Decimal("0")
    assert contract.status is ContractStatus.SETTLED


def test_untriggered_contract_releases_collateral() -> None:
    feed = ReplayPriceFeed.from_csv()
    ledger, engine = settlement_engine(feed)
    contract = matched_contract(feed, Decimal("1"))

    result = engine.settle(contract, current_tick=2)

    assert result.outcome is False
    assert result.payout == Decimal("0")
    assert ledger.account("taker").available == Decimal("100")


def test_contract_cannot_settle_before_expiry() -> None:
    feed = ReplayPriceFeed.from_csv()
    _, engine = settlement_engine(feed)
    contract = matched_contract(feed, Decimal("-1"))

    with pytest.raises(ContractError, match="not expired"):
        engine.settle(contract, current_tick=1)
