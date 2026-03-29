"""Exchange: order processing, validation, and state management."""

from dataclasses import dataclass
from decimal import Decimal

from market_simulator.core.clock import Clock
from market_simulator.core.exchange_enums import (
    OrderStatus,
    OrderType,
    RejectionReason,
    Side,
)
from market_simulator.exchange.data import Order, Transaction
from market_simulator.exchange.order_book import DepthLevel, OrderBook


@dataclass
class ExchangeConfig:
    """Configuration for an Exchange instance.

    Attributes:
        instruments: Supported ticker symbols.
        maker_fee_bps: Maker fee in basis points (negative = rebate).
        taker_fee_bps: Taker fee in basis points.
        starting_order_id: First order ID to assign.
        starting_transaction_id: First transaction ID to assign.
        starting_participant_id: First participant ID to assign.
    """
    instruments: list[str]
    maker_fee_bps: Decimal = Decimal("-3")
    taker_fee_bps: Decimal = Decimal("7")
    starting_order_id: int = 1
    starting_transaction_id: int = 1
    starting_participant_id: int = 1


class Exchange:
    """Central exchange for order processing and matching.

    The exchange validates incoming order messages, manages order books
    per instrument, and tracks registered participants. Matching and
    fee logic are added in a subsequent layer.

    Args:
        config: Exchange configuration.
        clock: Clock instance for timestamps.
    """

    def __init__(self, config: ExchangeConfig, clock: Clock) -> None:
        self._config = config
        self._clock = clock
        self._is_open = False

        self._next_order_id = config.starting_order_id
        self._next_transaction_id = config.starting_transaction_id
        self._next_participant_id = config.starting_participant_id

        self._participants: set[int] = set()
        self._order_books: dict[str, OrderBook] = {
            instrument: OrderBook(instrument)
            for instrument in config.instruments
        }
        self._transactions: list[Transaction] = []

    # -- Open / Close -------------------------------------------------------

    def open(self) -> None:
        """Open the exchange for trading."""
        self._is_open = True

    def close(self) -> None:
        """Close the exchange. Existing orders remain on the book."""
        self._is_open = False

    @property
    def is_open(self) -> bool:
        """Whether the exchange is currently accepting orders."""
        return self._is_open

    # -- Participant registration -------------------------------------------

    def register_participant(self) -> int:
        """Register a new participant and return their assigned ID."""
        pid = self._next_participant_id
        self._next_participant_id += 1
        self._participants.add(pid)
        return pid

    # -- Order submission ---------------------------------------------------

    def submit_order(
        self,
        participant_id: int,
        instrument: str,
        side: Side,
        order_type: OrderType,
        price: Decimal | None,
        quantity: Decimal,
    ) -> Order:
        """Validate and submit an order. Returns the created Order.

        The order is validated against exchange rules and either accepted
        (added to the book) or rejected with a reason. Market order
        matching and limit order crossing are handled separately.
        """
        order_id = self._next_order_id
        self._next_order_id += 1
        timestamp = self._clock.now()

        order = Order(
            order_id=order_id,
            participant_id=participant_id,
            creation_timestamp=timestamp,
            last_modified_timestamp=timestamp,
            instrument=instrument,
            side=side,
            order_type=order_type,
            price=price,
            quantity=quantity,
            remaining_quantity=quantity,
            status=OrderStatus.ACCEPTED,
        )

        rejection = self._validate_order(order)
        if rejection is not None:
            order.status = OrderStatus.REJECTED
            order.rejection_reason = rejection
            return order

        # Add limit orders to the book. Market orders will be matched
        # in the matching engine layer; for now they are just accepted.
        if order_type == OrderType.LIMIT:
            self._order_books[instrument].add_order(order)

        return order

    def _validate_order(self, order: Order) -> RejectionReason | None:
        """Return a rejection reason, or None if the order is valid."""
        if not self._is_open:
            return RejectionReason.EXCHANGE_CLOSED

        if order.participant_id not in self._participants:
            return RejectionReason.UNREGISTERED_PARTICIPANT

        if order.instrument not in self._order_books:
            return RejectionReason.UNSUPPORTED_INSTRUMENT

        if order.order_type not in (OrderType.MARKET, OrderType.LIMIT):
            return RejectionReason.UNSUPPORTED_ORDER_TYPE

        if order.quantity <= 0:
            return RejectionReason.NON_POSITIVE_QUANTITY

        if order.order_type == OrderType.LIMIT:
            if order.price is None or order.price <= 0:
                return RejectionReason.NON_POSITIVE_PRICE

        return None

    # -- Order modification -------------------------------------------------

    def modify_order(
        self,
        participant_id: int,
        order_id: int,
        new_price: Decimal | None,
        new_quantity: Decimal,
    ) -> Order | None:
        """Modify an existing order's price and/or quantity.

        The quantity refers to the new total order quantity (not the
        remaining). Modify semantics per the design doc:
        - If new total <= already filled, remaining is set to 0 and
          the order is marked FILLED.
        - A price change or increase in remaining quantity loses time
          priority.
        - A decrease in remaining quantity modifies in place.

        Returns the modified order, or None if the order was not found.
        """
        order = self._find_order(order_id)
        if order is None:
            return None

        timestamp = self._clock.now()
        order.last_modified_timestamp = timestamp

        filled = order.quantity - order.remaining_quantity
        new_remaining = new_quantity - filled

        # If new total <= filled, the order is fully filled.
        if new_remaining <= 0:
            order.quantity = new_quantity
            order.remaining_quantity = Decimal("0")
            order.status = OrderStatus.FILLED
            return order

        # Determine if time priority is lost.
        price_changed = new_price is not None and new_price != order.price
        remaining_increased = new_remaining > order.remaining_quantity
        loses_priority = price_changed or remaining_increased

        book = self._order_books[order.instrument]
        book.modify_order(
            order_id=order_id,
            new_price=new_price,
            new_quantity=new_quantity,
            new_remaining=new_remaining,
            loses_priority=loses_priority,
        )

        return order

    # -- Order cancellation -------------------------------------------------

    def cancel_order(
        self,
        participant_id: int,
        order_id: int,
    ) -> Order | None:
        """Cancel an existing order.

        Returns the cancelled order, or None if not found or not active.
        """
        order = self._find_order(order_id)
        if order is None:
            return None

        book = self._order_books[order.instrument]
        return book.cancel_order(order_id)

    # -- Query methods ------------------------------------------------------

    def get_transactions(self) -> list[Transaction]:
        """Return the list of all transactions."""
        return list(self._transactions)

    def get_depth(
        self, instrument: str, levels: int,
    ) -> dict[str, list[DepthLevel]]:
        """Return order book depth for an instrument."""
        book = self._order_books.get(instrument)
        if book is None:
            return {"bids": [], "asks": []}
        return book.get_depth(levels)

    def get_order(self, order_id: int) -> Order | None:
        """Look up an order by ID across all order books."""
        return self._find_order(order_id)

    # -- Internal helpers ---------------------------------------------------

    def _find_order(self, order_id: int) -> Order | None:
        """Search all order books for an order by ID."""
        for book in self._order_books.values():
            order = book.get_order(order_id)
            if order is not None:
                return order
        return None
