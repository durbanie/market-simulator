"""Tests for LocalDMAClient: in-process puppet DMA client."""

from decimal import Decimal

import pytest

from market_simulator.core.clock import Clock, ClockMode
from market_simulator.core.exchange_enums import (
    Action,
    OrderType,
    RequestStatus,
    Side,
)
from market_simulator.core.messages import OrderMessageRequest
from market_simulator.exchange.client.local_dma_client import LocalDMAClient
from market_simulator.exchange.exchange import Exchange, ExchangeConfig


def _make_client(
    instruments: list[str] | None = None,
) -> tuple[LocalDMAClient, Exchange]:
    """Create a LocalDMAClient and its backing Exchange."""
    config = ExchangeConfig(
        instruments=instruments or ["XYZ"],
    )
    clock = Clock(mode=ClockMode.FAST_SIMULATION)
    exchange = Exchange(config, clock)
    exchange.open()
    return LocalDMAClient(exchange), exchange


# -- Registration -------------------------------------------------------------


class TestRegistration:

    def test_register_assigns_participant_id(self) -> None:
        client, _ = _make_client()
        resp = client.register()

        assert resp.participant_id >= 1
        assert client.participant_id == resp.participant_id

    def test_register_twice_raises(self) -> None:
        client, _ = _make_client()
        client.register()

        with pytest.raises(RuntimeError, match="already registered"):
            client.register()

    def test_register_multiple_clients(self) -> None:
        config = ExchangeConfig(instruments=["XYZ"])
        clock = Clock(mode=ClockMode.FAST_SIMULATION)
        exchange = Exchange(config, clock)
        exchange.open()

        client_a = LocalDMAClient(exchange)
        client_b = LocalDMAClient(exchange)

        resp_a = client_a.register()
        resp_b = client_b.register()

        assert resp_a.participant_id != resp_b.participant_id


# -- Order submission ---------------------------------------------------------


class TestOrderSubmission:

    def test_submit_order_via_client(self) -> None:
        client, _ = _make_client()
        client.register()

        resp = client.send_order_message(OrderMessageRequest(
            action=Action.SUBMIT,
            participant_id=0,  # overwritten by client
            instrument="XYZ",
            side=Side.BUY,
            order_type=OrderType.LIMIT,
            price=Decimal("100"),
            quantity=Decimal("10"),
        ))

        assert resp.request_status == RequestStatus.ACCEPTED

    def test_submit_without_registration_raises(self) -> None:
        client, _ = _make_client()

        with pytest.raises(RuntimeError, match="must register"):
            client.send_order_message(OrderMessageRequest(
                action=Action.SUBMIT,
                participant_id=0,
                instrument="XYZ",
                side=Side.BUY,
                order_type=OrderType.LIMIT,
                price=Decimal("100"),
                quantity=Decimal("10"),
            ))

    def test_client_sets_participant_id_on_request(self) -> None:
        client, _ = _make_client()
        client.register()
        pid = client.participant_id

        request = OrderMessageRequest(
            action=Action.SUBMIT,
            participant_id=999,  # should be overwritten
            instrument="XYZ",
            side=Side.BUY,
            order_type=OrderType.LIMIT,
            price=Decimal("100"),
            quantity=Decimal("10"),
        )
        client.send_order_message(request)

        assert request.participant_id == pid


# -- Order lifecycle ----------------------------------------------------------


class TestOrderLifecycle:

    def test_submit_and_cancel_via_client(self) -> None:
        client, _ = _make_client()
        client.register()

        submit_resp = client.send_order_message(OrderMessageRequest(
            action=Action.SUBMIT,
            participant_id=0,
            instrument="XYZ",
            side=Side.BUY,
            order_type=OrderType.LIMIT,
            price=Decimal("100"),
            quantity=Decimal("10"),
        ))

        cancel_resp = client.send_order_message(OrderMessageRequest(
            action=Action.CANCEL,
            participant_id=0,
            order_id=submit_resp.order_id,
            instrument="XYZ",
        ))

        assert cancel_resp.request_status == RequestStatus.CANCELLED

    def test_submit_and_modify_via_client(self) -> None:
        client, _ = _make_client()
        client.register()

        submit_resp = client.send_order_message(OrderMessageRequest(
            action=Action.SUBMIT,
            participant_id=0,
            instrument="XYZ",
            side=Side.BUY,
            order_type=OrderType.LIMIT,
            price=Decimal("100"),
            quantity=Decimal("10"),
        ))

        modify_resp = client.send_order_message(OrderMessageRequest(
            action=Action.MODIFY,
            participant_id=0,
            order_id=submit_resp.order_id,
            instrument="XYZ",
            price=Decimal("105"),
            quantity=Decimal("10"),
        ))

        assert modify_resp.request_status == RequestStatus.MODIFIED_PRIORITY_RESET
        assert modify_resp.price == Decimal("105")

    def test_two_clients_fill_against_each_other(self) -> None:
        config = ExchangeConfig(instruments=["XYZ"])
        clock = Clock(mode=ClockMode.FAST_SIMULATION)
        exchange = Exchange(config, clock)
        exchange.open()

        buyer = LocalDMAClient(exchange)
        seller = LocalDMAClient(exchange)
        buyer.register()
        seller.register()

        # Seller posts an ask.
        sell_resp = seller.send_order_message(OrderMessageRequest(
            action=Action.SUBMIT,
            participant_id=0,
            instrument="XYZ",
            side=Side.SELL,
            order_type=OrderType.LIMIT,
            price=Decimal("50"),
            quantity=Decimal("5"),
        ))
        assert sell_resp.request_status == RequestStatus.ACCEPTED

        # Buyer crosses with a market order.
        buy_resp = buyer.send_order_message(OrderMessageRequest(
            action=Action.SUBMIT,
            participant_id=0,
            instrument="XYZ",
            side=Side.BUY,
            order_type=OrderType.MARKET,
            quantity=Decimal("5"),
        ))
        assert buy_resp.request_status == RequestStatus.FILLED
        assert buy_resp.filled_quantity == Decimal("5")


