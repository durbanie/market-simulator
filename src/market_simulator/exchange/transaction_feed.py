"""Shared transaction feed for broadcast-style market data.

The exchange appends transactions to the feed during order matching.
Consumers read from a cursor (last seen transaction ID) forward.
The feed does not track subscribers — it is a shared, append-only
data structure.

In network mode, this class would be replaced by a transport-specific
implementation behind the same interface.
"""

from market_simulator.exchange.data import Transaction


class TransactionFeed:
    """Append-only transaction feed with cursor-based reads.

    Args:
        starting_transaction_id: The ID of the first transaction that
            will be appended. Used for O(1) index calculation.
    """

    def __init__(self, starting_transaction_id: int = 1) -> None:
        self._transactions: list[Transaction] = []
        self._starting_id = starting_transaction_id

    def append(self, transaction: Transaction) -> None:
        """Append a transaction. Called by the exchange only."""
        self._transactions.append(transaction)

    def read_from(self, after_id: int = 0) -> list[Transaction]:
        """Return transactions with transaction_id > after_id.

        Uses sequential transaction IDs for O(1) index calculation.

        Args:
            after_id: The last transaction_id the caller has seen.
                Pass 0 to read from the beginning.

        Returns:
            List of new transactions (may be empty). Returns a copy.
        """
        if not self._transactions:
            return []
        start_index = after_id - self._starting_id + 1
        if start_index < 0:
            start_index = 0
        if start_index >= len(self._transactions):
            return []
        return list(self._transactions[start_index:])

    def peek_last(self) -> Transaction | None:
        """Return the most recent transaction, or None if empty."""
        return self._transactions[-1] if self._transactions else None

    @property
    def last_transaction_id(self) -> int:
        """The ID of the most recent transaction, or 0 if empty."""
        if self._transactions:
            return self._transactions[-1].transaction_id
        return 0
