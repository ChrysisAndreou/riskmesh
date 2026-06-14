from decimal import Decimal

import pytest

from riskmesh.clearing import ClearingEngine
from riskmesh.contracts import BinaryContract, ContractStatus
from riskmesh.forecasters import BeliefAggregator, Forecast
from riskmesh.ledger import AccountRole, InsufficientFunds, Ledger


def setup_market(taker_balance: str = "100") -> tuple[Ledger, BinaryContract, object]:
    ledger = Ledger()
    ledger.create_account("hedger", "Hedger", AccountRole.HEDGER, "100")
    ledger.create_account("taker", "Taker", AccountRole.RISK_TAKER, taker_balance)
    contract = BinaryContract(
        underlying="BTCUSDT",
        strike=Decimal("65000"),
        created_tick=0,
        expiry_tick=5,
        notional=Decimal("25"),
        hedger_id="hedger",
        contract_id="RM-CLEAR",
    )
    forecast = Forecast(
        "agent",
        "Agent",
        contract.contract_id,
        0,
        Decimal("0.40"),
        "test",
        "test",
    )
    quote = BeliefAggregator().aggregate(contract, [forecast])
    return ledger, contract, quote


def test_match_locks_max_payout_before_premium_transfer() -> None:
    ledger, contract, quote = setup_market()
    opening_equity = ledger.total_equity

    result = ClearingEngine(ledger).match(
        contract, risk_taker_id="taker", quote=quote, tick=1
    )

    assert result.collateral_locked == Decimal("25")
    assert result.premium == Decimal("10.00")
    assert ledger.account("hedger").available == Decimal("90.00")
    assert ledger.account("taker").available == Decimal("85.00")
    assert ledger.account("taker").locked == Decimal("25")
    assert ledger.total_equity == opening_equity
    assert contract.status is ContractStatus.MATCHED


def test_match_fails_atomically_when_taker_cannot_fully_collateralize() -> None:
    ledger, contract, quote = setup_market(taker_balance="20")
    balances_before = {
        agent_id: (account.available, account.locked)
        for agent_id, account in ledger.accounts.items()
    }

    with pytest.raises(InsufficientFunds, match="fully collateralize"):
        ClearingEngine(ledger).match(
            contract, risk_taker_id="taker", quote=quote, tick=1
        )

    assert contract.status is ContractStatus.OPEN
    assert balances_before == {
        agent_id: (account.available, account.locked)
        for agent_id, account in ledger.accounts.items()
    }
    assert ledger.transactions == []
