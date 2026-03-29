"""Tests for Exchange: order processing, validation, and state management."""

from decimal import Decimal

from market_simulator.core.clock import Clock, ClockMode
from market_simulator.core.exchange_enums import (
    OrderStatus,
    OrderType,
    RejectionReason,
    Side,
)
from market_simulator.exchange.exchange import Exchange, ExchangeConfig


def _make_exchange(
    instruments: list[str] | None = None,
    starting_order_id: int = 1,
    starting_participant_id: int = 1,
) -> Exchange:
    """Create an exchange with sensible defaults for testing."""
    config = ExchangeConfig(
        instruments=instruments or ["XYZ"],
        starting_order_id=starting_order_id,
        starting_participant_id=starting_participant_id,
    )
    clock = Clock(mode=ClockMode.FAST_SIMULATION)
    return Exchange(config, clock)


class TestOpenClose:
    def test_exchange_starts_closed(self):
        ex = _make_exchange()
        assert not ex.is_open

    def test_open(self):
        ex = _make_exchange()
        ex.open()
        assert ex.is_open

    def test_close(self):
        ex = _make_exchange()
        ex.open()
        ex.close()
        assert not ex.is_open


class TestRegistration:
    def test_register_returns_incrementing_ids(self):
        ex = _make_exchange(starting_participant_id=100)
        assert ex.register_participant() == 100
        assert ex.register_participant() == 101
        assert ex.register_participant() == 102


class TestSubmitOrder:
    def test_limit_buy_accepted(self):
        ex = _make_exchange()
        ex.open()
        pid = ex.register_participant()
        order = ex.submit_order(pid, "XYZ", Side.BUY, OrderType.LIMIT, Decimal("50.00"), Decimal("10"))
        assert order.status == OrderStatus.ACCEPTED
        assert order.order_id == 1
        assert order.participant_id == pid
        assert order.instrument == "XYZ"
        assert order.side == Side.BUY
        assert order.order_type == OrderType.LIMIT
        assert order.price == Decimal("50.00")
        assert order.quantity == Decimal("10")
        assert order.remaining_quantity == Decimal("10")
        assert order.rejection_reason is None

    def test_limit_sell_accepted(self):
        ex = _make_exchange()
        ex.open()
        pid = ex.register_participant()
        order = ex.submit_order(pid, "XYZ", Side.SELL, OrderType.LIMIT, Decimal("55.00"), Decimal("5"))
        assert order.status == OrderStatus.ACCEPTED

    def test_market_buy_accepted(self):
        ex = _make_exchange()
        ex.open()
        pid = ex.register_participant()
        order = ex.submit_order(pid, "XYZ", Side.BUY, OrderType.MARKET, None, Decimal("10"))
        assert order.status == OrderStatus.ACCEPTED
        assert order.price is None

    def test_order_ids_increment(self):
        ex = _make_exchange(starting_order_id=100)
        ex.open()
        pid = ex.register_participant()
        o1 = ex.submit_order(pid, "XYZ", Side.BUY, OrderType.LIMIT, Decimal("50"), Decimal("10"))
        o2 = ex.submit_order(pid, "XYZ", Side.SELL, OrderType.LIMIT, Decimal("55"), Decimal("10"))
        assert o1.order_id == 100
        assert o2.order_id == 101

    def test_limit_order_appears_on_book(self):
        ex = _make_exchange()
        ex.open()
        pid = ex.register_participant()
        ex.submit_order(pid, "XYZ", Side.BUY, OrderType.LIMIT, Decimal("50.00"), Decimal("10"))
        depth = ex.get_depth("XYZ", 5)
        assert depth["bids"] == [(Decimal("50.00"), Decimal("10"))]

    def test_market_order_does_not_appear_on_book(self):
        ex = _make_exchange()
        ex.open()
        pid = ex.register_participant()
        ex.submit_order(pid, "XYZ", Side.BUY, OrderType.MARKET, None, Decimal("10"))
        depth = ex.get_depth("XYZ", 5)
        assert depth["bids"] == []

    def test_timestamps_set_from_clock(self):
        config = ExchangeConfig(instruments=["XYZ"])
        clock = Clock(mode=ClockMode.FAST_SIMULATION, offset_us=5000000)
        ex = Exchange(config, clock)
        ex.open()
        pid = ex.register_participant()
        order = ex.submit_order(pid, "XYZ", Side.BUY, OrderType.LIMIT, Decimal("50"), Decimal("10"))
        assert order.creation_timestamp == 5000000
        assert order.last_modified_timestamp == 5000000


