"""Tests for OrderBook price-time priority order book."""

from decimal import Decimal

from market_simulator.core.exchange_enums import OrderStatus, OrderType, Side
from market_simulator.exchange.data import Order
from market_simulator.exchange.order_book import OrderBook


def _make_order(
    order_id: int,
    side: Side,
    price: Decimal,
    quantity: Decimal = Decimal("10"),
    status: OrderStatus = OrderStatus.ACCEPTED,
) -> Order:
    """Helper to create a limit order with sensible defaults."""
    return Order(
        order_id=order_id,
        participant_id=1,
        creation_timestamp=order_id * 1000,
        last_modified_timestamp=order_id * 1000,
        instrument="XYZ",
        side=side,
        order_type=OrderType.LIMIT,
        price=price,
        quantity=quantity,
        remaining_quantity=quantity,
        status=status,
    )


class TestEmptyBook:
    def test_best_bid_is_none(self):
        book = OrderBook("XYZ")
        assert book.best_bid_price() is None

    def test_best_ask_is_none(self):
        book = OrderBook("XYZ")
        assert book.best_ask_price() is None

    def test_peek_best_bid_is_none(self):
        book = OrderBook("XYZ")
        assert book.peek_best_bid() is None

    def test_peek_best_ask_is_none(self):
        book = OrderBook("XYZ")
        assert book.peek_best_ask() is None

    def test_get_depth_is_empty(self):
        book = OrderBook("XYZ")
        depth = book.get_depth(5)
        assert depth == {"bids": [], "asks": []}

    def test_cancel_nonexistent_returns_none(self):
        book = OrderBook("XYZ")
        assert book.cancel_order(999) is None

    def test_get_nonexistent_returns_none(self):
        book = OrderBook("XYZ")
        assert book.get_order(999) is None


class TestAddAndBestPrice:
    def test_single_bid(self):
        book = OrderBook("XYZ")
        book.add_order(_make_order(1, Side.BUY, Decimal("50.00")))
        assert book.best_bid_price() == Decimal("50.00")
        assert book.best_ask_price() is None

    def test_single_ask(self):
        book = OrderBook("XYZ")
        book.add_order(_make_order(1, Side.SELL, Decimal("55.00")))
        assert book.best_ask_price() == Decimal("55.00")
        assert book.best_bid_price() is None

    def test_best_bid_is_highest(self):
        book = OrderBook("XYZ")
        book.add_order(_make_order(1, Side.BUY, Decimal("49.00")))
        book.add_order(_make_order(2, Side.BUY, Decimal("51.00")))
        book.add_order(_make_order(3, Side.BUY, Decimal("50.00")))
        assert book.best_bid_price() == Decimal("51.00")

    def test_best_ask_is_lowest(self):
        book = OrderBook("XYZ")
        book.add_order(_make_order(1, Side.SELL, Decimal("56.00")))
        book.add_order(_make_order(2, Side.SELL, Decimal("54.00")))
        book.add_order(_make_order(3, Side.SELL, Decimal("55.00")))
        assert book.best_ask_price() == Decimal("54.00")


class TestPriceTimePriority:
    def test_fifo_within_bid_level(self):
        book = OrderBook("XYZ")
        o1 = _make_order(1, Side.BUY, Decimal("50.00"))
        o2 = _make_order(2, Side.BUY, Decimal("50.00"))
        o3 = _make_order(3, Side.BUY, Decimal("50.00"))
        book.add_order(o1)
        book.add_order(o2)
        book.add_order(o3)
        assert book.peek_best_bid() is o1

    def test_fifo_within_ask_level(self):
        book = OrderBook("XYZ")
        o1 = _make_order(1, Side.SELL, Decimal("55.00"))
        o2 = _make_order(2, Side.SELL, Decimal("55.00"))
        book.add_order(o1)
        book.add_order(o2)
        assert book.peek_best_ask() is o1

    def test_price_priority_over_time_for_bids(self):
        book = OrderBook("XYZ")
        o1 = _make_order(1, Side.BUY, Decimal("49.00"))
        o2 = _make_order(2, Side.BUY, Decimal("51.00"))
        book.add_order(o1)
        book.add_order(o2)
        # Higher price bid has priority even though added second.
        assert book.peek_best_bid() is o2

    def test_price_priority_over_time_for_asks(self):
        book = OrderBook("XYZ")
        o1 = _make_order(1, Side.SELL, Decimal("56.00"))
        o2 = _make_order(2, Side.SELL, Decimal("54.00"))
        book.add_order(o1)
        book.add_order(o2)
        # Lower price ask has priority even though added second.
        assert book.peek_best_ask() is o2


