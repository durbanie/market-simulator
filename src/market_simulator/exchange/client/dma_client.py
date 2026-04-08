"""DMA client base class.

The base class owns all exchange communication: it calls the exchange,
wraps housekeeping (e.g. storing participant_id), and dispatches
responses to abstract callback methods that subclasses override.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from market_simulator.core.exchange_enums import APILevel
from market_simulator.core.messages import (
    DepthRequest,
    DepthResponse,
    ExchangeStatusRequest,
    ExchangeStatusResponse,
    NBBORequest,
    NBBOResponse,
    OrderMessageRequest,
    OrderMessageResponse,
    OrderQueryRequest,
    OrderQueryResponse,
    RegistrationRequest,
    RegistrationResponse,
    TransactionFeedSubscribeRequest,
    TransactionFeedSubscribeResponse,
    TransactionsRequest,
    TransactionsResponse,
)
from market_simulator.exchange.data import Transaction
from market_simulator.exchange.exchange import Exchange
from market_simulator.exchange.transaction_feed import TransactionFeed

if TYPE_CHECKING:
    from market_simulator.exchange.feed_handler import FeedHandler


class DMAClient(ABC):
    """Base DMA client for exchange interaction.

    Handles all exchange communication directly.  Subclasses implement
    abstract ``_on_*`` callback methods to react to responses.

    Args:
        exchange: The exchange instance to communicate with.
        api_level: The API access level for this client.
        feed_handler: Optional FeedHandler for push-based market data.
            When provided, transaction subscriptions go through the
            feed handler instead of the exchange.
    """

    def __init__(
        self,
        exchange: Exchange,
        api_level: APILevel,
        feed_handler: FeedHandler | None = None,
    ) -> None:
        self._exchange = exchange
        self._api_level = api_level
        self._feed_handler = feed_handler
        self._participant_id: int | None = None
        self._legacy_transaction_feed: TransactionFeed | None = None
        self._last_seen_transaction_id: int = 0

    @property
    def participant_id(self) -> int | None:
        """The participant ID assigned by the exchange, or None."""
        return self._participant_id

    @property
    def api_level(self) -> APILevel:
        """The API access level for this client."""
        return self._api_level

    # -- Exchange communication (concrete) ------------------------------------

    def register(self) -> RegistrationResponse:
        """Register with the exchange and feed handler, store
        participant_id, and dispatch to the
        ``_on_registration_response`` callback.

        May only be called once per client.
        """
        if self._participant_id is not None:
            raise RuntimeError("Client is already registered")
        response = self._exchange.handle_registration_request(
            RegistrationRequest(api_level=self._api_level),
        )
        self._participant_id = response.participant_id
        if self._feed_handler is not None:
            self._feed_handler.register_participant(
                response.participant_id, self._api_level,
            )
        self._on_registration_response(response)
        return response

    def send_order_message(
        self, request: OrderMessageRequest,
    ) -> OrderMessageResponse:
        """Set participant_id on the request, send it to the exchange,
        and dispatch to the ``_on_order_message_response`` callback.
        """
        if self._participant_id is None:
            raise RuntimeError("Client must register before sending orders")
        request.participant_id = self._participant_id
        response = self._exchange.handle_order_message(request)
        self._on_order_message_response(response)
        return response

    def get_exchange_status(
        self, request: ExchangeStatusRequest,
    ) -> ExchangeStatusResponse:
        """Query exchange status and dispatch to callback."""
        response = self._exchange.handle_exchange_status_request(request)
        self._on_exchange_status_response(response)
        return response

    def get_nbbo(
        self, request: NBBORequest,
    ) -> NBBOResponse:
        """Query best bid/ask and dispatch to callback."""
        response = self._exchange.handle_nbbo_request(request)
        self._on_nbbo_response(response)
        return response

    def get_depth(
        self, request: DepthRequest,
    ) -> DepthResponse:
        """Query order book depth and dispatch to callback."""
        if self._api_level < APILevel.L2:
            raise RuntimeError(
                f"Depth query requires L2 or higher (client is {self._api_level})",
            )
        response = self._exchange.handle_depth_request(request)
        self._on_depth_response(response)
        return response

    def get_order(
        self, request: OrderQueryRequest,
    ) -> OrderQueryResponse:
        """Query a single order and dispatch to callback."""
        response = self._exchange.handle_order_query_request(request)
        self._on_order_query_response(response)
        return response

    def get_transactions(
        self, request: TransactionsRequest,
    ) -> TransactionsResponse:
        """Query all transactions and dispatch to callback."""
        if self._api_level < APILevel.L3:
            raise RuntimeError(
                f"Transactions query requires L3 (client is {self._api_level})",
            )
        response = self._exchange.handle_transactions_request(request)
        self._on_transactions_response(response)
        return response

    # -- Transaction feed (concrete) ------------------------------------------

    def subscribe_transaction_feed(
        self,
    ) -> TransactionFeedSubscribeResponse:
        """Subscribe to the transaction feed. Requires L3.

        When a feed handler is present, subscribes through it for
        push-based delivery. Otherwise falls back to the legacy
        exchange subscription path.
        """
        if self._participant_id is None:
            raise RuntimeError("Client must register before subscribing")
        if self._api_level < APILevel.L3:
            raise RuntimeError(
                f"Transaction feed requires L3 (client is {self._api_level})",
            )
        if self._feed_handler is not None:
            return self._feed_handler.subscribe(self._participant_id, self)
        # Legacy path: direct exchange subscription.
        response, feed = self._exchange.handle_transaction_feed_subscribe(
            TransactionFeedSubscribeRequest(
                participant_id=self._participant_id,
            ),
        )
        if feed is not None:
            self._legacy_transaction_feed = feed
        return response

    def poll_transactions(self) -> list[Transaction]:
        """Read new transactions from the feed since last poll.

        Returns an empty list if no new transactions.
        Advances the cursor automatically.
        """
        feed = self._get_transaction_feed()
        new_txns = feed.read_from(self._last_seen_transaction_id)
        if new_txns:
            self._last_seen_transaction_id = new_txns[-1].transaction_id
        return new_txns

    def peek_last_transaction(self) -> Transaction | None:
        """Peek at the most recent transaction without advancing cursor."""
        return self._get_transaction_feed().peek_last()

    def _get_transaction_feed(self) -> TransactionFeed:
        """Resolve the transaction feed from feed handler or legacy ref."""
        if self._feed_handler is not None:
            return self._feed_handler.transaction_feed
        if self._legacy_transaction_feed is not None:
            return self._legacy_transaction_feed
        raise RuntimeError(
            "Client must subscribe to transaction feed first",
        )

    # -- Abstract response callbacks ------------------------------------------

    @abstractmethod
    def _on_registration_response(
        self, response: RegistrationResponse,
    ) -> None: ...

    @abstractmethod
    def _on_order_message_response(
        self, response: OrderMessageResponse,
    ) -> None: ...

    @abstractmethod
    def _on_exchange_status_response(
        self, response: ExchangeStatusResponse,
    ) -> None: ...

    @abstractmethod
    def _on_nbbo_response(
        self, response: NBBOResponse,
    ) -> None: ...

    @abstractmethod
    def _on_depth_response(
        self, response: DepthResponse,
    ) -> None: ...

    @abstractmethod
    def _on_order_query_response(
        self, response: OrderQueryResponse,
    ) -> None: ...

    @abstractmethod
    def _on_transactions_response(
        self, response: TransactionsResponse,
    ) -> None: ...

    @abstractmethod
    def _on_transaction(
        self, transaction: Transaction,
    ) -> None:
        """Called by the FeedHandler for each new transaction (push)."""
        ...
