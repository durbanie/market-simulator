"""Exchange: order processing, validation, and state management."""

from dataclasses import dataclass
from decimal import Decimal

from market_simulator.core.clock import Clock
from market_simulator.core.exchange_enums import (
    Action,
    OrderStatus,
    OrderType,
    RejectionReason,
    RequestStatus,
    Side,
)
from market_simulator.core.messages import (
    OrderMessageRequest,
    OrderMessageResponse,
    RegistrationResponse,
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

    Public API uses OrderMessageRequest/OrderMessageResponse to mirror
    the future proto-based network interface.

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

    # -- Public request handlers --------------------------------------------

    def handle_registration_request(self) -> RegistrationResponse:
        """Register a new participant and return a RegistrationResponse."""
        pid = self._next_participant_id
        self._next_participant_id += 1
        self._participants.add(pid)
        return RegistrationResponse(participant_id=pid)

    def handle_order_message(
        self, request: OrderMessageRequest,
    ) -> OrderMessageResponse:
        """Dispatch an order message request and return a response."""
        if request.action == Action.SUBMIT:
            return self._submit_order(request)
        if request.action == Action.MODIFY:
            return self._modify_order(request)
        if request.action == Action.CANCEL:
            return self._cancel_order(request)
        return OrderMessageResponse(
            request_status=RequestStatus.REJECTED,
            rejection_reason=RejectionReason.UNSUPPORTED_ORDER_TYPE,
        )

    # -- Order submission ---------------------------------------------------

    def _submit_order(
        self, request: OrderMessageRequest,
    ) -> OrderMessageResponse:
        """Validate and submit an order."""
        order_id = self._next_order_id
        self._next_order_id += 1
        timestamp = self._clock.now()

        order = Order(
            order_id=order_id,
            participant_id=request.participant_id,
            creation_timestamp=timestamp,
            last_modified_timestamp=timestamp,
            instrument=request.instrument,
            side=request.side,
            order_type=request.order_type,
            price=request.price,
            quantity=request.quantity,
            remaining_quantity=request.quantity,
            status=OrderStatus.ACCEPTED,
        )

        rejection = self._validate_order(order)
        if rejection is not None:
            order.status = OrderStatus.REJECTED
            order.rejection_reason = rejection
            return OrderMessageResponse(
                request_status=RequestStatus.REJECTED,
                order_id=order_id,
                rejection_reason=rejection,
            )

        # Add limit orders to the book. Market orders are matched in the
        # matching engine layer; for now they are rejected (no liquidity
        # check yet, but market orders must always fill or reject).
        if order.order_type == OrderType.LIMIT:
            self._order_books[order.instrument].add_order(order)
            return OrderMessageResponse(
                request_status=RequestStatus.ACCEPTED,
                order_id=order_id,
            )

        # Market orders: matching not yet implemented. In this phase,
        # market orders are always either filled or rejected — never
        # resting. Matching PR will handle this; for now reject with
        # NO_LIQUIDITY as a placeholder.
        order.status = OrderStatus.REJECTED
        order.rejection_reason = RejectionReason.NO_LIQUIDITY
        return OrderMessageResponse(
            request_status=RequestStatus.REJECTED,
            order_id=order_id,
            rejection_reason=RejectionReason.NO_LIQUIDITY,
        )

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

    def _modify_order(
        self, request: OrderMessageRequest,
    ) -> OrderMessageResponse:
        """Modify an existing order's price and/or quantity."""
        order = self._find_order(request.order_id)
        if order is None:
            return OrderMessageResponse(
                request_status=RequestStatus.ORDER_NOT_FOUND,
                order_id=request.order_id,
            )

        if not OrderBook._is_active(order):
            return OrderMessageResponse(
                request_status=RequestStatus.ORDER_INACTIVE,
                order_id=request.order_id,
            )

        timestamp = self._clock.now()
        order.last_modified_timestamp = timestamp

        filled = order.quantity - order.remaining_quantity
        new_remaining = request.quantity - filled

        # If new total <= filled, the order is fully filled.
        if new_remaining <= 0:
            order.quantity = request.quantity
            order.remaining_quantity = Decimal("0")
            order.status = OrderStatus.FILLED
            return OrderMessageResponse(
                request_status=RequestStatus.FILLED,
                order_id=order.order_id,
            )

        # Determine if time priority is lost.
        price_changed = (
            request.price is not None and request.price != order.price
        )
        remaining_increased = new_remaining > order.remaining_quantity
        loses_priority = price_changed or remaining_increased

        book = self._order_books[order.instrument]
        book.modify_order(
            order_id=order.order_id,
            new_price=request.price,
            new_quantity=request.quantity,
            new_remaining=new_remaining,
            loses_priority=loses_priority,
        )

        status = (
            RequestStatus.MODIFIED_PRIORITY_RESET
            if loses_priority
            else RequestStatus.MODIFIED
        )
        return OrderMessageResponse(
            request_status=status,
            order_id=order.order_id,
        )

    # -- Order cancellation -------------------------------------------------

    def _cancel_order(
        self, request: OrderMessageRequest,
    ) -> OrderMessageResponse:
        """Cancel an existing order."""
        order = self._find_order(request.order_id)
        if order is None:
            return OrderMessageResponse(
                request_status=RequestStatus.ORDER_NOT_FOUND,
                order_id=request.order_id,
            )

        if not OrderBook._is_active(order):
            return OrderMessageResponse(
                request_status=RequestStatus.ORDER_INACTIVE,
                order_id=request.order_id,
            )

        book = self._order_books[order.instrument]
        book.cancel_order(request.order_id)
        return OrderMessageResponse(
            request_status=RequestStatus.CANCELLED,
            order_id=request.order_id,
        )

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