class TestRejections:
    def test_reject_exchange_closed(self):
        ex = _make_exchange()
        pid = ex.register_participant()
        order = ex.submit_order(pid, "XYZ", Side.BUY, OrderType.LIMIT, Decimal("50"), Decimal("10"))
        assert order.status == OrderStatus.REJECTED
        assert order.rejection_reason == RejectionReason.EXCHANGE_CLOSED

    def test_reject_unregistered_participant(self):
        ex = _make_exchange()
        ex.open()
        order = ex.submit_order(999, "XYZ", Side.BUY, OrderType.LIMIT, Decimal("50"), Decimal("10"))
        assert order.status == OrderStatus.REJECTED
        assert order.rejection_reason == RejectionReason.UNREGISTERED_PARTICIPANT

    def test_reject_unsupported_instrument(self):
        ex = _make_exchange(instruments=["XYZ"])
        ex.open()
        pid = ex.register_participant()
        order = ex.submit_order(pid, "ABC", Side.BUY, OrderType.LIMIT, Decimal("50"), Decimal("10"))
        assert order.status == OrderStatus.REJECTED
        assert order.rejection_reason == RejectionReason.UNSUPPORTED_INSTRUMENT

    def test_reject_non_positive_price(self):
        ex = _make_exchange()
        ex.open()
        pid = ex.register_participant()
        order = ex.submit_order(pid, "XYZ", Side.BUY, OrderType.LIMIT, Decimal("0"), Decimal("10"))
        assert order.status == OrderStatus.REJECTED
        assert order.rejection_reason == RejectionReason.NON_POSITIVE_PRICE

    def test_reject_negative_price(self):
        ex = _make_exchange()
        ex.open()
        pid = ex.register_participant()
        order = ex.submit_order(pid, "XYZ", Side.BUY, OrderType.LIMIT, Decimal("-1"), Decimal("10"))
        assert order.status == OrderStatus.REJECTED
        assert order.rejection_reason == RejectionReason.NON_POSITIVE_PRICE

    def test_reject_none_price_for_limit(self):
        ex = _make_exchange()
        ex.open()
        pid = ex.register_participant()
        order = ex.submit_order(pid, "XYZ", Side.BUY, OrderType.LIMIT, None, Decimal("10"))
        assert order.status == OrderStatus.REJECTED
        assert order.rejection_reason == RejectionReason.NON_POSITIVE_PRICE

    def test_reject_non_positive_quantity(self):
        ex = _make_exchange()
        ex.open()
        pid = ex.register_participant()
        order = ex.submit_order(pid, "XYZ", Side.BUY, OrderType.LIMIT, Decimal("50"), Decimal("0"))
        assert order.status == OrderStatus.REJECTED
        assert order.rejection_reason == RejectionReason.NON_POSITIVE_QUANTITY

    def test_reject_negative_quantity(self):
        ex = _make_exchange()
        ex.open()
        pid = ex.register_participant()
        order = ex.submit_order(pid, "XYZ", Side.BUY, OrderType.LIMIT, Decimal("50"), Decimal("-5"))
        assert order.status == OrderStatus.REJECTED
        assert order.rejection_reason == RejectionReason.NON_POSITIVE_QUANTITY

    def test_rejected_order_not_on_book(self):
        ex = _make_exchange()
        # Exchange is closed, so order is rejected.
        pid = ex.register_participant()
        ex.submit_order(pid, "XYZ", Side.BUY, OrderType.LIMIT, Decimal("50"), Decimal("10"))
        ex.open()
        depth = ex.get_depth("XYZ", 5)
        assert depth["bids"] == []

    def test_rejected_order_still_gets_order_id(self):
        ex = _make_exchange(starting_order_id=100)
        pid = ex.register_participant()
        order = ex.submit_order(pid, "XYZ", Side.BUY, OrderType.LIMIT, Decimal("50"), Decimal("10"))
        assert order.order_id == 100
        assert order.status == OrderStatus.REJECTED


