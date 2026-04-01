"""Exchange: order processing, validation, and state management."""

from dataclasses import dataclass
from decimal import Decimal

from market_simulator.core.clock import Clock
from market_simulator.core.exchange_enums import (
    Action,
    ExchangeState,
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

    Args:
        config: Exchange configuration.
        clock: Clock instance for timestamps.
    """

    def __init__(self, config: ExchangeConfig, clock: Clock) -> None:
        self._config = config
        self._clock = clock
        self._state = ExchangeState.CLOSED

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
        self._state = ExchangeState.OPEN

    def close(self) -> None:
        """Close the exchange. Existing orders remain on the book."""
        self._state = ExchangeState.CLOSED

    @property
    def state(self) -> ExchangeState:
        """Current exchange operational state."""
        return self._state

    @property
    def is_open(self) -> bool:
        """Whether the exchange is currently accepting orders."""
        return self._state == ExchangeState.OPEN

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

    # -- Shared validation ----------------------------------------------------

    def _validate_request(
        self, request: OrderMessageRequest,
    ) -> RejectionReason | None:
        """Validate request-level fields common to all actions.

        Checks exchange state and participant registration.
        """
        if not self.is_open:
            return RejectionReason.EXCHANGE_CLOSED
        if request.participant_id not in self._participants:
            return RejectionReason.UNREGISTERED_PARTICIPANT
        return None

    def _validate_submit_fields(
        self, order: Order,
    ) -> RejectionReason | None:
        """Validate submit-specific fields on a newly created order."""
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

    def _find_and_validate_order(
        self, request: OrderMessageRequest,
    ) -> OrderMessageResponse | Order:
        """Find the target order and validate order-level fields.

        Checks order existence, participant ownership, and order
        activity. Returns the Order on success, or an
        OrderMessageResponse on failure.

        Must be called after _validate_request.
        """
        order = self._find_order(request.order_id, request.instrument)
        if order is None:
            return OrderMessageResponse(
                request_status=RequestStatus.ORDER_NOT_FOUND,
                order_id=request.order_id,
            )

        if request.participant_id != order.participant_id:
            return OrderMessageResponse(
                request_status=RequestStatus.REJECTED,
                order_id=request.order_id,
                rejection_reason=RejectionReason.UNAUTHORIZED_PARTICIPANT,
            )

        if not order.is_active:
            return self._order_response(
                RequestStatus.ORDER_INACTIVE, order,
            )

        return order

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

        # Request-level validation (exchange open, participant registered).
        request_rejection = self._validate_request(request)
        if request_rejection is not None:
            order.status = OrderStatus.REJECTED
            order.rejection_reason = request_rejection
            return self._order_response(
                RequestStatus.REJECTED, order, request_rejection,
            )

        # Submit-specific validation (instrument, order type, quantity, price).
        submit_rejection = self._validate_submit_fields(order)
        if submit_rejection is not None:
            order.status = OrderStatus.REJECTED
            order.rejection_reason = submit_rejection
            return self._order_response(
                RequestStatus.REJECTED, order, submit_rejection,
            )

        # Add limit orders to the book.
        if order.order_type == OrderType.LIMIT:
            self._order_books[order.instrument].add_order(order)
            return self._order_response(RequestStatus.ACCEPTED, order)

        # Market orders must always fill or be rejected — never rest on
        # the book. Matching engine will handle fills; for now reject
        # with NO_LIQUIDITY.
        order.status = OrderStatus.REJECTED
        order.rejection_reason = RejectionReason.NO_LIQUIDITY
        return self._order_response(
            RequestStatus.REJECTED, order, RejectionReason.NO_LIQUIDITY,
        )

    # -- Order modification -------------------------------------------------

    def _modify_order(
        self, request: OrderMessageRequest,
    ) -> OrderMessageResponse:
        """Modify an existing order's price and/or quantity."""
        request_rejection = self._validate_request(request)
        if request_rejection is not None:
            return OrderMessageResponse(
                request_status=RequestStatus.REJECTED,
                order_id=request.order_id,
                rejection_reason=request_rejection,
            )

        result = self._find_and_validate_order(request)
        if isinstance(result, OrderMessageResponse):
            return result
        order = result

        timestamp = self._clock.now()
        order.last_modified_timestamp = timestamp

        filled_quantity = order.quantity - order.remaining_quantity
        new_remaining = request.quantity - filled_quantity

        # If new total <= filled, the order is fully filled. Set quantity
        # to the actual filled amount so filled_quantity is accurate.
        if new_remaining <= 0:
            order.quantity = filled_quantity
            order.remaining_quantity = Decimal("0")
            order.status = OrderStatus.FILLED
            return self._order_response(RequestStatus.FILLED, order)

        # Determine if time priority is lost.
        price_changed = (
            request.price is not None and request.price != order.price
        )
        remaining_increased = new_remaining > order.remaining_quantity
        loses_priority = price_changed or remaining_increased

        # Update order fields.
        old_price = order.price
        order.quantity = request.quantity
        order.remaining_quantity = new_remaining
        if price_changed:
            order.price = request.price

        if loses_priority:
            book = self._order_books[order.instrument]
            book.reposition_order(order.order_id, old_price)

        status = (
            RequestStatus.MODIFIED_PRIORITY_RESET
            if loses_priority
            else RequestStatus.MODIFIED
        )
        return self._order_response(status, order)

    # -- Order cancellation -------------------------------------------------

    def _cancel_order(
        self, request: OrderMessageRequest,
    ) -> OrderMessageResponse:
        """Cancel an existing order."""
        request_rejection = self._validate_request(request)
        if request_rejection is not None:
            return OrderMessageResponse(
                request_status=RequestStatus.REJECTED,
                order_id=request.order_id,
                rejection_reason=request_rejection,
            )

        result = self._find_and_validate_order(request)
        if isinstance(result, OrderMessageResponse):
            return result
        order = result

        order.status = OrderStatus.CANCELLED
        order.last_modified_timestamp = self._clock.now()
        return self._order_response(RequestStatus.CANCELLED, order)

    # -- Query methods ------------------------------------------------------

    def get_transactions(self) -> list[Transaction]:
        """Return the list of all transactions."""
        return list(self._transactions)

    def get_depth(
        self, instrument: str, levels: int,
    ) -> dict[str, list[DepthLevel]] | None:
        """Return order book depth for an instrument, or None if unknown."""
        book = self._order_books.get(instrument)
        if book is None:
            return None
        return book.get_depth(levels)

    def get_order(
        self, order_id: int, instrument: str | None = None,
    ) -> Order | None:
        """Look up an order by ID, optionally scoped to an instrument."""
        return self._find_order(order_id, instrument)

    # -- Internal helpers ---------------------------------------------------

    @staticmethod
    def _order_response(
        request_status: RequestStatus,
        order: Order,
        rejection_reason: RejectionReason | None = None,
    ) -> OrderMessageResponse:
        """Build an OrderMessageResponse populated from an Order."""
        return OrderMessageResponse(
            request_status=request_status,
            order_id=order.order_id,
            rejection_reason=rejection_reason,
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

    def _find_order(
        self, order_id: int, instrument: str | None = None,
    ) -> Order | None:
        """Search order books for an order by ID.

        If instrument is provided, only that book is checked.
        Otherwise, all books are searched.
        """
        if instrument is not None:
            book = self._order_books.get(instrument)
            if book is not None:
                return book.get_order(order_id)
            return None
        for book in self._order_books.values():
            order = book.get_order(order_id)
            if order is not None:
                return order
        return None
