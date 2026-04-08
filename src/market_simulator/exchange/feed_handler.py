"""FeedHandler: distributes market data from the exchange to subscribers.

The FeedHandler sits between the exchange and DMA clients, mirroring
real exchange multicast infrastructure. It registers as a transaction
listener on the exchange and pushes each transaction to subscribed
clients via their ``_on_transaction`` callback.

In network mode, the FeedHandler would receive transactions over
WebSocket from a remote exchange and distribute locally to co-located
clients.
"""

from typing import Any

from market_simulator.core.exchange_enums import APILevel, RejectionReason, RequestStatus
from market_simulator.core.messages import TransactionFeedSubscribeResponse
from market_simulator.exchange.data import Transaction
from market_simulator.exchange.exchange import Exchange
from market_simulator.exchange.transaction_feed import TransactionFeed


class FeedHandler:
    """Distributes transaction data from the exchange to subscribed clients.

    Args:
        exchange: The exchange to listen to.
        starting_transaction_id: Starting ID for the internal
            transaction feed (history buffer).
    """

    def __init__(
        self,
        exchange: Exchange,
        starting_transaction_id: int = 1,
    ) -> None:
        self._exchange = exchange
        self._transaction_feed = TransactionFeed(starting_transaction_id)
        self._participant_api_levels: dict[int, APILevel] = {}
        self._subscribers: dict[int, Any] = {}
        exchange.add_transaction_listener(self._on_exchange_transaction)

    def _on_exchange_transaction(self, transaction: Transaction) -> None:
        """Listener callback invoked by the exchange for each new transaction."""
        self._transaction_feed.append(transaction)
        for client in self._subscribers.values():
            client._on_transaction(transaction)

    def register_participant(
        self, participant_id: int, api_level: APILevel,
    ) -> None:
        """Record a participant's API level for subscription enforcement.

        Called by DMAClient.register() after successful exchange
        registration.
        """
        self._participant_api_levels[participant_id] = api_level

    def subscribe(
        self, participant_id: int, client: Any,
    ) -> TransactionFeedSubscribeResponse:
        """Subscribe a client to receive transaction push notifications.

        Enforces L3 API level requirement. The client must implement
        an ``_on_transaction(transaction)`` method.

        Args:
            participant_id: The registered participant's ID.
            client: The DMAClient instance to receive callbacks.
        """
        if participant_id not in self._participant_api_levels:
            return TransactionFeedSubscribeResponse(
                request_status=RequestStatus.REJECTED,
                rejection_reason=RejectionReason.UNREGISTERED_PARTICIPANT,
            )
        if self._participant_api_levels[participant_id] < APILevel.L3:
            return TransactionFeedSubscribeResponse(
                request_status=RequestStatus.REJECTED,
                rejection_reason=RejectionReason.INSUFFICIENT_API_LEVEL,
            )
        self._subscribers[participant_id] = client
        return TransactionFeedSubscribeResponse(
            request_status=RequestStatus.ACCEPTED,
        )

    @property
    def transaction_feed(self) -> TransactionFeed:
        """The internal transaction feed (history buffer)."""
        return self._transaction_feed