class TestCancelOrder:
    def test_cancel_marks_cancelled(self):
        book = OrderBook("XYZ")
        o = _make_order(1, Side.BUY, Decimal("50.00"))
        book.add_order(o)
        result = book.cancel_order(1)
        assert result is o
        assert o.status == OrderStatus.CANCELLED

    def test_cancelled_order_skipped_by_best_bid(self):
        book = OrderBook("XYZ")
        o1 = _make_order(1, Side.BUY, Decimal("51.00"))
        o2 = _make_order(2, Side.BUY, Decimal("50.00"))
        book.add_order(o1)
        book.add_order(o2)
        book.cancel_order(1)
        assert book.best_bid_price() == Decimal("50.00")

    def test_cancelled_order_skipped_by_best_ask(self):
        book = OrderBook("XYZ")
        o1 = _make_order(1, Side.SELL, Decimal("54.00"))
        o2 = _make_order(2, Side.SELL, Decimal("55.00"))
        book.add_order(o1)
        book.add_order(o2)
        book.cancel_order(1)
        assert book.best_ask_price() == Decimal("55.00")

    def test_cancel_all_bids_gives_none(self):
        book = OrderBook("XYZ")
        book.add_order(_make_order(1, Side.BUY, Decimal("50.00")))
        book.cancel_order(1)
        assert book.best_bid_price() is None
        assert book.peek_best_bid() is None

    def test_cancel_already_filled_returns_none(self):
        book = OrderBook("XYZ")
        o = _make_order(1, Side.BUY, Decimal("50.00"))
        book.add_order(o)
        o.status = OrderStatus.FILLED
        assert book.cancel_order(1) is None
        assert o.status == OrderStatus.FILLED

    def test_cancel_already_cancelled_returns_none(self):
        book = OrderBook("XYZ")
        o = _make_order(1, Side.BUY, Decimal("50.00"))
        book.add_order(o)
        book.cancel_order(1)
        assert book.cancel_order(1) is None


class TestLazyDeletion:
    def test_peek_skips_cancelled_at_front(self):
        book = OrderBook("XYZ")
        o1 = _make_order(1, Side.BUY, Decimal("50.00"))
        o2 = _make_order(2, Side.BUY, Decimal("50.00"))
        book.add_order(o1)
        book.add_order(o2)
        book.cancel_order(1)
        assert book.peek_best_bid() is o2

    def test_peek_skips_filled_at_front(self):
        book = OrderBook("XYZ")
        o1 = _make_order(1, Side.SELL, Decimal("55.00"))
        o2 = _make_order(2, Side.SELL, Decimal("55.00"))
        book.add_order(o1)
        book.add_order(o2)
        o1.status = OrderStatus.FILLED
        assert book.peek_best_ask() is o2

    def test_peek_skips_to_next_price_level(self):
        book = OrderBook("XYZ")
        o1 = _make_order(1, Side.SELL, Decimal("54.00"))
        o2 = _make_order(2, Side.SELL, Decimal("55.00"))
        book.add_order(o1)
        book.add_order(o2)
        book.cancel_order(1)
        assert book.peek_best_ask() is o2


class TestGetOrder:
    def test_get_existing_order(self):
        book = OrderBook("XYZ")
        o = _make_order(1, Side.BUY, Decimal("50.00"))
        book.add_order(o)
        assert book.get_order(1) is o

    def test_get_order_after_cancel(self):
        book = OrderBook("XYZ")
        o = _make_order(1, Side.BUY, Decimal("50.00"))
        book.add_order(o)
        book.cancel_order(1)
        # Still accessible via get_order (lazy deletion).
        assert book.get_order(1) is o
        assert o.status == OrderStatus.CANCELLED


