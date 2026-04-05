"""Request and response data classes for exchange communication.

These mirror the future proto definitions for network mode. In
single-process mode, they are used as plain Python dataclasses.
"""

from dataclasses import dataclass
from decimal import Decimal

from market_simulator.core.exchange_enums import (
    Action,
    APILevel,
    OrderStatus,
    OrderType,
    RejectionReason,
    RequestStatus,
    Side,
)


@dataclass
class OrderMessageRequest:
    """A request to submit, modify, or cancel an order.

    Fields are optional depending on the action:
    - SUBMIT: participant_id, instrument, side, order_type, price
      (None for market), quantity
    - MODIFY: participant_id, order_id, price (None to keep), quantity
    - CANCEL: participant_id, order_id
    """
    action: Action
    participant_id: int
    instrument: str | None = None
    side: Side | None = None
    order_type: OrderType | None = None
    price: Decimal | None = None
    quantity: Decimal | None = None
    order_id: int | None = None


@dataclass
class OrderMessageResponse:
    """Response to an order message request.

    Includes flat fields mirroring the order state so that DMA clients
    can reconstruct the order without a separate query. All order fields
    are None when the order was not found.

    Attributes:
        request_status: Outcome of the request.
        order_id: The affected order's ID, or None if not found.
        rejection_reason: Set only when request_status is REJECTED.
        order_status: Order lifecycle status after the operation.
        instrument: Ticker symbol.
        side: BUY or SELL.
        order_type: MARKET or LIMIT.
        price: Current limit price, or None for market orders.
        quantity: Current total order quantity.
        remaining_quantity: Quantity not yet filled.
        filled_quantity: Quantity already filled.
        creation_timestamp: When the order was created (microseconds).
        last_modified_timestamp: When the order was last modified.
    """
    request_status: RequestStatus
    order_id: int | None = None
    rejection_reason: RejectionReason | None = None
    order_status: OrderStatus | None = None
    instrument: str | None = None
    side: Side | None = None
    order_type: OrderType | None = None
    price: Decimal | None = None
    quantity: Decimal | None = None
    remaining_quantity: Decimal | None = None
    filled_quantity: Decimal | None = None
    creation_timestamp: int | None = None
    last_modified_timestamp: int | None = None


@dataclass
class RegistrationRequest:
    """Request to register a new participant.

    Attributes:
        api_level: The API access level requested.
    """
    api_level: APILevel


@dataclass
class RegistrationResponse:
    """Response to a participant registration request.

    Attributes:
        participant_id: The assigned participant ID.
    """
    participant_id: int


@dataclass
class ExchangeStatusRequest:
    """Request for the exchange's current operational status.

    Attributes:
        participant_id: The requesting participant's ID.
    """
    participant_id: int


@dataclass
class ExchangeStatusResponse:
    """Response for an exchange status query.

    Attributes:
        request_status: Outcome of the request.
        rejection_reason: Set only when request_status is REJECTED.
        is_open: Whether the exchange is currently accepting orders.
    """
    request_status: RequestStatus
    is_open: bool | None = None
    rejection_reason: RejectionReason | None = None


@dataclass
class NBBORequest:
    """Request for the national best bid and offer.

    Attributes:
        participant_id: The requesting participant's ID.
        instrument: The ticker symbol to query.
    """
    participant_id: int
    instrument: str


@dataclass
class NBBOResponse:
    """Response for an NBBO query.

    Attributes:
        request_status: Outcome of the request.
        instrument: The queried instrument.
        best_bid: Best bid price, or None if no bids.
        best_ask: Best ask price, or None if no asks.
        rejection_reason: Set only when request_status is REJECTED.
    """
    request_status: RequestStatus
    instrument: str
    best_bid: Decimal | None = None
    best_ask: Decimal | None = None
    rejection_reason: RejectionReason | None = None


@dataclass
class DepthRequest:
    """Request for order book depth on an instrument.

    Attributes:
        participant_id: The requesting participant's ID.
        instrument: The ticker symbol to query.
        levels: Number of price levels to return per side.
    """
    participant_id: int
    instrument: str
    levels: int


@dataclass
class DepthResponse:
    """Response for an order book depth query.

    Attributes:
        request_status: Outcome of the request.
        instrument: The queried instrument.
        levels: Depth levels keyed by "bids" and "asks", or None if
            the instrument is unknown.
        rejection_reason: Set only when request_status is REJECTED.
    """
    request_status: RequestStatus
    instrument: str
    levels: dict[str, list] | None = None
    rejection_reason: RejectionReason | None = None


@dataclass
class OrderQueryRequest:
    """Request for a single order's state.

    Attributes:
        participant_id: The requesting participant's ID.
        order_id: The order to look up.
        instrument: Optional instrument to narrow the search.
    """
    participant_id: int
    order_id: int
    instrument: str | None = None


@dataclass
class OrderQueryResponse:
    """Response for a single order query.

    Flat order fields are None when the order is not found, following
    the same pattern as OrderMessageResponse.

    Attributes:
        request_status: Outcome of the request.
        order_id: The queried order ID.
        found: Whether the order was found.
        rejection_reason: Set only when request_status is REJECTED.
    """
    request_status: RequestStatus
    order_id: int
    found: bool = False
    rejection_reason: RejectionReason | None = None
    order_status: OrderStatus | None = None
    instrument: str | None = None
    side: Side | None = None
    order_type: OrderType | None = None
    price: Decimal | None = None
    quantity: Decimal | None = None
    remaining_quantity: Decimal | None = None
    filled_quantity: Decimal | None = None
    creation_timestamp: int | None = None
    last_modified_timestamp: int | None = None


@dataclass
class TransactionsRequest:
    """Request for the list of all transactions.

    Attributes:
        participant_id: The requesting participant's ID.
    """
    participant_id: int


@dataclass
class TransactionsResponse:
    """Response for a transactions query.

    Attributes:
        request_status: Outcome of the request.
        transactions: List of Transaction records.
        rejection_reason: Set only when request_status is REJECTED.
    """
    request_status: RequestStatus
    transactions: list | None = None
    rejection_reason: RejectionReason | None = None
