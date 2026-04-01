"""Tests for LocalDMAClient: in-process DMA client."""

from decimal import Decimal

import pytest

from market_simulator.core.clock import Clock, ClockMode
from market_simulator.core.exchange_enums import (
    Action,
    OrderStatus,
    OrderType,
    RejectionReason,
    RequestStatus,
    Side,
)
from market_simulator.core.messages import (
    DepthResponse,
    ExchangeStatusResponse,
    OrderMessageRequest,
    OrderMessageResponse,
    OrderQueryResponse,
    RegistrationResponse,
    TransactionsResponse,
)
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
        received = []
        client.register(received.append)

        assert len(received) == 1
        assert isinstance(received[0], RegistrationResponse)
        assert received[0].participant_id >= 1
        assert client.participant_id == received[0].participant_id

    def test_register_twice_raises(self) -> None:
        client, _ = _make_client()
        client.register(lambda r: None)

        with pytest.raises(RuntimeError, match="already registered"):
            client.register(lambda r: None)

    def test_register_multiple_clients(self) -> None:
        config = ExchangeConfig(instruments=["XYZ"])
        clock = Clock(mode=ClockMode.FAST_SIMULATION)
        exchange = Exchange(config, clock)
        exchange.open()

        client_a = LocalDMAClient(exchange)
        client_b = LocalDMAClient(exchange)

        ids: list[int] = []
        client_a.register(lambda r: ids.append(r.participant_id))
        client_b.register(lambda r: ids.append(r.participant_id))

        assert len(ids) == 2
        assert ids[0] != ids[1]


# -- Order submission ---------------------------------------------------------


class TestOrderSubmission:

    def test_submit_order_via_client(self) -> None:
        client, _ = _make_client()
        client.register(lambda r: None)

        received = []
        client.send_order_message(
            OrderMessageRequest(
                action=Action.SUBMIT,
                participant_id=0,  # overwritten by client
                instrument="XYZ",
                side=Side.BUY,
                order_type=OrderType.LIMIT,
                price=Decimal("100"),
                quantity=Decimal("10"),
            ),
            received.append,
        )

        assert len(received) == 1
        assert received[0].request_status == RequestStatus.ACCEPTED

    def test_submit_without_registration_raises(self) -> None:
        client, _ = _make_client()

        with pytest.raises(RuntimeError, match="must register"):
            client.send_order_message(
                OrderMessageRequest(
                    action=Action.SUBMIT,
                    participant_id=0,
                    instrument="XYZ",
                    side=Side.BUY,
                    order_type=OrderType.LIMIT,
                    price=Decimal("100"),
                    quantity=Decimal("10"),
                ),
                lambda r: None,
            )

    def test_client_sets_participant_id_on_request(self) -> None:
        client, _ = _make_client()
        client.register(lambda r: None)
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
        client.send_order_message(request, lambda r: None)

        assert request.participant_id == pid


# -- Order lifecycle ----------------------------------------------------------


class TestOrderLifecycle:

    def test_submit_and_cancel_via_client(self) -> None:
        client, _ = _make_client()
        client.register(lambda r: None)

        # Submit.
        submit_resp = []
        client.send_order_message(
            OrderMessageRequest(
                action=Action.SUBMIT,
                participant_id=0,
                instrument="XYZ",
                side=Side.BUY,
                order_type=OrderType.LIMIT,
                price=Decimal("100"),
                quantity=Decimal("10"),
            ),
            submit_resp.append,
        )
        order_id = submit_resp[0].order_id

        # Cancel.
        cancel_resp = []
        client.send_order_message(
            OrderMessageRequest(
                action=Action.CANCEL,
                participant_id=0,
                order_id=order_id,
                instrument="XYZ",
            ),
            cancel_resp.append,
        )

        assert cancel_resp[0].request_status == RequestStatus.CANCELLED

    def test_submit_and_modify_via_client(self) -> None:
        client, _ = _make_client()
        client.register(lambda r: None)

        # Submit.
        submit_resp = []
        client.send_order_message(
            OrderMessageRequest(
                action=Action.SUBMIT,
                participant_id=0,
                instrument="XYZ",
                side=Side.BUY,
                order_type=OrderType.LIMIT,
                price=Decimal("100"),
                quantity=Decimal("10"),
            ),
            submit_resp.append,
        )
        order_id = submit_resp[0].order_id

        # Modify price.
        modify_resp = []
        client.send_order_message(
            OrderMessageRequest(
                action=Action.MODIFY,
                participant_id=0,
                order_id=order_id,
                instrument="XYZ",
                price=Decimal("105"),
                quantity=Decimal("10"),
            ),
            modify_resp.append,
        )

        assert modify_resp[0].request_status == RequestStatus.MODIFIED_PRIORITY_RESET
        assert modify_resp[0].price == Decimal("105")

    def test_two_clients_fill_against_each_other(self) -> None:
        config = ExchangeConfig(instruments=["XYZ"])
        clock = Clock(mode=ClockMode.FAST_SIMULATION)
        exchange = Exchange(config, clock)
        exchange.open()

        buyer = LocalDMAClient(exchange)
        seller = LocalDMAClient(exchange)
        buyer.register(lambda r: None)
        seller.register(lambda r: None)

        # Seller posts an ask.
        sell_resp = []
        seller.send_order_message(
            OrderMessageRequest(
                action=Action.SUBMIT,
                participant_id=0,
                instrument="XYZ",
                side=Side.SELL,
                order_type=OrderType.LIMIT,
                price=Decimal("50"),
                quantity=Decimal("5"),
            ),
            sell_resp.append,
        )
        assert sell_resp[0].request_status == RequestStatus.ACCEPTED

        # Buyer crosses with a market order.
        buy_resp = []
        buyer.send_order_message(
            OrderMessageRequest(
                action=Action.SUBMIT,
                participant_id=0,
                instrument="XYZ",
                side=Side.BUY,
                order_type=OrderType.MARKET,
                quantity=Decimal("5"),
            ),
            buy_resp.append,
        )
        assert buy_resp[0].request_status == RequestStatus.FILLED
        assert buy_resp[0].filled_quantity == Decimal("5")


