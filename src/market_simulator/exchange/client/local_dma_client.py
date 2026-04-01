"""Local DMA client: in-process transport to the exchange.

A dummy/puppet client with no autonomous behavior.  Driven externally
by the runner, test fixtures, or CSV-based scenarios.
"""

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
from market_simulator.exchange.client.dma_client import DMAClient
from market_simulator.exchange.exchange import Exchange


class LocalDMAClient(DMAClient):
    """DMA client that calls the exchange directly in-process.

    All callbacks are invoked synchronously within the calling thread.

    Args:
        exchange: The exchange instance to interact with.
    """

    def __init__(self, exchange: Exchange) -> None:
        super().__init__()
        self._exchange = exchange

    def _send_registration(
        self, on_response: Callable[[RegistrationResponse], None],
    ) -> None:
        response = self._exchange.handle_registration_request()
        self._participant_id = response.participant_id
        on_response(response)

    def _send_order_message(
        self,
        request: OrderMessageRequest,
        on_response: Callable[[OrderMessageResponse], None],
    ) -> None:
        response = self._exchange.handle_order_message(request)
        on_response(response)

    def _send_exchange_status_query(
        self, on_response: Callable[[ExchangeStatusResponse], None],
    ) -> None:
        on_response(ExchangeStatusResponse(is_open=self._exchange.is_open))

    def _send_depth_query(
        self,
        instrument: str,
        levels: int,
        on_response: Callable[[DepthResponse], None],
    ) -> None:
        depth = self._exchange.get_depth(instrument, levels)
        on_response(DepthResponse(instrument=instrument, levels=depth))

    def _send_order_query(
        self,
        order_id: int,
        on_response: Callable[[OrderQueryResponse], None],
        instrument: str | None,
    ) -> None:
        order = self._exchange.get_order(order_id, instrument)
        if order is None:
            on_response(OrderQueryResponse(order_id=order_id, found=False))
            return
        on_response(OrderQueryResponse(
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
        ))

    def _send_transactions_query(
        self, on_response: Callable[[TransactionsResponse], None],
    ) -> None:
        txns = self._exchange.get_transactions()
        on_response(TransactionsResponse(transactions=txns))
