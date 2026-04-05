"""Tests for TransactionFeed: shared append-only transaction feed."""

from decimal import Decimal

from market_simulator.exchange.data import Transaction
from market_simulator.exchange.transaction_feed import TransactionFeed


def _make_txn(transaction_id: int, price: str = "50.00") -> Transaction:
    """Create a minimal Transaction for testing."""
    return Transaction(
        transaction_id=transaction_id,
        timestamp=1000 + transaction_id,
        instrument="XYZ",
        price=Decimal(price),
        quantity=Decimal("10"),
        maker_order_id=1,
        taker_order_id=2,
        maker_participant_id=1,
        taker_participant_id=2,
        maker_fee=Decimal("-0.15"),
        taker_fee=Decimal("0.35"),
    )


class TestReadFrom:

    def test_empty_feed(self):
        feed = TransactionFeed()
        assert feed.read_from(0) == []

    def test_read_all_from_zero(self):
        feed = TransactionFeed()
        feed.append(_make_txn(1))
        feed.append(_make_txn(2))
        result = feed.read_from(0)
        assert len(result) == 2
        assert result[0].transaction_id == 1
        assert result[1].transaction_id == 2

    def test_read_from_cursor(self):
        feed = TransactionFeed()
        feed.append(_make_txn(1))
        feed.append(_make_txn(2))
        feed.append(_make_txn(3))
        result = feed.read_from(1)
        assert len(result) == 2
        assert result[0].transaction_id == 2
        assert result[1].transaction_id == 3

    def test_read_from_last_returns_empty(self):
        feed = TransactionFeed()
        feed.append(_make_txn(1))
        feed.append(_make_txn(2))
        assert feed.read_from(2) == []

    def test_read_from_future_cursor_returns_empty(self):
        feed = TransactionFeed()
        feed.append(_make_txn(1))
        assert feed.read_from(999) == []

    def test_returns_copy(self):
        feed = TransactionFeed()
        feed.append(_make_txn(1))
        result = feed.read_from(0)
        result.clear()
        assert len(feed.read_from(0)) == 1

    def test_custom_starting_id(self):
        feed = TransactionFeed(starting_transaction_id=100)
        feed.append(_make_txn(100))
        feed.append(_make_txn(101))
        feed.append(_make_txn(102))
        # Read from beginning.
        assert len(feed.read_from(0)) == 3
        # Read after first.
        result = feed.read_from(100)
        assert len(result) == 2
        assert result[0].transaction_id == 101
        # Read after last.
        assert feed.read_from(102) == []

    def test_custom_starting_id_cursor_before_start(self):
        feed = TransactionFeed(starting_transaction_id=50)
        feed.append(_make_txn(50))
        feed.append(_make_txn(51))
        # Cursor before the starting ID should return everything.
        result = feed.read_from(10)
        assert len(result) == 2


class TestPeekLast:

    def test_empty_feed(self):
        feed = TransactionFeed()
        assert feed.peek_last() is None

    def test_returns_last(self):
        feed = TransactionFeed()
        feed.append(_make_txn(1, "50.00"))
        feed.append(_make_txn(2, "51.00"))
        assert feed.peek_last().transaction_id == 2
        assert feed.peek_last().price == Decimal("51.00")


class TestLastTransactionId:

    def test_empty_feed(self):
        feed = TransactionFeed()
        assert feed.last_transaction_id == 0

    def test_after_append(self):
        feed = TransactionFeed()
        feed.append(_make_txn(1))
        assert feed.last_transaction_id == 1
        feed.append(_make_txn(2))
        assert feed.last_transaction_id == 2
