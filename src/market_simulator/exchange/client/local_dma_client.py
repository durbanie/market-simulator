"""Local DMA client: in-process puppet driven by the runner.

Has no autonomous behavior.  The runner, test fixtures, or CSV-based
scenarios call its public methods to direct exchange interaction.
"""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

from market_simulator.core.exchange_enums import (
    APILevel,
    Action,
    OrderType,
    Side,
)
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
    RegistrationResponse,
    TransactionsRequest,
    TransactionsResponse,
)
from market_simulator.exchange.client.dma_client import DMAClient
from market_simulator.exchange.data import Transaction
from market_simulator.exchange.exchange import Exchange

if TYPE_CHECKING:
    from market_simulator.exchange.feed_handler import FeedHandler


class LocalDMAClient(DMAClient):
    """Puppet DMA client for in-process use.

    Inherits ``register`` from the base class.  Adds field-level
    convenience methods for orders and queries so the runner can pass
    CSV values directly without constructing request objects.

    Args:
        exchange: The exchange instance to interact with.
        api_level: The API access level for this client.
        feed_handler: Optional FeedHandler for push-based market data.
    """

    def __init__(
        self,
        exchange: Exchange,
        api_level: APILevel = APILevel.L3,
        feed_handler: FeedHandler | None = None,
    ) -> None:
        super().__init__(exchange, api_level, feed_handler)

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

    # -- Query convenience methods (field-level API) ----------------------------

    def query_exchange_status(self) -> ExchangeStatusResponse:
        """Query whether the exchange is open."""
        return self.get_exchange_status(ExchangeStatusRequest(
            participant_id=self._participant_id or 0,
        ))

    def query_nbbo(self, instrument: str) -> NBBOResponse:
        """Query best bid/ask for an instrument."""
        return self.get_nbbo(NBBORequest(
            participant_id=self._participant_id or 0,
            instrument=instrument,
        ))

    def query_depth(
        self, instrument: str, levels: int,
    ) -> DepthResponse:
        """Query order book depth for an instrument."""
        return self.get_depth(DepthRequest(
            participant_id=self._participant_id or 0,
            instrument=instrument,
            levels=levels,
        ))

    def query_order(
        self, order_id: int, instrument: str | None = None,
    ) -> OrderQueryResponse:
        """Query a single order by ID."""
        return self.get_order(OrderQueryRequest(
            participant_id=self._participant_id or 0,
            order_id=order_id,
            instrument=instrument,
        ))

    def query_transactions(self) -> TransactionsResponse:
        """Query all transactions."""
        return self.get_transactions(TransactionsRequest(
            participant_id=self._participant_id or 0,
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

    def _on_nbbo_response(
        self, response: NBBOResponse,
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

    def _on_transaction(
        self, transaction: Transaction,
    ) -> None:
        pass
