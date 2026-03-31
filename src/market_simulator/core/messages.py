"""Request and response data classes for exchange communication.

These mirror the future proto definitions for network mode. In
single-process mode, they are used as plain Python dataclasses.
"""

from dataclasses import dataclass
from decimal import Decimal

from market_simulator.core.exchange_enums import (
    Action,
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
class RegistrationResponse:
    """Response to a participant registration request.

    Attributes:
        participant_id: The assigned participant ID.
    """
    participant_id: int