# -- Query methods ------------------------------------------------------------


class TestQueryMethods:

    def test_get_exchange_status_open(self) -> None:
        client, _ = _make_client()
        received = []
        client.get_exchange_status(received.append)

        assert received[0].is_open is True

    def test_get_exchange_status_closed(self) -> None:
        config = ExchangeConfig(instruments=["XYZ"])
        clock = Clock(mode=ClockMode.FAST_SIMULATION)
        exchange = Exchange(config, clock)
        # Exchange starts closed by default.
        client = LocalDMAClient(exchange)

        received = []
        client.get_exchange_status(received.append)

        assert received[0].is_open is False

    def test_get_depth(self) -> None:
        client, _ = _make_client()
        client.register(lambda r: None)

        # Place a bid.
        client.send_order_message(
            OrderMessageRequest(
                action=Action.SUBMIT,
                participant_id=0,
                instrument="XYZ",
                side=Side.BUY,
                order_type=OrderType.LIMIT,
                price=Decimal("100"),
                quantity=Decimal("10"),
            ),
            lambda r: None,
        )

        received = []
        client.get_depth("XYZ", 5, received.append)

        assert received[0].instrument == "XYZ"
        assert received[0].levels is not None
        assert len(received[0].levels["bids"]) == 1
        price, quantity = received[0].levels["bids"][0]
        assert price == Decimal("100")
        assert quantity == Decimal("10")

    def test_get_depth_unknown_instrument(self) -> None:
        client, _ = _make_client()
        received = []
        client.get_depth("UNKNOWN", 5, received.append)

        assert received[0].levels is None

    def test_get_order_found(self) -> None:
        client, _ = _make_client()
        client.register(lambda r: None)

        submit_resp = []
        client.send_order_message(
            OrderMessageRequest(
                action=Action.SUBMIT,
                participant_id=0,
                instrument="XYZ",
                side=Side.BUY,
                order_type=OrderType.LIMIT,
                price=Decimal("100"),
                quantity=Decimal("10"),
            ),
            submit_resp.append,
        )
        order_id = submit_resp[0].order_id

        received = []
        client.get_order(order_id, received.append, instrument="XYZ")

        assert received[0].found is True
        assert received[0].order_id == order_id
        assert received[0].price == Decimal("100")
        assert received[0].quantity == Decimal("10")
        assert received[0].remaining_quantity == Decimal("10")
        assert received[0].filled_quantity == Decimal("0")

    def test_get_order_not_found(self) -> None:
        client, _ = _make_client()
        received = []
        client.get_order(9999, received.append)

        assert received[0].found is False
        assert received[0].order_id == 9999
        assert received[0].order_status is None

    def test_get_transactions(self) -> None:
        config = ExchangeConfig(instruments=["XYZ"])
        clock = Clock(mode=ClockMode.FAST_SIMULATION)
        exchange = Exchange(config, clock)
        exchange.open()

        buyer = LocalDMAClient(exchange)
        seller = LocalDMAClient(exchange)
        buyer.register(lambda r: None)
        seller.register(lambda r: None)

        # Create a fill.
        seller.send_order_message(
            OrderMessageRequest(
                action=Action.SUBMIT,
                participant_id=0,
                instrument="XYZ",
                side=Side.SELL,
                order_type=OrderType.LIMIT,
                price=Decimal("50"),
                quantity=Decimal("5"),
            ),
            lambda r: None,
        )
        buyer.send_order_message(
            OrderMessageRequest(
                action=Action.SUBMIT,
                participant_id=0,
                instrument="XYZ",
                side=Side.BUY,
                order_type=OrderType.MARKET,
                quantity=Decimal("5"),
            ),
            lambda r: None,
        )

        received = []
        buyer.get_transactions(received.append)

        assert len(received[0].transactions) == 1
        txn = received[0].transactions[0]
        assert txn.price == Decimal("50")
        assert txn.quantity == Decimal("5")
