"""DMA client base class with template method pattern.

Public methods enforce invariants (single registration, must-be-registered)
and delegate to abstract transport methods that subclasses implement.
"""

from abc import ABC, abstractmethod
from collections.abc import Callable

from market_simulator.core.messages import (
    DepthResponse,
    ExchangeStatusResponse,
    OrderMessageRequest,
    OrderMessageResponse,
    OrderQueryResponse,
    RegistrationResponse,
    TransactionsResponse,
)


class DMAClient(ABC):
    """Base DMA client for exchange interaction.

    Provides a concrete public API that enforces registration invariants,
    then delegates to abstract ``_send_*`` transport methods.  Subclasses
    implement the transport layer (local direct call, network, etc.).
    """

    def __init__(self) -> None:
        self._participant_id: int | None = None

    @property
    def participant_id(self) -> int | None:
        """The participant ID assigned by the exchange, or None."""
        return self._participant_id

    # -- Public API (concrete) ------------------------------------------------

    def register(
        self, on_response: Callable[[RegistrationResponse], None],
    ) -> None:
        """Register with the exchange. May only be called once."""
        if self._participant_id is not None:
            raise RuntimeError("Client is already registered")
        self._send_registration(on_response)

    def send_order_message(
        self,
        request: OrderMessageRequest,
        on_response: Callable[[OrderMessageResponse], None],
    ) -> None:
        """Send an order message (submit, modify, or cancel)."""
        if self._participant_id is None:
            raise RuntimeError("Client must register before sending orders")
        request.participant_id = self._participant_id
        self._send_order_message(request, on_response)

    def get_exchange_status(
        self, on_response: Callable[[ExchangeStatusResponse], None],
    ) -> None:
        """Query whether the exchange is open."""
        self._send_exchange_status_query(on_response)

    def get_depth(
        self,
        instrument: str,
        levels: int,
        on_response: Callable[[DepthResponse], None],
    ) -> None:
        """Query order book depth for an instrument."""
        self._send_depth_query(instrument, levels, on_response)

    def get_order(
        self,
        order_id: int,
        on_response: Callable[[OrderQueryResponse], None],
        instrument: str | None = None,
    ) -> None:
        """Query a single order by ID."""
        self._send_order_query(order_id, on_response, instrument)

    def get_transactions(
        self, on_response: Callable[[TransactionsResponse], None],
    ) -> None:
        """Query the list of all transactions."""
        self._send_transactions_query(on_response)

    # -- Abstract transport methods -------------------------------------------

    @abstractmethod
    def _send_registration(
        self, on_response: Callable[[RegistrationResponse], None],
    ) -> None: ...

    @abstractmethod
    def _send_order_message(
        self,
        request: OrderMessageRequest,
        on_response: Callable[[OrderMessageResponse], None],
    ) -> None: ...

    @abstractmethod
    def _send_exchange_status_query(
        self, on_response: Callable[[ExchangeStatusResponse], None],
    ) -> None: ...

    @abstractmethod
    def _send_depth_query(
        self,
        instrument: str,
        levels: int,
        on_response: Callable[[DepthResponse], None],
    ) -> None: ...

    @abstractmethod
    def _send_order_query(
        self,
        order_id: int,
        on_response: Callable[[OrderQueryResponse], None],
        instrument: str | None,
    ) -> None: ...

    @abstractmethod
    def _send_transactions_query(
        self, on_response: Callable[[TransactionsResponse], None],
    ) -> None: ...