class TestModifyOrder:
    def test_modify_without_priority_loss(self):
        book = OrderBook("XYZ")
        o1 = _make_order(1, Side.BUY, Decimal("50.00"), Decimal("100"))
        o2 = _make_order(2, Side.BUY, Decimal("50.00"), Decimal("100"))
        book.add_order(o1)
        book.add_order(o2)
        # Reduce quantity — keeps priority. Caller computes new fields.
        result = book.modify_order(
            1, new_price=None, new_quantity=Decimal("50"),
            new_remaining=Decimal("50"), loses_priority=False,
        )
        assert result is o1
        assert o1.quantity == Decimal("50")
        assert o1.remaining_quantity == Decimal("50")
        # o1 is still at the front.
        assert book.peek_best_bid() is o1

    def test_modify_with_priority_loss_same_price(self):
        book = OrderBook("XYZ")
        o1 = _make_order(1, Side.BUY, Decimal("50.00"), Decimal("100"))
        o2 = _make_order(2, Side.BUY, Decimal("50.00"), Decimal("100"))
        book.add_order(o1)
        book.add_order(o2)
        # Increase quantity — loses priority.
        result = book.modify_order(
            1, new_price=None, new_quantity=Decimal("150"),
            new_remaining=Decimal("150"), loses_priority=True,
        )
        assert result is o1
        assert o1.remaining_quantity == Decimal("150")
        # o2 should now be at the front.
        assert book.peek_best_bid() is o2

    def test_modify_with_price_change(self):
        book = OrderBook("XYZ")
        o1 = _make_order(1, Side.BUY, Decimal("50.00"), Decimal("100"))
        o2 = _make_order(2, Side.BUY, Decimal("50.00"), Decimal("100"))
        book.add_order(o1)
        book.add_order(o2)
        # Move to better price — loses priority at new level.
        result = book.modify_order(
            1, new_price=Decimal("51.00"), new_quantity=Decimal("100"),
            new_remaining=Decimal("100"), loses_priority=True,
        )
        assert result is o1
        assert o1.price == Decimal("51.00")
        assert book.best_bid_price() == Decimal("51.00")
        assert book.peek_best_bid() is o1

    def test_modify_price_change_to_worse_price(self):
        book = OrderBook("XYZ")
        o1 = _make_order(1, Side.BUY, Decimal("51.00"), Decimal("100"))
        o2 = _make_order(2, Side.BUY, Decimal("50.00"), Decimal("100"))
        book.add_order(o1)
        book.add_order(o2)
        # Move o1 to worse price.
        book.modify_order(
            1, new_price=Decimal("49.00"), new_quantity=Decimal("100"),
            new_remaining=Decimal("100"), loses_priority=True,
        )
        assert book.best_bid_price() == Decimal("50.00")
        assert book.peek_best_bid() is o2

    def test_modify_cancelled_order_returns_none(self):
        book = OrderBook("XYZ")
        o = _make_order(1, Side.BUY, Decimal("50.00"), Decimal("100"))
        book.add_order(o)
        book.cancel_order(1)
        result = book.modify_order(
            1, new_price=None, new_quantity=Decimal("50"),
            new_remaining=Decimal("50"), loses_priority=False,
        )
        assert result is None
        # Original fields unchanged.
        assert o.quantity == Decimal("100")
        assert o.remaining_quantity == Decimal("100")

    def test_modify_filled_order_returns_none(self):
        book = OrderBook("XYZ")
        o = _make_order(1, Side.SELL, Decimal("55.00"), Decimal("100"))
        book.add_order(o)
        o.status = OrderStatus.FILLED
        result = book.modify_order(
            1, new_price=Decimal("56.00"), new_quantity=Decimal("100"),
            new_remaining=Decimal("100"), loses_priority=True,
        )
        assert result is None

    def test_modify_nonexistent_order_returns_none(self):
        book = OrderBook("XYZ")
        result = book.modify_order(
            999, new_price=None, new_quantity=Decimal("50"),
            new_remaining=Decimal("50"), loses_priority=False,
        )
        assert result is None

    def test_modify_partially_filled_order(self):
        """Caller provides pre-computed quantity and remaining."""
        book = OrderBook("XYZ")
        o = _make_order(1, Side.BUY, Decimal("50.00"), Decimal("100"))
        book.add_order(o)
        # Simulate a partial fill: 30 of 100 filled.
        o.status = OrderStatus.PARTIALLY_FILLED
        o.remaining_quantity = Decimal("70")
        # Caller computes: new_total=120, filled=30, new_remaining=90.
        result = book.modify_order(
            1, new_price=None, new_quantity=Decimal("120"),
            new_remaining=Decimal("90"), loses_priority=True,
        )
        assert result is o
        assert o.quantity == Decimal("120")
        assert o.remaining_quantity == Decimal("90")


