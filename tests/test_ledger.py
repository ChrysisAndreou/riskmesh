from decimal import Decimal

import pytest

from riskmesh.ledger import AccountRole, InsufficientFunds, Ledger


def test_ledger_transfers_and_collateral_preserve_total_equity() -> None:
    ledger = Ledger()
    ledger.create_account("hedger", "Hedger", AccountRole.HEDGER, "100")
    ledger.create_account("taker", "Taker", AccountRole.RISK_TAKER, "100")
    opening_equity = ledger.total_equity

    ledger.transfer("hedger", "taker", "3", note="premium", tick=1)
    ledger.lock("taker", "20", note="max payout", tick=1)
    ledger.pay_from_locked("taker", "hedger", "20", note="claim payout", tick=2)

    assert ledger.account("hedger").available == Decimal("117")
    assert ledger.account("taker").available == Decimal("83")
    assert ledger.account("taker").locked == Decimal("0")
    assert ledger.total_equity == opening_equity


def test_ledger_rejects_under_collateralization() -> None:
    ledger = Ledger()
    ledger.create_account("taker", "Taker", AccountRole.RISK_TAKER, "10")

    with pytest.raises(InsufficientFunds):
        ledger.lock("taker", "11", note="too much", tick=0)