class TestModifyOrder:
    def test_modify_quantity_down_keeps_priority(self):
        ex = _make_exchange()
        ex.open()
        pid = ex.register_participant()
        o1 = ex.submit_order(pid, "XYZ", Side.BUY, OrderType.LIMIT, Decimal("50"), Decimal("100"))
        o2 = ex.submit_order(pid, "XYZ", Side.BUY, OrderType.LIMIT, Decimal("50"), Decimal("100"))
        ex.modify_order(pid, o1.order_id, new_price=None, new_quantity=Decimal("80"))
        # o1 still at front (priority maintained).
        depth = ex.get_depth("XYZ", 5)
        assert depth["bids"] == [(Decimal("50"), Decimal("180"))]
        assert o1.remaining_quantity == Decimal("80")

    def test_modify_quantity_up_loses_priority(self):
        ex = _make_exchange()
        ex.open()
        pid = ex.register_participant()
        o1 = ex.submit_order(pid, "XYZ", Side.BUY, OrderType.LIMIT, Decimal("50"), Decimal("100"))
        o2 = ex.submit_order(pid, "XYZ", Side.BUY, OrderType.LIMIT, Decimal("50"), Decimal("100"))
        ex.modify_order(pid, o1.order_id, new_price=None, new_quantity=Decimal("150"))
        # o2 should now be at the front.
        book = ex._order_books["XYZ"]
        assert book.peek_best_bid() is o2

    def test_modify_price_change_loses_priority(self):
        ex = _make_exchange()
        ex.open()
        pid = ex.register_participant()
        o1 = ex.submit_order(pid, "XYZ", Side.BUY, OrderType.LIMIT, Decimal("50"), Decimal("100"))
        o2 = ex.submit_order(pid, "XYZ", Side.BUY, OrderType.LIMIT, Decimal("50"), Decimal("100"))
        ex.modify_order(pid, o1.order_id, new_price=Decimal("49"), new_quantity=Decimal("100"))
        # Price changed — loses priority at new level.
        book = ex._order_books["XYZ"]
        assert book.peek_best_bid() is o2
        assert o1.price == Decimal("49")

    def test_modify_same_price_keeps_priority(self):
        ex = _make_exchange()
        ex.open()
        pid = ex.register_participant()
        o1 = ex.submit_order(pid, "XYZ", Side.BUY, OrderType.LIMIT, Decimal("50"), Decimal("100"))
        o2 = ex.submit_order(pid, "XYZ", Side.BUY, OrderType.LIMIT, Decimal("50"), Decimal("100"))
        ex.modify_order(pid, o1.order_id, new_price=None, new_quantity=Decimal("100"))
        # No price change, no quantity change — keeps priority.
        book = ex._order_books["XYZ"]
        assert book.peek_best_bid() is o1

    def test_modify_to_filled_when_new_total_lte_filled(self):
        ex = _make_exchange()
        ex.open()
        pid = ex.register_participant()
        o = ex.submit_order(pid, "XYZ", Side.BUY, OrderType.LIMIT, Decimal("50"), Decimal("100"))
        # Simulate partial fill: 60 of 100 filled.
        o.status = OrderStatus.PARTIALLY_FILLED
        o.remaining_quantity = Decimal("40")
        result = ex.modify_order(pid, o.order_id, new_price=None, new_quantity=Decimal("60"))
        assert result is o
        assert o.status == OrderStatus.FILLED
        assert o.remaining_quantity == Decimal("0")
        assert o.quantity == Decimal("60")

    def test_modify_updates_timestamp(self):
        config = ExchangeConfig(instruments=["XYZ"])
        clock = Clock(mode=ClockMode.FAST_SIMULATION, offset_us=1000)
        ex = Exchange(config, clock)
        ex.open()
        pid = ex.register_participant()
        o = ex.submit_order(pid, "XYZ", Side.BUY, OrderType.LIMIT, Decimal("50"), Decimal("100"))
        clock.advance(5000)
        ex.modify_order(pid, o.order_id, new_price=None, new_quantity=Decimal("80"))
        assert o.last_modified_timestamp == 6000

    def test_modify_nonexistent_returns_none(self):
        ex = _make_exchange()
        ex.open()
        pid = ex.register_participant()
        assert ex.modify_order(pid, 999, new_price=None, new_quantity=Decimal("50")) is None


