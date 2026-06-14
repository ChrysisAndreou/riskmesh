"""In-memory double-entry-style ledger for the simulated venue."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from enum import StrEnum
from uuid import uuid4

ZERO = Decimal("0")


class LedgerError(ValueError):
    """Base class for invalid ledger operations."""


class InsufficientFunds(LedgerError):
    """Raised when an account cannot fund an operation."""


class AccountRole(StrEnum):
    FORECASTER = "forecaster"
    HEDGER = "hedger"
    RISK_TAKER = "risk_taker"
    VENUE = "venue"


class TransactionKind(StrEnum):
    TRANSFER = "transfer"
    COLLATERAL_LOCK = "collateral_lock"
    COLLATERAL_RELEASE = "collateral_release"
    COLLATERAL_PAYOUT = "collateral_payout"


@dataclass(slots=True)
class Account:
    agent_id: str
    display_name: str
    role: AccountRole
    available: Decimal
    initial_balance: Decimal
    locked: Decimal = ZERO

    @property
    def equity(self) -> Decimal:
        return self.available + self.locked

    @property
    def pnl(self) -> Decimal:
        return self.equity - self.initial_balance


@dataclass(frozen=True, slots=True)
class LedgerTransaction:
    transaction_id: str
    kind: TransactionKind
    amount: Decimal
    source: str | None
    destination: str | None
    note: str
    tick: int


@dataclass(slots=True)
class Ledger:
    accounts: dict[str, Account] = field(default_factory=dict)
    transactions: list[LedgerTransaction] = field(default_factory=list)

    def create_account(
        self,
        agent_id: str,
        display_name: str,
        role: AccountRole,
        opening_balance: Decimal | str | int,
    ) -> Account:
        if agent_id in self.accounts:
            raise LedgerError(f"Account already exists: {agent_id}")
        balance = self._amount(opening_balance)
        account = Account(agent_id, display_name, role, balance, balance)
        self.accounts[agent_id] = account
        return account

    def account(self, agent_id: str) -> Account:
        try:
            return self.accounts[agent_id]
        except KeyError as exc:
            raise LedgerError(f"Unknown account: {agent_id}") from exc

    def transfer(
        self,
        source: str,
        destination: str,
        amount: Decimal | str | int,
        *,
        note: str,
        tick: int,
    ) -> LedgerTransaction:
        value = self._amount(amount)
        source_account = self.account(source)
        destination_account = self.account(destination)
        self._require_available(source_account, value)
        source_account.available -= value
        destination_account.available += value
        return self._record(
            TransactionKind.TRANSFER, value, source, destination, note, tick
        )

    def lock(
        self,
        agent_id: str,
        amount: Decimal | str | int,
        *,
        note: str,
        tick: int,
    ) -> LedgerTransaction:
        value = self._amount(amount)
        account = self.account(agent_id)
        self._require_available(account, value)
        account.available -= value
        account.locked += value
        return self._record(
            TransactionKind.COLLATERAL_LOCK, value, agent_id, agent_id, note, tick
        )

    def release(
        self,
        agent_id: str,
        amount: Decimal | str | int,
        *,
        note: str,
        tick: int,
    ) -> LedgerTransaction:
        value = self._amount(amount)
        account = self.account(agent_id)
        self._require_locked(account, value)
        account.locked -= value
        account.available += value
        return self._record(
            TransactionKind.COLLATERAL_RELEASE, value, agent_id, agent_id, note, tick
        )

    def pay_from_locked(
        self,
        source: str,
        destination: str,
        amount: Decimal | str | int,
        *,
        note: str,
        tick: int,
    ) -> LedgerTransaction:
        value = self._amount(amount)
        source_account = self.account(source)
        destination_account = self.account(destination)
        self._require_locked(source_account, value)
        source_account.locked -= value
        destination_account.available += value
        return self._record(
            TransactionKind.COLLATERAL_PAYOUT,
            value,
            source,
            destination,
            note,
            tick,
        )

    @property
    def total_equity(self) -> Decimal:
        return sum((account.equity for account in self.accounts.values()), ZERO)

    @staticmethod
    def _amount(amount: Decimal | str | int) -> Decimal:
        value = Decimal(str(amount))
        if value <= ZERO:
            raise LedgerError("Amount must be positive")
        return value

    @staticmethod
    def _require_available(account: Account, amount: Decimal) -> None:
        if account.available < amount:
            raise InsufficientFunds(
                f"{account.agent_id} has {account.available} available, needs {amount}"
            )

    @staticmethod
    def _require_locked(account: Account, amount: Decimal) -> None:
        if account.locked < amount:
            raise InsufficientFunds(
                f"{account.agent_id} has {account.locked} locked, needs {amount}"
            )

    def _record(
        self,
        kind: TransactionKind,
        amount: Decimal,
        source: str | None,
        destination: str | None,
        note: str,
        tick: int,
    ) -> LedgerTransaction:
        transaction = LedgerTransaction(
            transaction_id=uuid4().hex[:12],
            kind=kind,
            amount=amount,
            source=source,
            destination=destination,
            note=note,
            tick=tick,
        )
        self.transactions.append(transaction)
        return transaction
