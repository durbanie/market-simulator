"""Tests for FeedHandler: market data distribution from exchange to clients."""

from decimal import Decimal

from market_simulator.core.clock import Clock, ClockMode
from market_simulator.core.exchange_enums import (
    Action,
    APILevel,
    OrderType,
    RejectionReason,
    RequestStatus,
    Side,
)
from market_simulator.core.messages import OrderMessageRequest, RegistrationRequest
from market_simulator.exchange.exchange import Exchange, ExchangeConfig
from market_simulator.exchange.feed_handler import FeedHandler


def _make_exchange_and_handler() -> tuple[Exchange, FeedHandler]:
    """Create an exchange and feed handler wired together."""
    config = ExchangeConfig(instruments=["XYZ"])
    clock = Clock(mode=ClockMode.FAST_SIMULATION)
    exchange = Exchange(config, clock)
    handler = FeedHandler(exchange, starting_transaction_id=config.starting_transaction_id)
    return exchange, handler


def _register(ex: Exchange, api_level: APILevel = APILevel.L3) -> int:
    return ex.handle_registration_request(
        RegistrationRequest(api_level=api_level),
    ).participant_id


def _submit_limit(ex, pid, instrument, side, price, quantity):
    return ex.handle_order_message(OrderMessageRequest(
        action=Action.SUBMIT, participant_id=pid, instrument=instrument,
        side=side, order_type=OrderType.LIMIT, price=price, quantity=quantity,
    ))


def _submit_market(ex, pid, instrument, side, quantity):
    return ex.handle_order_message(OrderMessageRequest(
        action=Action.SUBMIT, participant_id=pid, instrument=instrument,
        side=side, order_type=OrderType.MARKET, quantity=quantity,
    ))


class _MockClient:
    """Minimal mock with _on_transaction for testing push delivery."""

    def __init__(self):
        self.received = []

    def _on_transaction(self, transaction):
        self.received.append(transaction)


class TestFeedHandlerReceivesTransactions:

    def test_internal_feed_populated_after_match(self):
        ex, handler = _make_exchange_and_handler()
        ex.open()
        maker = _register(ex)
        taker = _register(ex)
        _submit_limit(ex, maker, "XYZ", Side.SELL, Decimal("50"), Decimal("10"))
        _submit_market(ex, taker, "XYZ", Side.BUY, Decimal("10"))
        feed = handler.transaction_feed
        assert feed.last_transaction_id == 1
        txns = feed.read_from(0)
        assert len(txns) == 1
        assert txns[0].price == Decimal("50")

    def test_multiple_fills_all_recorded(self):
        ex, handler = _make_exchange_and_handler()
        ex.open()
        maker1 = _register(ex)
        maker2 = _register(ex)
        taker = _register(ex)
        _submit_limit(ex, maker1, "XYZ", Side.SELL, Decimal("50"), Decimal("5"))
        _submit_limit(ex, maker2, "XYZ", Side.SELL, Decimal("51"), Decimal("5"))
        _submit_market(ex, taker, "XYZ", Side.BUY, Decimal("10"))
        assert handler.transaction_feed.last_transaction_id == 2


class TestFeedHandlerSubscription:

    def test_l3_can_subscribe(self):
        ex, handler = _make_exchange_and_handler()
        pid = _register(ex, APILevel.L3)
        handler.register_participant(pid, APILevel.L3)
        client = _MockClient()
        resp = handler.subscribe(pid, client)
        assert resp.request_status == RequestStatus.ACCEPTED

    def test_pushes_to_subscribed_client(self):
        ex, handler = _make_exchange_and_handler()
        ex.open()
        maker = _register(ex)
        taker = _register(ex)
        handler.register_participant(taker, APILevel.L3)
        client = _MockClient()
        handler.subscribe(taker, client)
        _submit_limit(ex, maker, "XYZ", Side.SELL, Decimal("50"), Decimal("10"))
        _submit_market(ex, taker, "XYZ", Side.BUY, Decimal("10"))
        assert len(client.received) == 1
        assert client.received[0].price == Decimal("50")

    def test_multiple_subscribers_all_receive(self):
        ex, handler = _make_exchange_and_handler()
        ex.open()
        maker = _register(ex)
        sub1 = _register(ex, APILevel.L3)
        sub2 = _register(ex, APILevel.L3)
        handler.register_participant(sub1, APILevel.L3)
        handler.register_participant(sub2, APILevel.L3)
        client1 = _MockClient()
        client2 = _MockClient()
        handler.subscribe(sub1, client1)
        handler.subscribe(sub2, client2)
        _submit_limit(ex, maker, "XYZ", Side.SELL, Decimal("50"), Decimal("10"))
        _submit_market(ex, sub1, "XYZ", Side.BUY, Decimal("10"))
        assert len(client1.received) == 1
        assert len(client2.received) == 1

    def test_rejects_non_l3(self):
        ex, handler = _make_exchange_and_handler()
        pid = _register(ex, APILevel.L1)
        handler.register_participant(pid, APILevel.L1)
        client = _MockClient()
        resp = handler.subscribe(pid, client)
        assert resp.request_status == RequestStatus.REJECTED
        assert resp.rejection_reason == RejectionReason.INSUFFICIENT_API_LEVEL

    def test_rejects_l2(self):
        ex, handler = _make_exchange_and_handler()
        pid = _register(ex, APILevel.L2)
        handler.register_participant(pid, APILevel.L2)
        client = _MockClient()
        resp = handler.subscribe(pid, client)
        assert resp.request_status == RequestStatus.REJECTED
        assert resp.rejection_reason == RejectionReason.INSUFFICIENT_API_LEVEL

    def test_rejects_unregistered(self):
        _, handler = _make_exchange_and_handler()
        client = _MockClient()
        resp = handler.subscribe(999, client)
        assert resp.request_status == RequestStatus.REJECTED
        assert resp.rejection_reason == RejectionReason.UNREGISTERED_PARTICIPANT

    def test_unsubscribed_client_does_not_receive(self):
        ex, handler = _make_exchange_and_handler()
        ex.open()
        maker = _register(ex)
        taker = _register(ex)
        handler.register_participant(taker, APILevel.L3)
        client = _MockClient()
        # Register but do NOT subscribe.
        _submit_limit(ex, maker, "XYZ", Side.SELL, Decimal("50"), Decimal("10"))
        _submit_market(ex, taker, "XYZ", Side.BUY, Decimal("10"))
        assert len(client.received) == 0
