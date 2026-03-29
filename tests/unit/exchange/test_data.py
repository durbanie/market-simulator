"""Tests for Order and Transaction data classes."""

from decimal import Decimal

from market_simulator.core.exchange_enums import (
    OrderStatus,
    OrderType,
    RejectionReason,
    Side,
)
from market_simulator.exchange.data import Order, Transaction


class TestOrder:
    def test_limit_order_construction(self):
        order = Order(
            order_id=1,
            participant_id=100,
            creation_timestamp=1000000,
            last_modified_timestamp=1000000,
            instrument="XYZ",
            side=Side.BUY,
            order_type=OrderType.LIMIT,
            price=Decimal("50.00"),
            quantity=Decimal("10.0000"),
            remaining_quantity=Decimal("10.0000"),
            status=OrderStatus.ACCEPTED,
        )
        assert order.order_id == 1
        assert order.participant_id == 100
        assert order.instrument == "XYZ"
        assert order.side == Side.BUY
        assert order.order_type == OrderType.LIMIT
        assert order.price == Decimal("50.00")
        assert order.quantity == Decimal("10.0000")
        assert order.remaining_quantity == Decimal("10.0000")
        assert order.status == OrderStatus.ACCEPTED
        assert order.rejection_reason is None

    def test_market_order_price_is_none(self):
        order = Order(
            order_id=2,
            participant_id=101,
            creation_timestamp=2000000,
            last_modified_timestamp=2000000,
            instrument="XYZ",
            side=Side.SELL,
            order_type=OrderType.MARKET,
            price=None,
            quantity=Decimal("5.0000"),
            remaining_quantity=Decimal("5.0000"),
            status=OrderStatus.ACCEPTED,
        )
        assert order.price is None
        assert order.order_type == OrderType.MARKET

    def test_rejected_order_has_reason(self):
        order = Order(
            order_id=3,
            participant_id=102,
            creation_timestamp=3000000,
            last_modified_timestamp=3000000,
            instrument="XYZ",
            side=Side.BUY,
            order_type=OrderType.LIMIT,
            price=Decimal("-1.00"),
            quantity=Decimal("10.0000"),
            remaining_quantity=Decimal("10.0000"),
            status=OrderStatus.REJECTED,
            rejection_reason=RejectionReason.NON_POSITIVE_PRICE,
        )
        assert order.status == OrderStatus.REJECTED
        assert order.rejection_reason == RejectionReason.NON_POSITIVE_PRICE

    def test_fractional_quantity(self):
        order = Order(
            order_id=4,
            participant_id=103,
            creation_timestamp=4000000,
            last_modified_timestamp=4000000,
            instrument="XYZ",
            side=Side.BUY,
            order_type=OrderType.LIMIT,
            price=Decimal("25.50"),
            quantity=Decimal("0.5000"),
            remaining_quantity=Decimal("0.5000"),
            status=OrderStatus.ACCEPTED,
        )
        assert order.quantity == Decimal("0.5000")

    def test_timestamps_are_integers(self):
        order = Order(
            order_id=5,
            participant_id=104,
            creation_timestamp=1719849600000000,
            last_modified_timestamp=1719849600000000,
            instrument="XYZ",
            side=Side.SELL,
            order_type=OrderType.LIMIT,
            price=Decimal("100.00"),
            quantity=Decimal("1.0000"),
            remaining_quantity=Decimal("1.0000"),
            status=OrderStatus.ACCEPTED,
        )
        assert isinstance(order.creation_timestamp, int)
        assert isinstance(order.last_modified_timestamp, int)


class TestTransaction:
    def test_construction(self):
        tx = Transaction(
            transaction_id=1,
            timestamp=5000000,
            instrument="XYZ",
            price=Decimal("50.05"),
            quantity=Decimal("10.0000"),
            maker_order_id=100,
            taker_order_id=200,
            maker_participant_id=1,
            taker_participant_id=2,
            maker_fee=Decimal("-0.02"),
            taker_fee=Decimal("0.04"),
        )
        assert tx.transaction_id == 1
        assert tx.timestamp == 5000000
        assert tx.instrument == "XYZ"
        assert tx.price == Decimal("50.05")
        assert tx.quantity == Decimal("10.0000")
        assert tx.maker_order_id == 100
        assert tx.taker_order_id == 200
        assert tx.maker_participant_id == 1
        assert tx.taker_participant_id == 2
        assert tx.maker_fee == Decimal("-0.02")
        assert tx.taker_fee == Decimal("0.04")

    def test_maker_fee_is_negative_rebate(self):
        tx = Transaction(
            transaction_id=2,
            timestamp=6000000,
            instrument="XYZ",
            price=Decimal("50.00"),
            quantity=Decimal("100.0000"),
            maker_order_id=101,
            taker_order_id=201,
            maker_participant_id=1,
            taker_participant_id=2,
            maker_fee=Decimal("-0.15"),
            taker_fee=Decimal("0.35"),
        )
        assert tx.maker_fee < 0
        assert tx.taker_fee > 0
