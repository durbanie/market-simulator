"""Tests for Exchange: order processing, validation, and state management."""

from decimal import Decimal

from market_simulator.core.clock import Clock, ClockMode
from market_simulator.core.exchange_enums import (
    Action,
    ExchangeState,
    OrderStatus,
    OrderType,
    RejectionReason,
    RequestStatus,
    Side,
)
from market_simulator.core.messages import OrderMessageRequest, OrderMessageResponse
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


def _register(ex: Exchange) -> int:
    """Register a participant and return their ID."""
    return ex.handle_registration_request().participant_id


def _submit_limit(
    ex: Exchange, pid: int, instrument: str, side: Side,
    price: Decimal, quantity: Decimal,
) -> OrderMessageResponse:
    """Submit a limit order and return the response."""
    return ex.handle_order_message(OrderMessageRequest(
        action=Action.SUBMIT,
        participant_id=pid,
        instrument=instrument,
        side=side,
        order_type=OrderType.LIMIT,
        price=price,
        quantity=quantity,
    ))


def _submit_market(
    ex: Exchange, pid: int, instrument: str, side: Side,
    quantity: Decimal,
) -> OrderMessageResponse:
    """Submit a market order and return the response."""
    return ex.handle_order_message(OrderMessageRequest(
        action=Action.SUBMIT,
        participant_id=pid,
        instrument=instrument,
        side=side,
        order_type=OrderType.MARKET,
        quantity=quantity,
    ))


class TestOpenClose:
    def test_exchange_starts_closed(self):
        ex = _make_exchange()
        assert ex.state == ExchangeState.CLOSED
        assert not ex.is_open

    def test_open(self):
        ex = _make_exchange()
        ex.open()
        assert ex.state == ExchangeState.OPEN
        assert ex.is_open

    def test_close(self):
        ex = _make_exchange()
        ex.open()
        ex.close()
        assert ex.state == ExchangeState.CLOSED
        assert not ex.is_open


class TestRegistration:
    def test_register_returns_incrementing_ids(self):
        ex = _make_exchange(starting_participant_id=100)
        r1 = ex.handle_registration_request()
        r2 = ex.handle_registration_request()
        r3 = ex.handle_registration_request()
        assert r1.participant_id == 100
        assert r2.participant_id == 101
        assert r3.participant_id == 102


