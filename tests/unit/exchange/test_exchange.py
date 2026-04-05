"""Tests for Exchange: order processing, validation, and state management."""

from decimal import Decimal

from market_simulator.core.clock import Clock, ClockMode
from market_simulator.core.exchange_enums import (
    Action,
    APILevel,
    ExchangeState,
    OrderStatus,
    OrderType,
    RejectionReason,
    RequestStatus,
    Side,
)
from market_simulator.core.messages import (
    DepthRequest,
    ExchangeStatusRequest,
    NBBORequest,
    OrderMessageRequest,
    OrderMessageResponse,
    OrderQueryRequest,
    RegistrationRequest,
    TransactionsRequest,
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


def _register(ex: Exchange, api_level: APILevel = APILevel.L3) -> int:
    """Register a participant and return their ID."""
    return ex.handle_registration_request(
        RegistrationRequest(api_level=api_level),
    ).participant_id


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


def _get_depth(ex: Exchange, pid: int, instrument: str, levels: int):
    """Query depth via the handle method and return the levels dict (or None)."""
    return ex.handle_depth_request(
        DepthRequest(participant_id=pid, instrument=instrument, levels=levels),
    ).levels


def _get_order(ex: Exchange, order_id: int, instrument: str | None = None):
    """Look up an order's internal state for test assertions.

    Uses _find_order to return the raw Order object so tests can check
    fields like ``status`` and ``participant_id`` directly, and can
    mutate order state to simulate partial fills.
    """
    return ex._find_order(order_id, instrument)


def _get_transactions(ex: Exchange, pid: int):
    """Query transactions via the handle method and return the list."""
    return ex.handle_transactions_request(
        TransactionsRequest(participant_id=pid),
    ).transactions


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
        req = RegistrationRequest(api_level=APILevel.L1)
        r1 = ex.handle_registration_request(req)
        r2 = ex.handle_registration_request(req)
        r3 = ex.handle_registration_request(req)
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
        depth = _get_depth(ex, pid, "XYZ", 5)
        assert depth["bids"] == [(Decimal("50.00"), Decimal("10"))]

    def test_market_order_does_not_appear_on_book(self):
        ex = _make_exchange()
        ex.open()
        pid = _register(ex)
        _submit_market(ex, pid, "XYZ", Side.BUY, Decimal("10"))
        depth = _get_depth(ex, pid, "XYZ", 5)
        assert depth["bids"] == []

    def test_accepted_order_retrievable_via_get_order(self):
        ex = _make_exchange()
        ex.open()
        pid = _register(ex)
        resp = _submit_limit(ex, pid, "XYZ", Side.BUY, Decimal("50"), Decimal("10"))
        order = _get_order(ex,resp.order_id)
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
        pid = _register(ex)
        resp = _submit_limit(ex, pid, "XYZ", Side.BUY, Decimal("50"), Decimal("10"))
        order = _get_order(ex,resp.order_id)
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
        depth = _get_depth(ex, pid, "XYZ", 5)
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
        depth = _get_depth(ex, pid, "XYZ", 5)
        assert depth["bids"] == [(Decimal("50"), Decimal("180"))]
        order = _get_order(ex,r1.order_id)
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
        depth = _get_depth(ex, pid, "XYZ", 5)
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
        order = _get_order(ex,r1.order_id)
        assert order.price == Decimal("49")
        # Two price levels: $50 (100) and $49 (100).
        depth = _get_depth(ex, pid, "XYZ", 5)
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
        order = _get_order(ex,r.order_id)
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
        order = _get_order(ex,r.order_id)
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
        pid = _register(ex)
        r = _submit_limit(ex, pid, "XYZ", Side.BUY, Decimal("50"), Decimal("100"))
        clock.advance(5000)
        ex.handle_order_message(OrderMessageRequest(
            action=Action.MODIFY,
            participant_id=pid,
            order_id=r.order_id,
            quantity=Decimal("80"),
        ))
        order = _get_order(ex,r.order_id)
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
        order = _get_order(ex,r.order_id)
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
        depth = _get_depth(ex, pid, "XYZ", 5)
        assert depth["bids"] == []

    def test_cancel_updates_timestamp(self):
        config = ExchangeConfig(instruments=["XYZ"])
        clock = Clock(mode=ClockMode.FAST_SIMULATION, offset_us=1000)
        ex = Exchange(config, clock)
        ex.open()
        pid = _register(ex)
        r = _submit_limit(ex, pid, "XYZ", Side.BUY, Decimal("50"), Decimal("10"))
        clock.advance(5000)
        resp = ex.handle_order_message(OrderMessageRequest(
            action=Action.CANCEL,
            participant_id=pid,
            order_id=r.order_id,
        ))
        assert resp.last_modified_timestamp == 6000
        order = _get_order(ex,r.order_id)
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


class TestRequestHandlers:
    def test_handle_exchange_status_request(self):
        ex = _make_exchange()
        pid = _register(ex)
        closed = ex.handle_exchange_status_request(
            ExchangeStatusRequest(participant_id=pid),
        )
        assert closed.request_status == RequestStatus.ACCEPTED
        assert closed.is_open is False
        ex.open()
        opened = ex.handle_exchange_status_request(
            ExchangeStatusRequest(participant_id=pid),
        )
        assert opened.request_status == RequestStatus.ACCEPTED
        assert opened.is_open is True

    def test_handle_transactions_request_empty(self):
        ex = _make_exchange()
        pid = _register(ex)
        resp = ex.handle_transactions_request(
            TransactionsRequest(participant_id=pid),
        )
        assert resp.request_status == RequestStatus.ACCEPTED
        assert resp.transactions == []

    def test_handle_depth_request_unknown_instrument(self):
        ex = _make_exchange(instruments=["XYZ"])
        pid = _register(ex)
        resp = ex.handle_depth_request(
            DepthRequest(participant_id=pid, instrument="ABC", levels=5),
        )
        assert resp.request_status == RequestStatus.ACCEPTED
        assert resp.levels is None

    def test_handle_depth_request_multiple_instruments(self):
        ex = _make_exchange(instruments=["XYZ", "ABC"])
        ex.open()
        pid = _register(ex)
        _submit_limit(ex, pid, "XYZ", Side.BUY, Decimal("50"), Decimal("10"))
        _submit_limit(ex, pid, "ABC", Side.SELL, Decimal("25"), Decimal("5"))
        xyz = ex.handle_depth_request(
            DepthRequest(participant_id=pid, instrument="XYZ", levels=5),
        )
        abc = ex.handle_depth_request(
            DepthRequest(participant_id=pid, instrument="ABC", levels=5),
        )
        assert xyz.levels["bids"] == [(Decimal("50"), Decimal("10"))]
        assert abc.levels["asks"] == [(Decimal("25"), Decimal("5"))]

    def test_handle_order_query_request_found(self):
        ex = _make_exchange()
        ex.open()
        pid = _register(ex)
        submit = _submit_limit(ex, pid, "XYZ", Side.BUY, Decimal("50"), Decimal("10"))
        resp = ex.handle_order_query_request(
            OrderQueryRequest(
                participant_id=pid, order_id=submit.order_id,
            ),
        )
        assert resp.found is True
        assert resp.order_id == submit.order_id
        assert resp.price == Decimal("50")
        assert resp.quantity == Decimal("10")

    def test_handle_order_query_request_with_instrument(self):
        ex = _make_exchange(instruments=["XYZ", "ABC"])
        ex.open()
        pid = _register(ex)
        submit = _submit_limit(ex, pid, "XYZ", Side.BUY, Decimal("50"), Decimal("10"))
        found = ex.handle_order_query_request(
            OrderQueryRequest(
                participant_id=pid, order_id=submit.order_id,
                instrument="XYZ",
            ),
        )
        not_found = ex.handle_order_query_request(
            OrderQueryRequest(
                participant_id=pid, order_id=submit.order_id,
                instrument="ABC",
            ),
        )
        assert found.found is True
        assert not_found.found is False

    def test_handle_order_query_request_not_found(self):
        ex = _make_exchange()
        pid = _register(ex)
        resp = ex.handle_order_query_request(
            OrderQueryRequest(participant_id=pid, order_id=999),
        )
        assert resp.request_status == RequestStatus.ACCEPTED
        assert resp.found is False
        assert resp.order_id == 999

    def test_reject_exchange_status_unregistered(self):
        ex = _make_exchange()
        resp = ex.handle_exchange_status_request(
            ExchangeStatusRequest(participant_id=999),
        )
        assert resp.request_status == RequestStatus.REJECTED
        assert resp.rejection_reason == RejectionReason.UNREGISTERED_PARTICIPANT
        assert resp.is_open is None

    def test_reject_depth_unregistered(self):
        ex = _make_exchange()
        resp = ex.handle_depth_request(
            DepthRequest(participant_id=999, instrument="XYZ", levels=5),
        )
        assert resp.request_status == RequestStatus.REJECTED
        assert resp.rejection_reason == RejectionReason.UNREGISTERED_PARTICIPANT
        assert resp.levels is None

    def test_reject_order_query_unregistered(self):
        ex = _make_exchange()
        resp = ex.handle_order_query_request(
            OrderQueryRequest(participant_id=999, order_id=1),
        )
        assert resp.request_status == RequestStatus.REJECTED
        assert resp.rejection_reason == RejectionReason.UNREGISTERED_PARTICIPANT
        assert resp.found is False

    def test_reject_transactions_unregistered(self):
        ex = _make_exchange()
        resp = ex.handle_transactions_request(
            TransactionsRequest(participant_id=999),
        )
        assert resp.request_status == RequestStatus.REJECTED
        assert resp.rejection_reason == RejectionReason.UNREGISTERED_PARTICIPANT
        assert resp.transactions is None


class TestMultipleInstruments:
    def test_orders_go_to_correct_book(self):
        ex = _make_exchange(instruments=["XYZ", "ABC"])
        ex.open()
        pid = _register(ex)
        _submit_limit(ex, pid, "XYZ", Side.BUY, Decimal("50"), Decimal("10"))
        _submit_limit(ex, pid, "ABC", Side.BUY, Decimal("25"), Decimal("20"))
        xyz = _get_depth(ex, pid, "XYZ", 5)
        abc = _get_depth(ex, pid, "ABC", 5)
        assert len(xyz["bids"]) == 1
        assert len(abc["bids"]) == 1
        assert xyz["bids"][0] == (Decimal("50"), Decimal("10"))
        assert abc["bids"][0] == (Decimal("25"), Decimal("20"))


class TestMatching:
    """Tests for the order matching engine."""

    # -- Market order matching ------------------------------------------------

    def test_market_buy_fills_resting_ask(self):
        ex = _make_exchange()
        ex.open()
        maker = _register(ex)
        taker = _register(ex)
        _submit_limit(ex, maker, "XYZ", Side.SELL, Decimal("50.00"), Decimal("10"))
        resp = _submit_market(ex, taker, "XYZ", Side.BUY, Decimal("10"))
        assert resp.request_status == RequestStatus.FILLED
        assert resp.order_status == OrderStatus.FILLED
        assert resp.remaining_quantity == Decimal("0")
        assert resp.filled_quantity == Decimal("10")
        txns = _get_transactions(ex, maker)
        assert len(txns) == 1
        assert txns[0].price == Decimal("50.00")
        assert txns[0].quantity == Decimal("10")

    def test_market_sell_fills_resting_bid(self):
        ex = _make_exchange()
        ex.open()
        maker = _register(ex)
        taker = _register(ex)
        _submit_limit(ex, maker, "XYZ", Side.BUY, Decimal("50.00"), Decimal("10"))
        resp = _submit_market(ex, taker, "XYZ", Side.SELL, Decimal("10"))
        assert resp.request_status == RequestStatus.FILLED
        assert resp.order_status == OrderStatus.FILLED
        assert resp.filled_quantity == Decimal("10")
        txns = _get_transactions(ex, maker)
        assert len(txns) == 1
        assert txns[0].price == Decimal("50.00")

    def test_market_buy_fills_at_resting_price(self):
        ex = _make_exchange()
        ex.open()
        maker = _register(ex)
        taker = _register(ex)
        _submit_limit(
            ex, maker, "XYZ", Side.SELL, Decimal("50.05"), Decimal("10"),
        )
        resp = _submit_market(ex, taker, "XYZ", Side.BUY, Decimal("10"))
        assert resp.request_status == RequestStatus.FILLED
        txns = _get_transactions(ex, maker)
        assert txns[0].price == Decimal("50.05")

    def test_market_order_fills_multiple_levels(self):
        ex = _make_exchange()
        ex.open()
        maker = _register(ex)
        taker = _register(ex)
        _submit_limit(
            ex, maker, "XYZ", Side.SELL, Decimal("50.00"), Decimal("5"),
        )
        _submit_limit(
            ex, maker, "XYZ", Side.SELL, Decimal("50.10"), Decimal("5"),
        )
        resp = _submit_market(ex, taker, "XYZ", Side.BUY, Decimal("8"))
        assert resp.request_status == RequestStatus.FILLED
        assert resp.filled_quantity == Decimal("8")
        txns = _get_transactions(ex, maker)
        assert len(txns) == 2
        # First fill at best price.
        assert txns[0].price == Decimal("50.00")
        assert txns[0].quantity == Decimal("5")
        # Second fill at next level.
        assert txns[1].price == Decimal("50.10")
        assert txns[1].quantity == Decimal("3")
        # Resting order at 50.10 partially filled.
        resting = _get_order(ex,2, "XYZ")
        assert resting.remaining_quantity == Decimal("2")
        assert resting.status == OrderStatus.PARTIALLY_FILLED

    def test_market_order_partial_fill_rests_remainder(self):
        ex = _make_exchange()
        ex.open()
        maker = _register(ex)
        taker = _register(ex)
        _submit_limit(
            ex, maker, "XYZ", Side.SELL, Decimal("50.00"), Decimal("5"),
        )
        resp = _submit_market(ex, taker, "XYZ", Side.BUY, Decimal("10"))
        assert resp.request_status == RequestStatus.ACCEPTED
        assert resp.order_status == OrderStatus.PARTIALLY_FILLED
        assert resp.filled_quantity == Decimal("5")
        assert resp.remaining_quantity == Decimal("5")
        # Remainder rests on bid side at last fill price.
        depth = _get_depth(ex, maker, "XYZ", 5)
        assert depth["bids"] == [(Decimal("50.00"), Decimal("5"))]
        assert depth["asks"] == []
        # One transaction for the filled portion.
        txns = _get_transactions(ex, maker)
        assert len(txns) == 1
        assert txns[0].quantity == Decimal("5")

    def test_market_order_partial_fill_rests_at_last_fill_price(self):
        ex = _make_exchange()
        ex.open()
        maker = _register(ex)
        taker = _register(ex)
        _submit_limit(
            ex, maker, "XYZ", Side.SELL, Decimal("50.00"), Decimal("3"),
        )
        _submit_limit(
            ex, maker, "XYZ", Side.SELL, Decimal("50.10"), Decimal("3"),
        )
        # Buy 10: fills 3@50.00, 3@50.10, remainder 4 rests at 50.10.
        resp = _submit_market(ex, taker, "XYZ", Side.BUY, Decimal("10"))
        assert resp.request_status == RequestStatus.ACCEPTED
        assert resp.filled_quantity == Decimal("6")
        assert resp.remaining_quantity == Decimal("4")
        depth = _get_depth(ex, maker, "XYZ", 5)
        assert depth["bids"] == [(Decimal("50.10"), Decimal("4"))]

    def test_market_order_not_on_book_after_fill(self):
        ex = _make_exchange()
        ex.open()
        maker = _register(ex)
        taker = _register(ex)
        _submit_limit(
            ex, maker, "XYZ", Side.SELL, Decimal("50.00"), Decimal("10"),
        )
        _submit_market(ex, taker, "XYZ", Side.BUY, Decimal("10"))
        depth = _get_depth(ex, maker, "XYZ", 5)
        assert depth["bids"] == []
        assert depth["asks"] == []

    # -- Crossing limit order matching ----------------------------------------

    def test_limit_buy_crosses_resting_ask(self):
        ex = _make_exchange()
        ex.open()
        maker = _register(ex)
        taker = _register(ex)
        _submit_limit(
            ex, maker, "XYZ", Side.SELL, Decimal("50.05"), Decimal("10"),
        )
        resp = _submit_limit(
            ex, taker, "XYZ", Side.BUY, Decimal("50.10"), Decimal("10"),
        )
        assert resp.request_status == RequestStatus.FILLED
        assert resp.order_status == OrderStatus.FILLED
        txns = _get_transactions(ex, maker)
        assert len(txns) == 1
        assert txns[0].price == Decimal("50.05")

    def test_limit_sell_crosses_resting_bid(self):
        ex = _make_exchange()
        ex.open()
        maker = _register(ex)
        taker = _register(ex)
        _submit_limit(
            ex, maker, "XYZ", Side.BUY, Decimal("50.10"), Decimal("10"),
        )
        resp = _submit_limit(
            ex, taker, "XYZ", Side.SELL, Decimal("50.05"), Decimal("10"),
        )
        assert resp.request_status == RequestStatus.FILLED
        txns = _get_transactions(ex, maker)
        assert txns[0].price == Decimal("50.10")

    def test_crossing_limit_partial_fill_rests_remainder(self):
        ex = _make_exchange()
        ex.open()
        maker = _register(ex)
        taker = _register(ex)
        _submit_limit(
            ex, maker, "XYZ", Side.SELL, Decimal("50.05"), Decimal("5"),
        )
        resp = _submit_limit(
            ex, taker, "XYZ", Side.BUY, Decimal("50.10"), Decimal("10"),
        )
        assert resp.request_status == RequestStatus.ACCEPTED
        assert resp.order_status == OrderStatus.PARTIALLY_FILLED
        assert resp.filled_quantity == Decimal("5")
        assert resp.remaining_quantity == Decimal("5")
        # Remainder rests on bid side.
        depth = _get_depth(ex, maker, "XYZ", 5)
        assert depth["bids"] == [(Decimal("50.10"), Decimal("5"))]
        assert depth["asks"] == []

    def test_noncrossing_limit_rests_without_fill(self):
        ex = _make_exchange()
        ex.open()
        pid = _register(ex)
        _submit_limit(
            ex, pid, "XYZ", Side.SELL, Decimal("50.10"), Decimal("10"),
        )
        resp = _submit_limit(
            ex, pid, "XYZ", Side.BUY, Decimal("50.00"), Decimal("10"),
        )
        assert resp.request_status == RequestStatus.ACCEPTED
        assert resp.order_status == OrderStatus.ACCEPTED
        assert _get_transactions(ex, pid) == []
        depth = _get_depth(ex, pid, "XYZ", 5)
        assert len(depth["bids"]) == 1
        assert len(depth["asks"]) == 1

    def test_limit_crosses_multiple_resting_same_level(self):
        ex = _make_exchange()
        ex.open()
        maker = _register(ex)
        taker = _register(ex)
        _submit_limit(
            ex, maker, "XYZ", Side.SELL, Decimal("50.05"), Decimal("3"),
        )
        _submit_limit(
            ex, maker, "XYZ", Side.SELL, Decimal("50.05"), Decimal("3"),
        )
        resp = _submit_limit(
            ex, taker, "XYZ", Side.BUY, Decimal("50.05"), Decimal("5"),
        )
        assert resp.request_status == RequestStatus.FILLED
        assert resp.filled_quantity == Decimal("5")
        txns = _get_transactions(ex, maker)
        assert len(txns) == 2
        # FIFO: first resting fully filled (3), second partially (2).
        assert txns[0].quantity == Decimal("3")
        assert txns[0].maker_order_id == 1
        assert txns[1].quantity == Decimal("2")
        assert txns[1].maker_order_id == 2

    # -- Fee calculation ------------------------------------------------------

    def test_fee_calculation(self):
        ex = _make_exchange()
        ex.open()
        maker = _register(ex)
        taker = _register(ex)
        _submit_limit(
            ex, maker, "XYZ", Side.SELL, Decimal("100.00"), Decimal("10"),
        )
        _submit_market(ex, taker, "XYZ", Side.BUY, Decimal("10"))
        txn = _get_transactions(ex, maker)[0]
        # maker_fee = 100 * 10 * -3 / 10000 = -0.30 (rebate)
        assert txn.maker_fee == Decimal("-0.30")
        # taker_fee = 100 * 10 * 7 / 10000 = 0.70
        assert txn.taker_fee == Decimal("0.70")

    def test_fees_computed_per_fill(self):
        ex = _make_exchange()
        ex.open()
        maker = _register(ex)
        taker = _register(ex)
        _submit_limit(
            ex, maker, "XYZ", Side.SELL, Decimal("50.00"), Decimal("5"),
        )
        _submit_limit(
            ex, maker, "XYZ", Side.SELL, Decimal("60.00"), Decimal("5"),
        )
        _submit_market(ex, taker, "XYZ", Side.BUY, Decimal("10"))
        txns = _get_transactions(ex, maker)
        # First fill: 50 * 5 * 7 / 10000 = 0.175
        assert txns[0].taker_fee == Decimal("0.175")
        # Second fill: 60 * 5 * 7 / 10000 = 0.21
        assert txns[1].taker_fee == Decimal("0.21")

    # -- Transaction fields ---------------------------------------------------

    def test_transaction_fields_complete(self):
        ex = _make_exchange()
        ex.open()
        maker = _register(ex)
        taker = _register(ex)
        _submit_limit(
            ex, maker, "XYZ", Side.SELL, Decimal("50.00"), Decimal("10"),
        )
        _submit_market(ex, taker, "XYZ", Side.BUY, Decimal("10"))
        txn = _get_transactions(ex, maker)[0]
        assert txn.transaction_id == 1
        assert txn.instrument == "XYZ"
        assert txn.price == Decimal("50.00")
        assert txn.quantity == Decimal("10")
        assert txn.maker_order_id == 1
        assert txn.taker_order_id == 2
        assert txn.maker_participant_id == maker
        assert txn.taker_participant_id == taker
        assert isinstance(txn.timestamp, int)

    def test_transaction_ids_increment(self):
        ex = _make_exchange()
        ex.open()
        maker = _register(ex)
        taker = _register(ex)
        _submit_limit(
            ex, maker, "XYZ", Side.SELL, Decimal("50.00"), Decimal("3"),
        )
        _submit_limit(
            ex, maker, "XYZ", Side.SELL, Decimal("50.00"), Decimal("3"),
        )
        _submit_market(ex, taker, "XYZ", Side.BUY, Decimal("6"))
        txns = _get_transactions(ex, maker)
        assert txns[0].transaction_id == 1
        assert txns[1].transaction_id == 2

    # -- Edge cases -----------------------------------------------------------

    def test_self_trade_allowed(self):
        ex = _make_exchange()
        ex.open()
        pid = _register(ex)
        _submit_limit(
            ex, pid, "XYZ", Side.SELL, Decimal("50.00"), Decimal("10"),
        )
        resp = _submit_limit(
            ex, pid, "XYZ", Side.BUY, Decimal("50.00"), Decimal("10"),
        )
        assert resp.request_status == RequestStatus.FILLED
        txns = _get_transactions(ex, pid)
        assert len(txns) == 1
        assert txns[0].maker_participant_id == pid
        assert txns[0].taker_participant_id == pid

    def test_filled_order_removed_from_depth(self):
        ex = _make_exchange()
        ex.open()
        maker = _register(ex)
        taker = _register(ex)
        _submit_limit(
            ex, maker, "XYZ", Side.SELL, Decimal("50.00"), Decimal("10"),
        )
        depth_before = _get_depth(ex, maker, "XYZ", 5)
        assert len(depth_before["asks"]) == 1
        _submit_market(ex, taker, "XYZ", Side.BUY, Decimal("10"))
        depth_after = _get_depth(ex, maker, "XYZ", 5)
        assert depth_after["asks"] == []


class TestNBBO:

    def test_nbbo_with_orders(self):
        ex = _make_exchange()
        ex.open()
        pid = _register(ex)
        _submit_limit(ex, pid, "XYZ", Side.BUY, Decimal("50.00"), Decimal("10"))
        _submit_limit(ex, pid, "XYZ", Side.SELL, Decimal("51.00"), Decimal("5"))
        resp = ex.handle_nbbo_request(
            NBBORequest(participant_id=pid, instrument="XYZ"),
        )
        assert resp.request_status == RequestStatus.ACCEPTED
        assert resp.best_bid == Decimal("50.00")
        assert resp.best_ask == Decimal("51.00")

    def test_nbbo_empty_book(self):
        ex = _make_exchange()
        ex.open()
        pid = _register(ex)
        resp = ex.handle_nbbo_request(
            NBBORequest(participant_id=pid, instrument="XYZ"),
        )
        assert resp.request_status == RequestStatus.ACCEPTED
        assert resp.best_bid is None
        assert resp.best_ask is None

    def test_nbbo_one_side_only(self):
        ex = _make_exchange()
        ex.open()
        pid = _register(ex)
        _submit_limit(ex, pid, "XYZ", Side.BUY, Decimal("50.00"), Decimal("10"))
        resp = ex.handle_nbbo_request(
            NBBORequest(participant_id=pid, instrument="XYZ"),
        )
        assert resp.best_bid == Decimal("50.00")
        assert resp.best_ask is None

    def test_nbbo_unknown_instrument(self):
        ex = _make_exchange()
        pid = _register(ex)
        resp = ex.handle_nbbo_request(
            NBBORequest(participant_id=pid, instrument="UNKNOWN"),
        )
        assert resp.request_status == RequestStatus.ACCEPTED
        assert resp.best_bid is None
        assert resp.best_ask is None

    def test_nbbo_unregistered_participant(self):
        ex = _make_exchange()
        resp = ex.handle_nbbo_request(
            NBBORequest(participant_id=999, instrument="XYZ"),
        )
        assert resp.request_status == RequestStatus.REJECTED
        assert resp.rejection_reason == RejectionReason.UNREGISTERED_PARTICIPANT


class TestAPILevelEnforcement:

    def test_l1_can_submit_orders(self):
        ex = _make_exchange()
        ex.open()
        pid = _register(ex, APILevel.L1)
        resp = _submit_limit(ex, pid, "XYZ", Side.BUY, Decimal("50"), Decimal("10"))
        assert resp.request_status == RequestStatus.ACCEPTED

    def test_l1_can_query_exchange_status(self):
        ex = _make_exchange()
        pid = _register(ex, APILevel.L1)
        resp = ex.handle_exchange_status_request(
            ExchangeStatusRequest(participant_id=pid),
        )
        assert resp.request_status == RequestStatus.ACCEPTED

    def test_l1_can_query_order(self):
        ex = _make_exchange()
        ex.open()
        pid = _register(ex, APILevel.L1)
        _submit_limit(ex, pid, "XYZ", Side.BUY, Decimal("50"), Decimal("10"))
        resp = ex.handle_order_query_request(
            OrderQueryRequest(participant_id=pid, order_id=1),
        )
        assert resp.request_status == RequestStatus.ACCEPTED

    def test_l1_can_query_nbbo(self):
        ex = _make_exchange()
        pid = _register(ex, APILevel.L1)
        resp = ex.handle_nbbo_request(
            NBBORequest(participant_id=pid, instrument="XYZ"),
        )
        assert resp.request_status == RequestStatus.ACCEPTED

    def test_l1_cannot_query_depth(self):
        ex = _make_exchange()
        pid = _register(ex, APILevel.L1)
        resp = ex.handle_depth_request(
            DepthRequest(participant_id=pid, instrument="XYZ", levels=5),
        )
        assert resp.request_status == RequestStatus.REJECTED
        assert resp.rejection_reason == RejectionReason.INSUFFICIENT_API_LEVEL

    def test_l1_cannot_query_transactions(self):
        ex = _make_exchange()
        pid = _register(ex, APILevel.L1)
        resp = ex.handle_transactions_request(
            TransactionsRequest(participant_id=pid),
        )
        assert resp.request_status == RequestStatus.REJECTED
        assert resp.rejection_reason == RejectionReason.INSUFFICIENT_API_LEVEL

    def test_l2_can_query_depth(self):
        ex = _make_exchange()
        ex.open()
        pid = _register(ex, APILevel.L2)
        _submit_limit(ex, pid, "XYZ", Side.BUY, Decimal("50"), Decimal("10"))
        resp = ex.handle_depth_request(
            DepthRequest(participant_id=pid, instrument="XYZ", levels=5),
        )
        assert resp.request_status == RequestStatus.ACCEPTED
        assert len(resp.levels["bids"]) == 1

    def test_l2_cannot_query_transactions(self):
        ex = _make_exchange()
        pid = _register(ex, APILevel.L2)
        resp = ex.handle_transactions_request(
            TransactionsRequest(participant_id=pid),
        )
        assert resp.request_status == RequestStatus.REJECTED
        assert resp.rejection_reason == RejectionReason.INSUFFICIENT_API_LEVEL

    def test_l3_can_query_transactions(self):
        ex = _make_exchange()
        ex.open()
        pid = _register(ex, APILevel.L3)
        resp = ex.handle_transactions_request(
            TransactionsRequest(participant_id=pid),
        )
        assert resp.request_status == RequestStatus.ACCEPTED
        assert resp.transactions == []

    def test_l3_can_query_depth(self):
        ex = _make_exchange()
        pid = _register(ex, APILevel.L3)
        resp = ex.handle_depth_request(
            DepthRequest(participant_id=pid, instrument="XYZ", levels=5),
        )
        assert resp.request_status == RequestStatus.ACCEPTED
