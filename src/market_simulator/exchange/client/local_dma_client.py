"""Local DMA client: in-process puppet driven by the runner.

Has no autonomous behavior.  The runner, test fixtures, or CSV-based
scenarios call its public methods to direct exchange interaction.
"""

from decimal import Decimal

from market_simulator.core.exchange_enums import (
    Action,
    OrderType,
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
from market_simulator.exchange.client.dma_client import DMAClient
from market_simulator.exchange.exchange import Exchange


class LocalDMAClient(DMAClient):
    """Puppet DMA client for in-process use.

    Inherits ``register``, ``get_exchange_status``, ``get_depth``,
    ``get_order``, and ``get_transactions`` from the base class.
    Adds ``submit_order``, ``modify_order``, and ``cancel_order``
    that accept individual fields so the runner can pass CSV values
    directly without constructing ``OrderMessageRequest`` objects.

    Args:
        exchange: The exchange instance to interact with.
    """

    def __init__(self, exchange: Exchange) -> None:
        super().__init__(exchange)

    # -- Order convenience methods (field-level API) --------------------------

    def submit_order(
        self,
        instrument: str,
        side: Side,
        order_type: OrderType,
        quantity: Decimal,
        price: Decimal | None = None,
    ) -> OrderMessageResponse:
        """Submit an order with individual fields."""
        return self.send_order_message(OrderMessageRequest(
            action=Action.SUBMIT,
            participant_id=0,  # set by base class
            instrument=instrument,
            side=side,
            order_type=order_type,
            price=price,
            quantity=quantity,
        ))

    def modify_order(
        self,
        order_id: int,
        quantity: Decimal,
        price: Decimal | None = None,
        instrument: str | None = None,
    ) -> OrderMessageResponse:
        """Modify an existing order with individual fields."""
        return self.send_order_message(OrderMessageRequest(
            action=Action.MODIFY,
            participant_id=0,  # set by base class
            order_id=order_id,
            price=price,
            quantity=quantity,
            instrument=instrument,
        ))

    def cancel_order(
        self,
        order_id: int,
        instrument: str | None = None,
    ) -> OrderMessageResponse:
        """Cancel an existing order."""
        return self.send_order_message(OrderMessageRequest(
            action=Action.CANCEL,
            participant_id=0,  # set by base class
            order_id=order_id,
            instrument=instrument,
        ))

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