class TestSubmitOrder:
    def test_limit_buy_accepted(self):
        ex = _make_exchange()
        ex.open()
        pid = _register(ex)
        resp = _submit_limit(ex, pid, "XYZ", Side.BUY, Decimal("50.00"), Decimal("10"))
        assert resp.request_status == RequestStatus.ACCEPTED
        assert resp.order_id == 1
        assert resp.rejection_reason is None
        # Response includes full order state for DMA reconstruction.
        assert resp.order_status == OrderStatus.ACCEPTED
        assert resp.instrument == "XYZ"
        assert resp.side == Side.BUY
        assert resp.order_type == OrderType.LIMIT
        assert resp.price == Decimal("50.00")
        assert resp.quantity == Decimal("10")
        assert resp.remaining_quantity == Decimal("10")
        assert resp.filled_quantity == Decimal("0")

    def test_limit_sell_accepted(self):
        ex = _make_exchange()
        ex.open()
        pid = _register(ex)
        resp = _submit_limit(ex, pid, "XYZ", Side.SELL, Decimal("55.00"), Decimal("5"))
        assert resp.request_status == RequestStatus.ACCEPTED

    def test_market_order_rejected_no_liquidity(self):
        ex = _make_exchange()
        ex.open()
        pid = _register(ex)
        resp = _submit_market(ex, pid, "XYZ", Side.BUY, Decimal("10"))
        assert resp.request_status == RequestStatus.REJECTED
        assert resp.rejection_reason == RejectionReason.NO_LIQUIDITY

    def test_order_ids_increment(self):
        ex = _make_exchange(starting_order_id=100)
        ex.open()
        pid = _register(ex)
        r1 = _submit_limit(ex, pid, "XYZ", Side.BUY, Decimal("50"), Decimal("10"))
        r2 = _submit_limit(ex, pid, "XYZ", Side.SELL, Decimal("55"), Decimal("10"))
        assert r1.order_id == 100
        assert r2.order_id == 101

    def test_limit_order_appears_on_book(self):
        ex = _make_exchange()
        ex.open()
        pid = _register(ex)
        _submit_limit(ex, pid, "XYZ", Side.BUY, Decimal("50.00"), Decimal("10"))
        depth = ex.get_depth("XYZ", 5)
        assert depth["bids"] == [(Decimal("50.00"), Decimal("10"))]

    def test_market_order_does_not_appear_on_book(self):
        ex = _make_exchange()
        ex.open()
        pid = _register(ex)
        _submit_market(ex, pid, "XYZ", Side.BUY, Decimal("10"))
        depth = ex.get_depth("XYZ", 5)
        assert depth["bids"] == []

    def test_accepted_order_retrievable_via_get_order(self):
        ex = _make_exchange()
        ex.open()
        pid = _register(ex)
        resp = _submit_limit(ex, pid, "XYZ", Side.BUY, Decimal("50"), Decimal("10"))
        order = ex.get_order(resp.order_id)
        assert order is not None
        assert order.order_id == resp.order_id
        assert order.participant_id == pid
        assert order.instrument == "XYZ"
        assert order.side == Side.BUY
        assert order.order_type == OrderType.LIMIT
        assert order.price == Decimal("50")
        assert order.quantity == Decimal("10")
        assert order.remaining_quantity == Decimal("10")
        assert order.status == OrderStatus.ACCEPTED
        assert order.rejection_reason is None

    def test_timestamps_set_from_clock(self):
        config = ExchangeConfig(instruments=["XYZ"])
        clock = Clock(mode=ClockMode.FAST_SIMULATION, offset_us=5000000)
        ex = Exchange(config, clock)
        ex.open()
        pid = ex.handle_registration_request().participant_id
        resp = _submit_limit(ex, pid, "XYZ", Side.BUY, Decimal("50"), Decimal("10"))
        order = ex.get_order(resp.order_id)
        assert order.creation_timestamp == 5000000
        assert order.last_modified_timestamp == 5000000