class TestCancelOrder:
    def test_cancel_active_order(self):
        ex = _make_exchange()
        ex.open()
        pid = ex.register_participant()
        o = ex.submit_order(pid, "XYZ", Side.BUY, OrderType.LIMIT, Decimal("50"), Decimal("10"))
        result = ex.cancel_order(pid, o.order_id)
        assert result is o
        assert o.status == OrderStatus.CANCELLED

    def test_cancel_removes_from_depth(self):
        ex = _make_exchange()
        ex.open()
        pid = ex.register_participant()
        o = ex.submit_order(pid, "XYZ", Side.BUY, OrderType.LIMIT, Decimal("50"), Decimal("10"))
        ex.cancel_order(pid, o.order_id)
        depth = ex.get_depth("XYZ", 5)
        assert depth["bids"] == []

    def test_cancel_nonexistent_returns_none(self):
        ex = _make_exchange()
        ex.open()
        pid = ex.register_participant()
        assert ex.cancel_order(pid, 999) is None


class TestQueryMethods:
    def test_get_transactions_empty(self):
        ex = _make_exchange()
        assert ex.get_transactions() == []

    def test_get_depth_unknown_instrument(self):
        ex = _make_exchange(instruments=["XYZ"])
        assert ex.get_depth("ABC", 5) == {"bids": [], "asks": []}

    def test_get_depth_multiple_instruments(self):
        ex = _make_exchange(instruments=["XYZ", "ABC"])
        ex.open()
        pid = ex.register_participant()
        ex.submit_order(pid, "XYZ", Side.BUY, OrderType.LIMIT, Decimal("50"), Decimal("10"))
        ex.submit_order(pid, "ABC", Side.SELL, OrderType.LIMIT, Decimal("25"), Decimal("5"))
        xyz_depth = ex.get_depth("XYZ", 5)
        abc_depth = ex.get_depth("ABC", 5)
        assert xyz_depth["bids"] == [(Decimal("50"), Decimal("10"))]
        assert abc_depth["asks"] == [(Decimal("25"), Decimal("5"))]

    def test_get_order(self):
        ex = _make_exchange()
        ex.open()
        pid = ex.register_participant()
        o = ex.submit_order(pid, "XYZ", Side.BUY, OrderType.LIMIT, Decimal("50"), Decimal("10"))
        assert ex.get_order(o.order_id) is o

    def test_get_order_not_found(self):
        ex = _make_exchange()
        assert ex.get_order(999) is None


class TestMultipleInstruments:
    def test_orders_go_to_correct_book(self):
        ex = _make_exchange(instruments=["XYZ", "ABC"])
        ex.open()
        pid = ex.register_participant()
        ex.submit_order(pid, "XYZ", Side.BUY, OrderType.LIMIT, Decimal("50"), Decimal("10"))
        ex.submit_order(pid, "ABC", Side.BUY, OrderType.LIMIT, Decimal("25"), Decimal("20"))
        xyz = ex.get_depth("XYZ", 5)
        abc = ex.get_depth("ABC", 5)
        assert len(xyz["bids"]) == 1
        assert len(abc["bids"]) == 1
        assert xyz["bids"][0] == (Decimal("50"), Decimal("10"))
        assert abc["bids"][0] == (Decimal("25"), Decimal("20"))
