"""DMA client base class.

The base class owns all exchange communication: it calls the exchange,
wraps housekeeping (e.g. storing participant_id), and dispatches
responses to abstract callback methods that subclasses override.
"""

from abc import ABC, abstractmethod

from market_simulator.core.messages import (
    DepthResponse,
    ExchangeStatusResponse,
    OrderMessageRequest,
    OrderMessageResponse,
    OrderQueryResponse,
    RegistrationResponse,
    TransactionsResponse,
)
from market_simulator.exchange.exchange import Exchange


class DMAClient(ABC):
    """Base DMA client for exchange interaction.

    Handles all exchange communication directly.  Subclasses implement
    abstract ``_on_*`` callback methods to react to responses, and
    expose whatever public API suits their use case (e.g. a puppet
    client exposes ``register()`` for the runner to call; a smart
    participant might call ``_register()`` internally).

    Args:
        exchange: The exchange instance to communicate with.
    """

    def __init__(self, exchange: Exchange) -> None:
        self._exchange = exchange
        self._participant_id: int | None = None

    @property
    def participant_id(self) -> int | None:
        """The participant ID assigned by the exchange, or None."""
        return self._participant_id

    # -- Exchange communication (concrete) ------------------------------------

    def _register(self) -> RegistrationResponse:
        """Call the exchange to register, store participant_id, and
        dispatch to the ``_on_registration_response`` callback.

        May only be called once per client.
        """
        if self._participant_id is not None:
            raise RuntimeError("Client is already registered")
        response = self._exchange.handle_registration_request()
        self._participant_id = response.participant_id
        self._on_registration_response(response)
        return response

    def _send_order_message(
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

    def _query_exchange_status(self) -> ExchangeStatusResponse:
        """Query exchange status and dispatch to callback."""
        response = ExchangeStatusResponse(is_open=self._exchange.is_open)
        self._on_exchange_status_response(response)
        return response

    def _query_depth(
        self, instrument: str, levels: int,
    ) -> DepthResponse:
        """Query order book depth and dispatch to callback."""
        depth = self._exchange.get_depth(instrument, levels)
        response = DepthResponse(instrument=instrument, levels=depth)
        self._on_depth_response(response)
        return response

    def _query_order(
        self, order_id: int, instrument: str | None = None,
    ) -> OrderQueryResponse:
        """Query a single order and dispatch to callback."""
        order = self._exchange.get_order(order_id, instrument)
        if order is None:
            response = OrderQueryResponse(
                order_id=order_id, found=False,
            )
        else:
            response = OrderQueryResponse(
                order_id=order_id,
                found=True,
                order_status=order.status,
                instrument=order.instrument,
                side=order.side,
                order_type=order.order_type,
                price=order.price,
                quantity=order.quantity,
                remaining_quantity=order.remaining_quantity,
                filled_quantity=order.quantity - order.remaining_quantity,
                creation_timestamp=order.creation_timestamp,
                last_modified_timestamp=order.last_modified_timestamp,
            )
        self._on_order_query_response(response)
        return response

    def _query_transactions(self) -> TransactionsResponse:
        """Query all transactions and dispatch to callback."""
        txns = self._exchange.get_transactions()
        response = TransactionsResponse(transactions=txns)
        self._on_transactions_response(response)
        return response

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
