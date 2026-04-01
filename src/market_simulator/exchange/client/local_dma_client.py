"""Local DMA client: in-process puppet driven by the runner.

Has no autonomous behavior.  The runner, test fixtures, or CSV-based
scenarios call its public methods to direct exchange interaction.
"""

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
    """Puppet DMA client for in-process use.

    Exposes public methods that the runner calls to trigger exchange
    communication.  Response callbacks are no-ops; the runner uses the
    return values from the public methods directly.

    Args:
        exchange: The exchange instance to interact with.
    """

    def __init__(self, exchange: Exchange) -> None:
        super().__init__(exchange)

    # -- Public API for runner / test control ----------------------------------

    def register(self) -> RegistrationResponse:
        """Register with the exchange and return the response."""
        return self._register()

    def send_order_message(
        self, request: OrderMessageRequest,
    ) -> OrderMessageResponse:
        """Send an order message and return the response."""
        return self._send_order_message(request)

    def get_exchange_status(self) -> ExchangeStatusResponse:
        """Query exchange status and return the response."""
        return self._query_exchange_status()

    def get_depth(
        self, instrument: str, levels: int,
    ) -> DepthResponse:
        """Query order book depth and return the response."""
        return self._query_depth(instrument, levels)

    def get_order(
        self, order_id: int, instrument: str | None = None,
    ) -> OrderQueryResponse:
        """Query a single order and return the response."""
        return self._query_order(order_id, instrument)

    def get_transactions(self) -> TransactionsResponse:
        """Query all transactions and return the response."""
        return self._query_transactions()

    # -- Response callbacks (no-ops for puppet) --------------------------------

    def _on_registration_response(
        self, response: RegistrationResponse,
    ) -> None:
        pass

    def _on_order_message_response(
        self, response: OrderMessageResponse,
    ) -> None:
        pass

    def _on_exchange_status_response(
        self, response: ExchangeStatusResponse,
    ) -> None:
        pass

    def _on_depth_response(
        self, response: DepthResponse,
    ) -> None:
        pass

    def _on_order_query_response(
        self, response: OrderQueryResponse,
    ) -> None:
        pass

    def _on_transactions_response(
        self, response: TransactionsResponse,
    ) -> None:
        pass
