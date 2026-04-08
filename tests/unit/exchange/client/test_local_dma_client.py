"""Tests for LocalDMAClient: in-process puppet DMA client."""

from decimal import Decimal

import pytest

from market_simulator.core.clock import Clock, ClockMode
from market_simulator.core.exchange_enums import (
    APILevel,
    OrderType,
    RequestStatus,
    Side,
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

    def test_submit_order(self) -> None:
        client, _ = _make_client()
        client.register()

        resp = client.submit_order(
            instrument="XYZ",
            side=Side.BUY,
            order_type=OrderType.LIMIT,
            price=Decimal("100"),
            quantity=Decimal("10"),
        )

        assert resp.request_status == RequestStatus.ACCEPTED

    def test_submit_without_registration_raises(self) -> None:
        client, _ = _make_client()

        with pytest.raises(RuntimeError, match="must register"):
            client.submit_order(
                instrument="XYZ",
                side=Side.BUY,
                order_type=OrderType.LIMIT,
                price=Decimal("100"),
                quantity=Decimal("10"),
            )

    def test_submit_sets_participant_id(self) -> None:
        """The base class sets participant_id on the request."""
        client, _ = _make_client()
        client.register()

        resp = client.submit_order(
            instrument="XYZ",
            side=Side.BUY,
            order_type=OrderType.LIMIT,
            price=Decimal("100"),
            quantity=Decimal("10"),
        )

        # Verify the order is owned by this client's participant.
        order_resp = client.query_order(resp.order_id, instrument="XYZ")
        assert order_resp.found is True


# -- Order lifecycle ----------------------------------------------------------


class TestOrderLifecycle:

    def test_submit_and_cancel(self) -> None:
        client, _ = _make_client()
        client.register()

        submit_resp = client.submit_order(
            instrument="XYZ",
            side=Side.BUY,
            order_type=OrderType.LIMIT,
            price=Decimal("100"),
            quantity=Decimal("10"),
        )

        cancel_resp = client.cancel_order(
            order_id=submit_resp.order_id,
            instrument="XYZ",
        )

        assert cancel_resp.request_status == RequestStatus.CANCELLED

    def test_submit_and_modify(self) -> None:
        client, _ = _make_client()
        client.register()

        submit_resp = client.submit_order(
            instrument="XYZ",
            side=Side.BUY,
            order_type=OrderType.LIMIT,
            price=Decimal("100"),
            quantity=Decimal("10"),
        )

        modify_resp = client.modify_order(
            order_id=submit_resp.order_id,
            instrument="XYZ",
            price=Decimal("105"),
            quantity=Decimal("10"),
        )

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

        sell_resp = seller.submit_order(
            instrument="XYZ",
            side=Side.SELL,
            order_type=OrderType.LIMIT,
            price=Decimal("50"),
            quantity=Decimal("5"),
        )
        assert sell_resp.request_status == RequestStatus.ACCEPTED

        buy_resp = buyer.submit_order(
            instrument="XYZ",
            side=Side.BUY,
            order_type=OrderType.MARKET,
            quantity=Decimal("5"),
        )
        assert buy_resp.request_status == RequestStatus.FILLED
        assert buy_resp.filled_quantity == Decimal("5")


# -- Query methods ------------------------------------------------------------


class TestQueryMethods:

    def test_query_exchange_status_open(self) -> None:
        client, _ = _make_client()
        client.register()
        resp = client.query_exchange_status()
        assert resp.is_open is True

    def test_query_exchange_status_closed(self) -> None:
        config = ExchangeConfig(instruments=["XYZ"])
        clock = Clock(mode=ClockMode.FAST_SIMULATION)
        exchange = Exchange(config, clock)
        client = LocalDMAClient(exchange)
        client.register()

        resp = client.query_exchange_status()
        assert resp.is_open is False

    def test_query_depth(self) -> None:
        client, _ = _make_client()
        client.register()

        client.submit_order(
            instrument="XYZ",
            side=Side.BUY,
            order_type=OrderType.LIMIT,
            price=Decimal("100"),
            quantity=Decimal("10"),
        )

        resp = client.query_depth("XYZ", 5)

        assert resp.instrument == "XYZ"
        assert resp.levels is not None
        assert len(resp.levels["bids"]) == 1
        price, quantity = resp.levels["bids"][0]
        assert price == Decimal("100")
        assert quantity == Decimal("10")

    def test_query_depth_unknown_instrument(self) -> None:
        client, _ = _make_client()
        client.register()
        resp = client.query_depth("UNKNOWN", 5)
        assert resp.levels is None

    def test_query_order_found(self) -> None:
        client, _ = _make_client()
        client.register()

        submit_resp = client.submit_order(
            instrument="XYZ",
            side=Side.BUY,
            order_type=OrderType.LIMIT,
            price=Decimal("100"),
            quantity=Decimal("10"),
        )

        resp = client.query_order(submit_resp.order_id, instrument="XYZ")

        assert resp.found is True
        assert resp.order_id == submit_resp.order_id
        assert resp.price == Decimal("100")
        assert resp.quantity == Decimal("10")
        assert resp.remaining_quantity == Decimal("10")
        assert resp.filled_quantity == Decimal("0")

    def test_query_order_not_found(self) -> None:
        client, _ = _make_client()
        client.register()
        resp = client.query_order(9999)

        assert resp.found is False
        assert resp.order_id == 9999
        assert resp.order_status is None

    def test_query_transactions(self) -> None:
        config = ExchangeConfig(instruments=["XYZ"])
        clock = Clock(mode=ClockMode.FAST_SIMULATION)
        exchange = Exchange(config, clock)
        exchange.open()

        buyer = LocalDMAClient(exchange)
        seller = LocalDMAClient(exchange)
        buyer.register()
        seller.register()

        seller.submit_order(
            instrument="XYZ",
            side=Side.SELL,
            order_type=OrderType.LIMIT,
            price=Decimal("50"),
            quantity=Decimal("5"),
        )
        buyer.submit_order(
            instrument="XYZ",
            side=Side.BUY,
            order_type=OrderType.MARKET,
            quantity=Decimal("5"),
        )

        resp = buyer.query_transactions()

        assert len(resp.transactions) == 1
        txn = resp.transactions[0]
        assert txn.price == Decimal("50")
        assert txn.quantity == Decimal("5")


# -- API level enforcement (client-side) --------------------------------------


def _make_leveled_client(
    level: APILevel,
) -> tuple[LocalDMAClient, Exchange]:
    """Create a registered LocalDMAClient at a given API level."""
    config = ExchangeConfig(instruments=["XYZ"])
    clock = Clock(mode=ClockMode.FAST_SIMULATION)
    exchange = Exchange(config, clock)
    exchange.open()
    client = LocalDMAClient(exchange, api_level=level)
    client.register()
    return client, exchange


class TestAPILevelClientEnforcement:

    # -- L1 capabilities -------------------------------------------------------

    def test_l1_can_submit_orders(self) -> None:
        client, _ = _make_leveled_client(APILevel.L1)
        resp = client.submit_order(
            instrument="XYZ", side=Side.BUY,
            order_type=OrderType.LIMIT, price=Decimal("100"), quantity=Decimal("10"),
        )
        assert resp.request_status == RequestStatus.ACCEPTED

    def test_l1_can_query_exchange_status(self) -> None:
        client, _ = _make_leveled_client(APILevel.L1)
        assert client.query_exchange_status().is_open is True

    def test_l1_can_query_order(self) -> None:
        client, _ = _make_leveled_client(APILevel.L1)
        client.submit_order(
            instrument="XYZ", side=Side.BUY,
            order_type=OrderType.LIMIT, price=Decimal("100"), quantity=Decimal("10"),
        )
        resp = client.query_order(1, instrument="XYZ")
        assert resp.found is True

    def test_l1_can_query_nbbo(self) -> None:
        client, _ = _make_leveled_client(APILevel.L1)
        assert client.query_nbbo("XYZ").request_status == RequestStatus.ACCEPTED

    def test_l1_cannot_query_depth(self) -> None:
        client, _ = _make_leveled_client(APILevel.L1)
        with pytest.raises(RuntimeError, match="Depth query requires L2"):
            client.query_depth("XYZ", 5)

    def test_l1_cannot_query_transactions(self) -> None:
        client, _ = _make_leveled_client(APILevel.L1)
        with pytest.raises(RuntimeError, match="Transactions query requires L3"):
            client.query_transactions()

    # -- L2 inherits all L1 capabilities ---------------------------------------

    def test_l2_can_submit_orders(self) -> None:
        client, _ = _make_leveled_client(APILevel.L2)
        resp = client.submit_order(
            instrument="XYZ", side=Side.BUY,
            order_type=OrderType.LIMIT, price=Decimal("100"), quantity=Decimal("10"),
        )
        assert resp.request_status == RequestStatus.ACCEPTED

    def test_l2_can_query_exchange_status(self) -> None:
        client, _ = _make_leveled_client(APILevel.L2)
        assert client.query_exchange_status().is_open is True

    def test_l2_can_query_order(self) -> None:
        client, _ = _make_leveled_client(APILevel.L2)
        client.submit_order(
            instrument="XYZ", side=Side.BUY,
            order_type=OrderType.LIMIT, price=Decimal("100"), quantity=Decimal("10"),
        )
        resp = client.query_order(1, instrument="XYZ")
        assert resp.found is True

    def test_l2_can_query_nbbo(self) -> None:
        client, _ = _make_leveled_client(APILevel.L2)
        assert client.query_nbbo("XYZ").request_status == RequestStatus.ACCEPTED

    def test_l2_can_query_depth(self) -> None:
        client, _ = _make_leveled_client(APILevel.L2)
        assert client.query_depth("XYZ", 5).request_status == RequestStatus.ACCEPTED

    def test_l2_cannot_query_transactions(self) -> None:
        client, _ = _make_leveled_client(APILevel.L2)
        with pytest.raises(RuntimeError, match="Transactions query requires L3"):
            client.query_transactions()

    # -- L3 inherits all L1 and L2 capabilities --------------------------------

    def test_l3_can_submit_orders(self) -> None:
        client, _ = _make_leveled_client(APILevel.L3)
        resp = client.submit_order(
            instrument="XYZ", side=Side.BUY,
            order_type=OrderType.LIMIT, price=Decimal("100"), quantity=Decimal("10"),
        )
        assert resp.request_status == RequestStatus.ACCEPTED

    def test_l3_can_query_exchange_status(self) -> None:
        client, _ = _make_leveled_client(APILevel.L3)
        assert client.query_exchange_status().is_open is True

    def test_l3_can_query_order(self) -> None:
        client, _ = _make_leveled_client(APILevel.L3)
        client.submit_order(
            instrument="XYZ", side=Side.BUY,
            order_type=OrderType.LIMIT, price=Decimal("100"), quantity=Decimal("10"),
        )
        resp = client.query_order(1, instrument="XYZ")
        assert resp.found is True

    def test_l3_can_query_nbbo(self) -> None:
        client, _ = _make_leveled_client(APILevel.L3)
        assert client.query_nbbo("XYZ").request_status == RequestStatus.ACCEPTED

    def test_l3_can_query_depth(self) -> None:
        client, _ = _make_leveled_client(APILevel.L3)
        assert client.query_depth("XYZ", 5).request_status == RequestStatus.ACCEPTED

    def test_l3_can_query_transactions(self) -> None:
        client, _ = _make_leveled_client(APILevel.L3)
        assert client.query_transactions().request_status == RequestStatus.ACCEPTED

    # -- Misc ------------------------------------------------------------------

    def test_api_level_property(self) -> None:
        config = ExchangeConfig(instruments=["XYZ"])
        clock = Clock(mode=ClockMode.FAST_SIMULATION)
        exchange = Exchange(config, clock)
        client = LocalDMAClient(exchange, api_level=APILevel.L2)
        assert client.api_level == APILevel.L2


# -- Transaction feed ---------------------------------------------------------


class TestTransactionFeed:

    def test_subscribe_and_poll(self) -> None:
        client, exchange = _make_leveled_client(APILevel.L3)
        seller = LocalDMAClient(exchange, api_level=APILevel.L3)
        seller.register()

        client.subscribe_transaction_feed()

        seller.submit_order(
            instrument="XYZ", side=Side.SELL,
            order_type=OrderType.LIMIT, price=Decimal("50"), quantity=Decimal("5"),
        )
        client.submit_order(
            instrument="XYZ", side=Side.BUY,
            order_type=OrderType.MARKET, quantity=Decimal("5"),
        )

        txns = client.poll_transactions()
        assert len(txns) == 1
        assert txns[0].price == Decimal("50")

    def test_poll_advances_cursor(self) -> None:
        client, exchange = _make_leveled_client(APILevel.L3)
        seller = LocalDMAClient(exchange, api_level=APILevel.L3)
        seller.register()
        client.subscribe_transaction_feed()

        # First fill.
        seller.submit_order(
            instrument="XYZ", side=Side.SELL,
            order_type=OrderType.LIMIT, price=Decimal("50"), quantity=Decimal("5"),
        )
        client.submit_order(
            instrument="XYZ", side=Side.BUY,
            order_type=OrderType.MARKET, quantity=Decimal("5"),
        )
        first = client.poll_transactions()
        assert len(first) == 1

        # Second fill.
        seller.submit_order(
            instrument="XYZ", side=Side.SELL,
            order_type=OrderType.LIMIT, price=Decimal("60"), quantity=Decimal("3"),
        )
        client.submit_order(
            instrument="XYZ", side=Side.BUY,
            order_type=OrderType.MARKET, quantity=Decimal("3"),
        )
        second = client.poll_transactions()
        assert len(second) == 1
        assert second[0].price == Decimal("60")

    def test_poll_empty_when_no_new(self) -> None:
        client, _ = _make_leveled_client(APILevel.L3)
        client.subscribe_transaction_feed()
        assert client.poll_transactions() == []

    def test_peek_last_transaction(self) -> None:
        client, exchange = _make_leveled_client(APILevel.L3)
        seller = LocalDMAClient(exchange, api_level=APILevel.L3)
        seller.register()
        client.subscribe_transaction_feed()

        assert client.peek_last_transaction() is None

        seller.submit_order(
            instrument="XYZ", side=Side.SELL,
            order_type=OrderType.LIMIT, price=Decimal("50"), quantity=Decimal("5"),
        )
        client.submit_order(
            instrument="XYZ", side=Side.BUY,
            order_type=OrderType.MARKET, quantity=Decimal("5"),
        )
        assert client.peek_last_transaction().price == Decimal("50")

    def test_poll_before_subscribe_raises(self) -> None:
        client, _ = _make_leveled_client(APILevel.L3)
        with pytest.raises(RuntimeError, match="must subscribe"):
            client.poll_transactions()

    def test_peek_before_subscribe_raises(self) -> None:
        client, _ = _make_leveled_client(APILevel.L3)
        with pytest.raises(RuntimeError, match="must subscribe"):
            client.peek_last_transaction()

    def test_l1_subscribe_raises(self) -> None:
        client, _ = _make_leveled_client(APILevel.L1)
        with pytest.raises(RuntimeError, match="requires L3"):
            client.subscribe_transaction_feed()

    def test_l2_subscribe_raises(self) -> None:
        client, _ = _make_leveled_client(APILevel.L2)
        with pytest.raises(RuntimeError, match="requires L3"):
            client.subscribe_transaction_feed()


# -- FeedHandler integration ---------------------------------------------------


def _make_client_with_handler(
    level: APILevel = APILevel.L3,
) -> tuple[LocalDMAClient, Exchange]:
    """Create a registered LocalDMAClient wired to a FeedHandler."""
    from market_simulator.exchange.feed_handler import FeedHandler
    config = ExchangeConfig(instruments=["XYZ"])
    clock = Clock(mode=ClockMode.FAST_SIMULATION)
    exchange = Exchange(config, clock)
    exchange.open()
    handler = FeedHandler(exchange, starting_transaction_id=config.starting_transaction_id)
    client = LocalDMAClient(exchange, api_level=level, feed_handler=handler)
    client.register()
    return client, exchange


class TestFeedHandlerIntegration:

    def test_register_registers_with_feed_handler(self) -> None:
        client, exchange = _make_client_with_handler()
        # If registered with feed handler, subscribing should work
        # without calling exchange's handle_transaction_feed_subscribe.
        resp = client.subscribe_transaction_feed()
        assert resp.request_status == RequestStatus.ACCEPTED

    def test_subscribe_goes_to_feed_handler(self) -> None:
        client, exchange = _make_client_with_handler()
        client.subscribe_transaction_feed()
        seller = LocalDMAClient(exchange, api_level=APILevel.L3)
        seller.register()
        seller.submit_order(
            instrument="XYZ", side=Side.SELL,
            order_type=OrderType.LIMIT, price=Decimal("50"), quantity=Decimal("5"),
        )
        client.submit_order(
            instrument="XYZ", side=Side.BUY,
            order_type=OrderType.MARKET, quantity=Decimal("5"),
        )
        txns = client.poll_transactions()
        assert len(txns) == 1
        assert txns[0].price == Decimal("50")

    def test_poll_reads_from_feed_handler(self) -> None:
        client, exchange = _make_client_with_handler()
        client.subscribe_transaction_feed()
        seller = LocalDMAClient(exchange, api_level=APILevel.L3)
        seller.register()
        # First trade.
        seller.submit_order(
            instrument="XYZ", side=Side.SELL,
            order_type=OrderType.LIMIT, price=Decimal("50"), quantity=Decimal("5"),
        )
        client.submit_order(
            instrument="XYZ", side=Side.BUY,
            order_type=OrderType.MARKET, quantity=Decimal("5"),
        )
        first = client.poll_transactions()
        assert len(first) == 1
        # Second trade — cursor should have advanced.
        seller.submit_order(
            instrument="XYZ", side=Side.SELL,
            order_type=OrderType.LIMIT, price=Decimal("60"), quantity=Decimal("3"),
        )
        client.submit_order(
            instrument="XYZ", side=Side.BUY,
            order_type=OrderType.MARKET, quantity=Decimal("3"),
        )
        second = client.poll_transactions()
        assert len(second) == 1
        assert second[0].price == Decimal("60")

    def test_peek_reads_from_feed_handler(self) -> None:
        client, exchange = _make_client_with_handler()
        client.subscribe_transaction_feed()
        assert client.peek_last_transaction() is None
        seller = LocalDMAClient(exchange, api_level=APILevel.L3)
        seller.register()
        seller.submit_order(
            instrument="XYZ", side=Side.SELL,
            order_type=OrderType.LIMIT, price=Decimal("50"), quantity=Decimal("5"),
        )
        client.submit_order(
            instrument="XYZ", side=Side.BUY,
            order_type=OrderType.MARKET, quantity=Decimal("5"),
        )
        assert client.peek_last_transaction().price == Decimal("50")

    def test_on_transaction_called_on_push(self) -> None:
        """Verify the _on_transaction callback fires during matching."""
        from market_simulator.exchange.feed_handler import FeedHandler
        config = ExchangeConfig(instruments=["XYZ"])
        clock = Clock(mode=ClockMode.FAST_SIMULATION)
        exchange = Exchange(config, clock)
        exchange.open()
        handler = FeedHandler(exchange, starting_transaction_id=config.starting_transaction_id)

        received = []

        class TrackingClient(LocalDMAClient):
            def _on_transaction(self, transaction):
                received.append(transaction)

        client = TrackingClient(exchange, api_level=APILevel.L3, feed_handler=handler)
        client.register()
        client.subscribe_transaction_feed()
        seller = LocalDMAClient(exchange, api_level=APILevel.L3)
        seller.register()
        seller.submit_order(
            instrument="XYZ", side=Side.SELL,
            order_type=OrderType.LIMIT, price=Decimal("50"), quantity=Decimal("5"),
        )
        client.submit_order(
            instrument="XYZ", side=Side.BUY,
            order_type=OrderType.MARKET, quantity=Decimal("5"),
        )
        assert len(received) == 1
        assert received[0].price == Decimal("50")