class TestRejections:
    def test_reject_exchange_closed(self):
        ex = _make_exchange()
        pid = _register(ex)
        resp = _submit_limit(ex, pid, "XYZ", Side.BUY, Decimal("50"), Decimal("10"))
        assert resp.request_status == RequestStatus.REJECTED
        assert resp.rejection_reason == RejectionReason.EXCHANGE_CLOSED

    def test_reject_unregistered_participant(self):
        ex = _make_exchange()
        ex.open()
        resp = _submit_limit(ex, 999, "XYZ", Side.BUY, Decimal("50"), Decimal("10"))
        assert resp.request_status == RequestStatus.REJECTED
        assert resp.rejection_reason == RejectionReason.UNREGISTERED_PARTICIPANT

    def test_reject_unsupported_instrument(self):
        ex = _make_exchange(instruments=["XYZ"])
        ex.open()
        pid = _register(ex)
        resp = _submit_limit(ex, pid, "ABC", Side.BUY, Decimal("50"), Decimal("10"))
        assert resp.request_status == RequestStatus.REJECTED
        assert resp.rejection_reason == RejectionReason.UNSUPPORTED_INSTRUMENT

    def test_reject_non_positive_price(self):
        ex = _make_exchange()
        ex.open()
        pid = _register(ex)
        resp = _submit_limit(ex, pid, "XYZ", Side.BUY, Decimal("0"), Decimal("10"))
        assert resp.request_status == RequestStatus.REJECTED
        assert resp.rejection_reason == RejectionReason.NON_POSITIVE_PRICE

    def test_reject_negative_price(self):
        ex = _make_exchange()
        ex.open()
        pid = _register(ex)
        resp = _submit_limit(ex, pid, "XYZ", Side.BUY, Decimal("-1"), Decimal("10"))
        assert resp.request_status == RequestStatus.REJECTED
        assert resp.rejection_reason == RejectionReason.NON_POSITIVE_PRICE

    def test_reject_none_price_for_limit(self):
        ex = _make_exchange()
        ex.open()
        pid = _register(ex)
        resp = _submit_limit(ex, pid, "XYZ", Side.BUY, None, Decimal("10"))
        assert resp.request_status == RequestStatus.REJECTED
        assert resp.rejection_reason == RejectionReason.NON_POSITIVE_PRICE

    def test_reject_non_positive_quantity(self):
        ex = _make_exchange()
        ex.open()
        pid = _register(ex)
        resp = _submit_limit(ex, pid, "XYZ", Side.BUY, Decimal("50"), Decimal("0"))
        assert resp.request_status == RequestStatus.REJECTED
        assert resp.rejection_reason == RejectionReason.NON_POSITIVE_QUANTITY

    def test_reject_negative_quantity(self):
        ex = _make_exchange()
        ex.open()
        pid = _register(ex)
        resp = _submit_limit(ex, pid, "XYZ", Side.BUY, Decimal("50"), Decimal("-5"))
        assert resp.request_status == RequestStatus.REJECTED
        assert resp.rejection_reason == RejectionReason.NON_POSITIVE_QUANTITY

    def test_rejected_order_not_on_book(self):
        ex = _make_exchange()
        # Exchange is closed, so order is rejected.
        pid = _register(ex)
        _submit_limit(ex, pid, "XYZ", Side.BUY, Decimal("50"), Decimal("10"))
        ex.open()
        depth = ex.get_depth("XYZ", 5)
        assert depth["bids"] == []

    def test_rejected_order_still_gets_order_id(self):
        ex = _make_exchange(starting_order_id=100)
        pid = _register(ex)
        resp = _submit_limit(ex, pid, "XYZ", Side.BUY, Decimal("50"), Decimal("10"))
        assert resp.order_id == 100
        assert resp.request_status == RequestStatus.REJECTED

    def test_unsupported_action_rejected(self):
        """Unknown action values fall through to unsupported rejection."""
        ex = _make_exchange()
        ex.open()
        pid = _register(ex)
        # Construct a request with a fake action that doesn't match any.
        request = OrderMessageRequest(
            action=Action.SUBMIT,
            participant_id=pid,
            instrument="XYZ",
            side=Side.BUY,
            order_type=OrderType.LIMIT,
            price=Decimal("50"),
            quantity=Decimal("10"),
        )
        # Manually override action to test the fallthrough branch.
        request.action = "UNKNOWN"
        resp = ex.handle_order_message(request)
        assert resp.request_status == RequestStatus.REJECTED
        assert resp.rejection_reason == RejectionReason.UNSUPPORTED_ORDER_TYPE