# -- Query methods ------------------------------------------------------------


class TestQueryMethods:

    def test_get_exchange_status_open(self) -> None:
        client, _ = _make_client()
        resp = client.get_exchange_status()
        assert resp.is_open is True

    def test_get_exchange_status_closed(self) -> None:
        config = ExchangeConfig(instruments=["XYZ"])
        clock = Clock(mode=ClockMode.FAST_SIMULATION)
        exchange = Exchange(config, clock)
        # Exchange starts closed by default.
        client = LocalDMAClient(exchange)

        resp = client.get_exchange_status()
        assert resp.is_open is False

    def test_get_depth(self) -> None:
        client, _ = _make_client()
        client.register()

        client.send_order_message(OrderMessageRequest(
            action=Action.SUBMIT,
            participant_id=0,
            instrument="XYZ",
            side=Side.BUY,
            order_type=OrderType.LIMIT,
            price=Decimal("100"),
            quantity=Decimal("10"),
        ))

        resp = client.get_depth("XYZ", 5)

        assert resp.instrument == "XYZ"
        assert resp.levels is not None
        assert len(resp.levels["bids"]) == 1
        price, quantity = resp.levels["bids"][0]
        assert price == Decimal("100")
        assert quantity == Decimal("10")

    def test_get_depth_unknown_instrument(self) -> None:
        client, _ = _make_client()
        resp = client.get_depth("UNKNOWN", 5)
        assert resp.levels is None

    def test_get_order_found(self) -> None:
        client, _ = _make_client()
        client.register()

        submit_resp = client.send_order_message(OrderMessageRequest(
            action=Action.SUBMIT,
            participant_id=0,
            instrument="XYZ",
            side=Side.BUY,
            order_type=OrderType.LIMIT,
            price=Decimal("100"),
            quantity=Decimal("10"),
        ))

        resp = client.get_order(submit_resp.order_id, instrument="XYZ")

        assert resp.found is True
        assert resp.order_id == submit_resp.order_id
        assert resp.price == Decimal("100")
        assert resp.quantity == Decimal("10")
        assert resp.remaining_quantity == Decimal("10")
        assert resp.filled_quantity == Decimal("0")

    def test_get_order_not_found(self) -> None:
        client, _ = _make_client()
        resp = client.get_order(9999)

        assert resp.found is False
        assert resp.order_id == 9999
        assert resp.order_status is None

    def test_get_transactions(self) -> None:
        config = ExchangeConfig(instruments=["XYZ"])
        clock = Clock(mode=ClockMode.FAST_SIMULATION)
        exchange = Exchange(config, clock)
        exchange.open()

        buyer = LocalDMAClient(exchange)
        seller = LocalDMAClient(exchange)
        buyer.register()
        seller.register()

        # Create a fill.
        seller.send_order_message(OrderMessageRequest(
            action=Action.SUBMIT,
            participant_id=0,
            instrument="XYZ",
            side=Side.SELL,
            order_type=OrderType.LIMIT,
            price=Decimal("50"),
            quantity=Decimal("5"),
        ))
        buyer.send_order_message(OrderMessageRequest(
            action=Action.SUBMIT,
            participant_id=0,
            instrument="XYZ",
            side=Side.BUY,
            order_type=OrderType.MARKET,
            quantity=Decimal("5"),
        ))

        resp = buyer.get_transactions()

        assert len(resp.transactions) == 1
        txn = resp.transactions[0]
        assert txn.price == Decimal("50")
        assert txn.quantity == Decimal("5")