class TestGetDepth:
    def test_single_level_per_side(self):
        book = OrderBook("XYZ")
        book.add_order(_make_order(1, Side.BUY, Decimal("50.00"), Decimal("10")))
        book.add_order(_make_order(2, Side.SELL, Decimal("55.00"), Decimal("20")))
        depth = book.get_depth(5)
        assert depth["bids"] == [(Decimal("50.00"), Decimal("10"))]
        assert depth["asks"] == [(Decimal("55.00"), Decimal("20"))]

    def test_multiple_orders_at_same_level_aggregated(self):
        book = OrderBook("XYZ")
        book.add_order(_make_order(1, Side.BUY, Decimal("50.00"), Decimal("10")))
        book.add_order(_make_order(2, Side.BUY, Decimal("50.00"), Decimal("15")))
        depth = book.get_depth(5)
        assert depth["bids"] == [(Decimal("50.00"), Decimal("25"))]

    def test_multiple_levels_sorted_best_to_worst(self):
        book = OrderBook("XYZ")
        book.add_order(_make_order(1, Side.BUY, Decimal("49.00"), Decimal("10")))
        book.add_order(_make_order(2, Side.BUY, Decimal("51.00"), Decimal("20")))
        book.add_order(_make_order(3, Side.BUY, Decimal("50.00"), Decimal("15")))
        depth = book.get_depth(5)
        assert depth["bids"] == [
            (Decimal("51.00"), Decimal("20")),
            (Decimal("50.00"), Decimal("15")),
            (Decimal("49.00"), Decimal("10")),
        ]

    def test_ask_depth_sorted_best_to_worst(self):
        book = OrderBook("XYZ")
        book.add_order(_make_order(1, Side.SELL, Decimal("56.00"), Decimal("10")))
        book.add_order(_make_order(2, Side.SELL, Decimal("54.00"), Decimal("20")))
        book.add_order(_make_order(3, Side.SELL, Decimal("55.00"), Decimal("15")))
        depth = book.get_depth(5)
        assert depth["asks"] == [
            (Decimal("54.00"), Decimal("20")),
            (Decimal("55.00"), Decimal("15")),
            (Decimal("56.00"), Decimal("10")),
        ]

    def test_depth_limited_to_requested_levels(self):
        book = OrderBook("XYZ")
        for i, price in enumerate([49, 50, 51, 52, 53]):
            book.add_order(_make_order(i + 1, Side.BUY, Decimal(str(price)), Decimal("10")))
        depth = book.get_depth(3)
        assert len(depth["bids"]) == 3
        assert depth["bids"][0] == (Decimal("53"), Decimal("10"))

    def test_depth_skips_cancelled_orders(self):
        book = OrderBook("XYZ")
        book.add_order(_make_order(1, Side.BUY, Decimal("50.00"), Decimal("10")))
        book.add_order(_make_order(2, Side.BUY, Decimal("50.00"), Decimal("15")))
        book.cancel_order(1)
        depth = book.get_depth(5)
        assert depth["bids"] == [(Decimal("50.00"), Decimal("15"))]

    def test_depth_skips_level_where_all_cancelled(self):
        book = OrderBook("XYZ")
        book.add_order(_make_order(1, Side.BUY, Decimal("51.00"), Decimal("10")))
        book.add_order(_make_order(2, Side.BUY, Decimal("50.00"), Decimal("20")))
        book.cancel_order(1)
        depth = book.get_depth(5)
        assert depth["bids"] == [(Decimal("50.00"), Decimal("20"))]


class TestCleanup:
    def test_cleanup_removes_cancelled_orders(self):
        book = OrderBook("XYZ")
        o1 = _make_order(1, Side.BUY, Decimal("50.00"))
        o2 = _make_order(2, Side.BUY, Decimal("50.00"))
        book.add_order(o1)
        book.add_order(o2)
        book.cancel_order(1)
        book.cleanup()
        assert book.get_order(1) is None
        assert book.get_order(2) is o2

    def test_cleanup_removes_filled_orders(self):
        book = OrderBook("XYZ")
        o = _make_order(1, Side.SELL, Decimal("55.00"))
        book.add_order(o)
        o.status = OrderStatus.FILLED
        book.cleanup()
        assert book.get_order(1) is None

    def test_cleanup_removes_empty_price_levels(self):
        book = OrderBook("XYZ")
        book.add_order(_make_order(1, Side.BUY, Decimal("50.00")))
        book.cancel_order(1)
        book.cleanup()
        # After cleanup, no levels remain — depth should be empty.
        assert book.get_depth(5) == {"bids": [], "asks": []}

    def test_cleanup_preserves_active_orders(self):
        book = OrderBook("XYZ")
        o1 = _make_order(1, Side.BUY, Decimal("50.00"))
        o2 = _make_order(2, Side.BUY, Decimal("50.00"))
        book.add_order(o1)
        book.add_order(o2)
        o1.status = OrderStatus.FILLED
        book.cleanup()
        assert book.peek_best_bid() is o2
        assert book.get_order(2) is o2

    def test_cleanup_preserves_partially_filled(self):
        book = OrderBook("XYZ")
        o = _make_order(1, Side.SELL, Decimal("55.00"), Decimal("100"))
        book.add_order(o)
        o.status = OrderStatus.PARTIALLY_FILLED
        o.remaining_quantity = Decimal("50")
        book.cleanup()
        assert book.get_order(1) is o
        assert book.peek_best_ask() is o

    def test_cleanup_on_empty_book(self):
        book = OrderBook("XYZ")
        book.cleanup()  # Should not raise.
        assert book.get_depth(5) == {"bids": [], "asks": []}


class TestInstrument:
    def test_instrument_stored(self):
        book = OrderBook("ABC")
        assert book.instrument == "ABC"