class TestModifyOrder:
    def test_modify_quantity_down_keeps_priority(self):
        ex = _make_exchange()
        ex.open()
        pid = _register(ex)
        r1 = _submit_limit(ex, pid, "XYZ", Side.BUY, Decimal("50"), Decimal("100"))
        _submit_limit(ex, pid, "XYZ", Side.BUY, Decimal("50"), Decimal("100"))
        resp = ex.handle_order_message(OrderMessageRequest(
            action=Action.MODIFY,
            participant_id=pid,
            order_id=r1.order_id,
            quantity=Decimal("80"),
        ))
        assert resp.request_status == RequestStatus.MODIFIED
        # Total depth should be 80 + 100 = 180 at $50.
        depth = ex.get_depth("XYZ", 5)
        assert depth["bids"] == [(Decimal("50"), Decimal("180"))]
        order = ex.get_order(r1.order_id)
        assert order.remaining_quantity == Decimal("80")

    def test_modify_quantity_up_loses_priority(self):
        ex = _make_exchange()
        ex.open()
        pid = _register(ex)
        r1 = _submit_limit(ex, pid, "XYZ", Side.BUY, Decimal("50"), Decimal("100"))
        _submit_limit(ex, pid, "XYZ", Side.BUY, Decimal("50"), Decimal("100"))
        resp = ex.handle_order_message(OrderMessageRequest(
            action=Action.MODIFY,
            participant_id=pid,
            order_id=r1.order_id,
            quantity=Decimal("150"),
        ))
        assert resp.request_status == RequestStatus.MODIFIED_PRIORITY_RESET
        # Total depth should be 150 + 100 = 250 at $50.
        depth = ex.get_depth("XYZ", 5)
        assert depth["bids"] == [(Decimal("50"), Decimal("250"))]

    def test_modify_price_change_loses_priority(self):
        ex = _make_exchange()
        ex.open()
        pid = _register(ex)
        r1 = _submit_limit(ex, pid, "XYZ", Side.BUY, Decimal("50"), Decimal("100"))
        _submit_limit(ex, pid, "XYZ", Side.BUY, Decimal("50"), Decimal("100"))
        resp = ex.handle_order_message(OrderMessageRequest(
            action=Action.MODIFY,
            participant_id=pid,
            order_id=r1.order_id,
            price=Decimal("49"),
            quantity=Decimal("100"),
        ))
        assert resp.request_status == RequestStatus.MODIFIED_PRIORITY_RESET
        order = ex.get_order(r1.order_id)
        assert order.price == Decimal("49")
        # Two price levels: $50 (100) and $49 (100).
        depth = ex.get_depth("XYZ", 5)
        assert depth["bids"] == [
            (Decimal("50"), Decimal("100")),
            (Decimal("49"), Decimal("100")),
        ]

    def test_modify_same_price_keeps_priority(self):
        ex = _make_exchange()
        ex.open()
        pid = _register(ex)
        r1 = _submit_limit(ex, pid, "XYZ", Side.BUY, Decimal("50"), Decimal("100"))
        _submit_limit(ex, pid, "XYZ", Side.BUY, Decimal("50"), Decimal("100"))
        resp = ex.handle_order_message(OrderMessageRequest(
            action=Action.MODIFY,
            participant_id=pid,
            order_id=r1.order_id,
            quantity=Decimal("100"),
        ))
        assert resp.request_status == RequestStatus.MODIFIED

    def test_modify_response_includes_order_fields(self):
        ex = _make_exchange()
        ex.open()
        pid = _register(ex)
        r = _submit_limit(ex, pid, "XYZ", Side.BUY, Decimal("50"), Decimal("100"))
        resp = ex.handle_order_message(OrderMessageRequest(
            action=Action.MODIFY,
            participant_id=pid,
            order_id=r.order_id,
            quantity=Decimal("80"),
        ))
        assert resp.order_status == OrderStatus.ACCEPTED
        assert resp.instrument == "XYZ"
        assert resp.side == Side.BUY
        assert resp.order_type == OrderType.LIMIT
        assert resp.price == Decimal("50")
        assert resp.quantity == Decimal("80")
        assert resp.remaining_quantity == Decimal("80")
        assert resp.filled_quantity == Decimal("0")
        assert resp.creation_timestamp is not None
        assert resp.last_modified_timestamp is not None

    def test_modify_to_filled_equal_to_filled(self):
        """Modify total to exactly the filled amount marks FILLED."""
        ex = _make_exchange()
        ex.open()
        pid = _register(ex)
        r = _submit_limit(ex, pid, "XYZ", Side.BUY, Decimal("50"), Decimal("100"))
        # Simulate partial fill: 60 of 100 filled.
        order = ex.get_order(r.order_id)
        order.status = OrderStatus.PARTIALLY_FILLED
        order.remaining_quantity = Decimal("40")
        resp = ex.handle_order_message(OrderMessageRequest(
            action=Action.MODIFY,
            participant_id=pid,
            order_id=r.order_id,
            quantity=Decimal("60"),
        ))
        assert resp.request_status == RequestStatus.FILLED
        assert resp.filled_quantity == Decimal("60")
        assert resp.remaining_quantity == Decimal("0")
        assert resp.quantity == Decimal("60")
        assert order.status == OrderStatus.FILLED

    def test_modify_to_filled_less_than_filled(self):
        """Modify total to less than filled amount marks FILLED with actual filled qty."""
        ex = _make_exchange()
        ex.open()
        pid = _register(ex)
        r = _submit_limit(ex, pid, "XYZ", Side.BUY, Decimal("50"), Decimal("100"))
        # Simulate partial fill: 80 of 100 filled.
        order = ex.get_order(r.order_id)
        order.status = OrderStatus.PARTIALLY_FILLED
        order.remaining_quantity = Decimal("20")
        resp = ex.handle_order_message(OrderMessageRequest(
            action=Action.MODIFY,
            participant_id=pid,
            order_id=r.order_id,
            quantity=Decimal("50"),
        ))
        assert resp.request_status == RequestStatus.FILLED
        # Filled quantity reflects actual fills (80), not the requested total (50).
        assert resp.filled_quantity == Decimal("80")
        assert resp.remaining_quantity == Decimal("0")
        assert resp.quantity == Decimal("80")
        assert order.status == OrderStatus.FILLED

    def test_modify_updates_timestamp(self):
        config = ExchangeConfig(instruments=["XYZ"])
        clock = Clock(mode=ClockMode.FAST_SIMULATION, offset_us=1000)
        ex = Exchange(config, clock)
        ex.open()
        pid = ex.handle_registration_request().participant_id
        r = _submit_limit(ex, pid, "XYZ", Side.BUY, Decimal("50"), Decimal("100"))
        clock.advance(5000)
        ex.handle_order_message(OrderMessageRequest(
            action=Action.MODIFY,
            participant_id=pid,
            order_id=r.order_id,
            quantity=Decimal("80"),
        ))
        order = ex.get_order(r.order_id)
        assert order.last_modified_timestamp == 6000

    def test_modify_exchange_closed(self):
        ex = _make_exchange()
        ex.open()
        pid = _register(ex)
        r = _submit_limit(ex, pid, "XYZ", Side.BUY, Decimal("50"), Decimal("10"))
        ex.close()
        resp = ex.handle_order_message(OrderMessageRequest(
            action=Action.MODIFY,
            participant_id=pid,
            order_id=r.order_id,
            quantity=Decimal("5"),
        ))
        assert resp.request_status == RequestStatus.REJECTED
        assert resp.rejection_reason == RejectionReason.EXCHANGE_CLOSED

    def test_modify_unregistered_participant(self):
        ex = _make_exchange()
        ex.open()
        pid = _register(ex)
        r = _submit_limit(ex, pid, "XYZ", Side.BUY, Decimal("50"), Decimal("10"))
        resp = ex.handle_order_message(OrderMessageRequest(
            action=Action.MODIFY,
            participant_id=999,
            order_id=r.order_id,
            quantity=Decimal("5"),
        ))
        assert resp.request_status == RequestStatus.REJECTED
        assert resp.rejection_reason == RejectionReason.UNREGISTERED_PARTICIPANT

    def test_modify_unauthorized_participant(self):
        ex = _make_exchange()
        ex.open()
        pid1 = _register(ex)
        pid2 = _register(ex)
        r = _submit_limit(ex, pid1, "XYZ", Side.BUY, Decimal("50"), Decimal("10"))
        resp = ex.handle_order_message(OrderMessageRequest(
            action=Action.MODIFY,
            participant_id=pid2,
            order_id=r.order_id,
            quantity=Decimal("5"),
        ))
        assert resp.request_status == RequestStatus.REJECTED
        assert resp.rejection_reason == RejectionReason.UNAUTHORIZED_PARTICIPANT

    def test_modify_nonexistent_returns_not_found(self):
        ex = _make_exchange()
        ex.open()
        pid = _register(ex)
        resp = ex.handle_order_message(OrderMessageRequest(
            action=Action.MODIFY,
            participant_id=pid,
            order_id=999,
            quantity=Decimal("50"),
        ))
        assert resp.request_status == RequestStatus.ORDER_NOT_FOUND

    def test_modify_inactive_order(self):
        ex = _make_exchange()
        ex.open()
        pid = _register(ex)
        r = _submit_limit(ex, pid, "XYZ", Side.BUY, Decimal("50"), Decimal("10"))
        # Cancel first, then try to modify.
        ex.handle_order_message(OrderMessageRequest(
            action=Action.CANCEL,
            participant_id=pid,
            order_id=r.order_id,
        ))
        resp = ex.handle_order_message(OrderMessageRequest(
            action=Action.MODIFY,
            participant_id=pid,
            order_id=r.order_id,
            quantity=Decimal("20"),
        ))
        assert resp.request_status == RequestStatus.ORDER_INACTIVE
        # Response includes order fields so client can inspect why.
        assert resp.order_status == OrderStatus.CANCELLED
        assert resp.instrument == "XYZ"


