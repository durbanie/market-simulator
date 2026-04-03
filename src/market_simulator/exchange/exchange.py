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
    DepthRequest,
    DepthResponse,
    ExchangeStatusRequest,
    ExchangeStatusResponse,
    OrderMessageRequest,
    OrderMessageResponse,
    OrderQueryRequest,
    OrderQueryResponse,
    RegistrationResponse,
    TransactionsRequest,
    TransactionsResponse,
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
    per instrument, matches crossing orders, and tracks registered
    participants.

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

        book = self._order_books[order.instrument]

        if order.order_type == OrderType.LIMIT:
            self._match_order(order, book)
            if order.remaining_quantity > 0:
                book.add_order(order)
            request_status = (
                RequestStatus.FILLED if order.status == OrderStatus.FILLED
                else RequestStatus.ACCEPTED
            )
            return self._order_response(request_status, order)

        # Market orders: fill what's available, rest remainder at last
        # fill price. Reject if no liquidity at all.
        peek = (book.peek_best_ask if order.side == Side.BUY
                else book.peek_best_bid)
        if peek() is None:
            order.status = OrderStatus.REJECTED
            order.rejection_reason = RejectionReason.NO_LIQUIDITY
            return self._order_response(
                RequestStatus.REJECTED, order, RejectionReason.NO_LIQUIDITY,
            )
        self._match_order(order, book)
        if order.remaining_quantity > 0:
            # Rest remainder at the last fill price.
            order.price = self._transactions[-1].price
            book.add_order(order)
        request_status = (
            RequestStatus.FILLED if order.status == OrderStatus.FILLED
            else RequestStatus.ACCEPTED
        )
        return self._order_response(request_status, order)

    # -- Order matching -----------------------------------------------------

    def _match_order(self, order: Order, book: OrderBook) -> None:
        """Match an incoming order against resting orders on the book.

        Fills execute at the resting (maker) order's price. Each fill
        creates a Transaction. Both the incoming and resting orders are
        updated in place. Market orders must have sufficient liquidity
        verified before calling this method.

        Args:
            order: The incoming (taker) order.
            book: The order book for the order's instrument.
        """
        timestamp = self._clock.now()
        peek = (book.peek_best_ask if order.side == Side.BUY
                else book.peek_best_bid)
        bps_divisor = Decimal("10000")

        while order.remaining_quantity > 0:
            resting = peek()
            if resting is None:
                break

            # Limit orders only match if the price crosses.
            if order.order_type == OrderType.LIMIT:
                if order.side == Side.BUY and order.price < resting.price:
                    break
                if order.side == Side.SELL and order.price > resting.price:
                    break

            fill_qty = min(order.remaining_quantity, resting.remaining_quantity)
            fill_price = resting.price

            # Update resting (maker) order.
            resting.remaining_quantity -= fill_qty
            resting.status = (
                OrderStatus.FILLED if resting.remaining_quantity == 0
                else OrderStatus.PARTIALLY_FILLED
            )
            resting.last_modified_timestamp = timestamp

            # Update incoming (taker) order.
            order.remaining_quantity -= fill_qty
            order.status = (
                OrderStatus.FILLED if order.remaining_quantity == 0
                else OrderStatus.PARTIALLY_FILLED
            )
            order.last_modified_timestamp = timestamp

            # Compute fees.
            notional = fill_price * fill_qty
            maker_fee = notional * self._config.maker_fee_bps / bps_divisor
            taker_fee = notional * self._config.taker_fee_bps / bps_divisor

            # Record transaction.
            txn = Transaction(
                transaction_id=self._next_transaction_id,
                timestamp=timestamp,
                instrument=order.instrument,
                price=fill_price,
                quantity=fill_qty,
                maker_order_id=resting.order_id,
                taker_order_id=order.order_id,
                maker_participant_id=resting.participant_id,
                taker_participant_id=order.participant_id,
                maker_fee=maker_fee,
                taker_fee=taker_fee,
            )
            self._next_transaction_id += 1
            self._transactions.append(txn)

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

    # -- Query handlers -------------------------------------------------------

    def _validate_query_participant(
        self, participant_id: int,
    ) -> RejectionReason | None:
        """Validate participant_id for query requests."""
        if participant_id not in self._participants:
            return RejectionReason.UNREGISTERED_PARTICIPANT
        return None

    def handle_exchange_status_request(
        self, request: ExchangeStatusRequest,
    ) -> ExchangeStatusResponse:
        """Return the current exchange operational status."""
        rejection = self._validate_query_participant(request.participant_id)
        if rejection is not None:
            return ExchangeStatusResponse(
                request_status=RequestStatus.REJECTED,
                rejection_reason=rejection,
            )
        return ExchangeStatusResponse(
            request_status=RequestStatus.ACCEPTED,
            is_open=self.is_open,
        )

    def handle_depth_request(
        self, request: DepthRequest,
    ) -> DepthResponse:
        """Return order book depth for an instrument."""
        rejection = self._validate_query_participant(request.participant_id)
        if rejection is not None:
            return DepthResponse(
                request_status=RequestStatus.REJECTED,
                instrument=request.instrument,
                rejection_reason=rejection,
            )
        book = self._order_books.get(request.instrument)
        levels = None if book is None else book.get_depth(request.levels)
        return DepthResponse(
            request_status=RequestStatus.ACCEPTED,
            instrument=request.instrument,
            levels=levels,
        )

    def handle_order_query_request(
        self, request: OrderQueryRequest,
    ) -> OrderQueryResponse:
        """Look up an order by ID and return its state."""
        rejection = self._validate_query_participant(request.participant_id)
        if rejection is not None:
            return OrderQueryResponse(
                request_status=RequestStatus.REJECTED,
                order_id=request.order_id,
                rejection_reason=rejection,
            )
        order = self._find_order(request.order_id, request.instrument)
        if order is None:
            return OrderQueryResponse(
                request_status=RequestStatus.ACCEPTED,
                order_id=request.order_id,
                found=False,
            )
        return OrderQueryResponse(
            request_status=RequestStatus.ACCEPTED,
            order_id=request.order_id,
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

    def handle_transactions_request(
        self, request: TransactionsRequest,
    ) -> TransactionsResponse:
        """Return the list of all transactions."""
        rejection = self._validate_query_participant(request.participant_id)
        if rejection is not None:
            return TransactionsResponse(
                request_status=RequestStatus.REJECTED,
                rejection_reason=rejection,
            )
        return TransactionsResponse(
            request_status=RequestStatus.ACCEPTED,
            transactions=list(self._transactions),
        )

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
