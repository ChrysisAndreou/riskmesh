"""Deterministic oracle resolution and collateral settlement."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from riskmesh.contracts import BinaryContract, ContractError, ContractStatus
from riskmesh.ledger import InsufficientFunds, Ledger
from riskmesh.market import ReplayPriceFeed


@dataclass(frozen=True, slots=True)
class SettlementResult:
    contract_id: str
    settlement_tick: int
    settlement_price: Decimal
    outcome: bool
    payout: Decimal
    winner_id: str


class ReplayOracle:
    def __init__(self, feed: ReplayPriceFeed) -> None:
        self.feed = feed

    def price_at_expiry(self, contract: BinaryContract) -> Decimal:
        return self.feed.point_at(contract.expiry_tick).close


class SettlementEngine:
    def __init__(self, ledger: Ledger, oracle: ReplayOracle) -> None:
        self.ledger = ledger
        self.oracle = oracle

    def settle(self, contract: BinaryContract, *, current_tick: int) -> SettlementResult:
        if contract.status is not ContractStatus.MATCHED:
            raise ContractError(f"Cannot settle contract in {contract.status} state")
        if current_tick < contract.expiry_tick:
            raise ContractError("Contract has not expired")
        if contract.risk_taker_id is None:
            raise ContractError("Matched contract has no risk-taker")

        taker = self.ledger.account(contract.risk_taker_id)
        if taker.locked < contract.max_payout:
            raise InsufficientFunds(
                f"{contract.contract_id} is not fully collateralized: "
                f"{taker.locked} locked for {contract.max_payout} max payout"
            )

        settlement_price = self.oracle.price_at_expiry(contract)
        outcome = contract.is_triggered(settlement_price)
        if outcome:
            self.ledger.pay_from_locked(
                contract.risk_taker_id,
                contract.hedger_id,
                contract.max_payout,
                note=f"{contract.contract_id} triggered payout",
                tick=contract.expiry_tick,
            )
            payout = contract.max_payout
            winner_id = contract.hedger_id
        else:
            self.ledger.release(
                contract.risk_taker_id,
                contract.max_payout,
                note=f"{contract.contract_id} collateral released",
                tick=contract.expiry_tick,
            )
            payout = Decimal("0")
            winner_id = contract.risk_taker_id

        contract.settlement_price = settlement_price
        contract.outcome = outcome
        contract.payout = payout
        contract.status = ContractStatus.SETTLED
        return SettlementResult(
            contract_id=contract.contract_id,
            settlement_tick=contract.expiry_tick,
            settlement_price=settlement_price,
            outcome=outcome,
            payout=payout,
            winner_id=winner_id,
        )