class TestCancelOrder:
    def test_cancel_active_order(self):
        ex = _make_exchange()
        ex.open()
        pid = _register(ex)
        r = _submit_limit(ex, pid, "XYZ", Side.BUY, Decimal("50"), Decimal("10"))
        resp = ex.handle_order_message(OrderMessageRequest(
            action=Action.CANCEL,
            participant_id=pid,
            order_id=r.order_id,
        ))
        assert resp.request_status == RequestStatus.CANCELLED
        assert resp.order_status == OrderStatus.CANCELLED
        assert resp.instrument == "XYZ"
        assert resp.filled_quantity == Decimal("0")
        order = ex.get_order(r.order_id)
        assert order.status == OrderStatus.CANCELLED

    def test_cancel_removes_from_depth(self):
        ex = _make_exchange()
        ex.open()
        pid = _register(ex)
        r = _submit_limit(ex, pid, "XYZ", Side.BUY, Decimal("50"), Decimal("10"))
        ex.handle_order_message(OrderMessageRequest(
            action=Action.CANCEL,
            participant_id=pid,
            order_id=r.order_id,
        ))
        depth = ex.get_depth("XYZ", 5)
        assert depth["bids"] == []

    def test_cancel_updates_timestamp(self):
        config = ExchangeConfig(instruments=["XYZ"])
        clock = Clock(mode=ClockMode.FAST_SIMULATION, offset_us=1000)
        ex = Exchange(config, clock)
        ex.open()
        pid = ex.handle_registration_request().participant_id
        r = _submit_limit(ex, pid, "XYZ", Side.BUY, Decimal("50"), Decimal("10"))
        clock.advance(5000)
        resp = ex.handle_order_message(OrderMessageRequest(
            action=Action.CANCEL,
            participant_id=pid,
            order_id=r.order_id,
        ))
        assert resp.last_modified_timestamp == 6000
        order = ex.get_order(r.order_id)
        assert order.last_modified_timestamp == 6000

    def test_cancel_exchange_closed(self):
        ex = _make_exchange()
        ex.open()
        pid = _register(ex)
        r = _submit_limit(ex, pid, "XYZ", Side.BUY, Decimal("50"), Decimal("10"))
        ex.close()
        resp = ex.handle_order_message(OrderMessageRequest(
            action=Action.CANCEL,
            participant_id=pid,
            order_id=r.order_id,
        ))
        assert resp.request_status == RequestStatus.REJECTED
        assert resp.rejection_reason == RejectionReason.EXCHANGE_CLOSED

    def test_cancel_unregistered_participant(self):
        ex = _make_exchange()
        ex.open()
        pid = _register(ex)
        r = _submit_limit(ex, pid, "XYZ", Side.BUY, Decimal("50"), Decimal("10"))
        resp = ex.handle_order_message(OrderMessageRequest(
            action=Action.CANCEL,
            participant_id=999,
            order_id=r.order_id,
        ))
        assert resp.request_status == RequestStatus.REJECTED
        assert resp.rejection_reason == RejectionReason.UNREGISTERED_PARTICIPANT

    def test_cancel_unauthorized_participant(self):
        ex = _make_exchange()
        ex.open()
        pid1 = _register(ex)
        pid2 = _register(ex)
        r = _submit_limit(ex, pid1, "XYZ", Side.BUY, Decimal("50"), Decimal("10"))
        resp = ex.handle_order_message(OrderMessageRequest(
            action=Action.CANCEL,
            participant_id=pid2,
            order_id=r.order_id,
        ))
        assert resp.request_status == RequestStatus.REJECTED
        assert resp.rejection_reason == RejectionReason.UNAUTHORIZED_PARTICIPANT

    def test_cancel_nonexistent_returns_not_found(self):
        ex = _make_exchange()
        ex.open()
        pid = _register(ex)
        resp = ex.handle_order_message(OrderMessageRequest(
            action=Action.CANCEL,
            participant_id=pid,
            order_id=999,
        ))
        assert resp.request_status == RequestStatus.ORDER_NOT_FOUND

    def test_cancel_already_cancelled_returns_inactive(self):
        ex = _make_exchange()
        ex.open()
        pid = _register(ex)
        r = _submit_limit(ex, pid, "XYZ", Side.BUY, Decimal("50"), Decimal("10"))
        ex.handle_order_message(OrderMessageRequest(
            action=Action.CANCEL,
            participant_id=pid,
            order_id=r.order_id,
        ))
        resp = ex.handle_order_message(OrderMessageRequest(
            action=Action.CANCEL,
            participant_id=pid,
            order_id=r.order_id,
        ))
        assert resp.request_status == RequestStatus.ORDER_INACTIVE
        assert resp.order_status == OrderStatus.CANCELLED


class TestQueryMethods:
    def test_get_transactions_empty(self):
        ex = _make_exchange()
        assert ex.get_transactions() == []

    def test_get_depth_unknown_instrument(self):
        ex = _make_exchange(instruments=["XYZ"])
        assert ex.get_depth("ABC", 5) is None

    def test_get_depth_multiple_instruments(self):
        ex = _make_exchange(instruments=["XYZ", "ABC"])
        ex.open()
        pid = _register(ex)
        _submit_limit(ex, pid, "XYZ", Side.BUY, Decimal("50"), Decimal("10"))
        _submit_limit(ex, pid, "ABC", Side.SELL, Decimal("25"), Decimal("5"))
        xyz_depth = ex.get_depth("XYZ", 5)
        abc_depth = ex.get_depth("ABC", 5)
        assert xyz_depth["bids"] == [(Decimal("50"), Decimal("10"))]
        assert abc_depth["asks"] == [(Decimal("25"), Decimal("5"))]

    def test_get_order(self):
        ex = _make_exchange()
        ex.open()
        pid = _register(ex)
        resp = _submit_limit(ex, pid, "XYZ", Side.BUY, Decimal("50"), Decimal("10"))
        order = ex.get_order(resp.order_id)
        assert order is not None
        assert order.order_id == resp.order_id

    def test_get_order_with_instrument(self):
        ex = _make_exchange(instruments=["XYZ", "ABC"])
        ex.open()
        pid = _register(ex)
        resp = _submit_limit(ex, pid, "XYZ", Side.BUY, Decimal("50"), Decimal("10"))
        assert ex.get_order(resp.order_id, instrument="XYZ") is not None
        assert ex.get_order(resp.order_id, instrument="ABC") is None

    def test_get_order_not_found(self):
        ex = _make_exchange()
        assert ex.get_order(999) is None


class TestMultipleInstruments:
    def test_orders_go_to_correct_book(self):
        ex = _make_exchange(instruments=["XYZ", "ABC"])
        ex.open()
        pid = _register(ex)
        _submit_limit(ex, pid, "XYZ", Side.BUY, Decimal("50"), Decimal("10"))
        _submit_limit(ex, pid, "ABC", Side.BUY, Decimal("25"), Decimal("20"))
        xyz = ex.get_depth("XYZ", 5)
        abc = ex.get_depth("ABC", 5)
        assert len(xyz["bids"]) == 1
        assert len(abc["bids"]) == 1
        assert xyz["bids"][0] == (Decimal("50"), Decimal("10"))
        assert abc["bids"][0] == (Decimal("25"), Decimal("20"))
