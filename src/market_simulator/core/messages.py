"""Request and response data classes for exchange communication.

These mirror the future proto definitions for network mode. In
single-process mode, they are used as plain Python dataclasses.
"""

from dataclasses import dataclass
from decimal import Decimal

from market_simulator.core.exchange_enums import (
    Action,
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

    Attributes:
        request_status: Outcome of the request.
        order_id: The affected order's ID, or None if not found.
        rejection_reason: Set only when request_status is REJECTED.
    """
    request_status: RequestStatus
    order_id: int | None = None
    rejection_reason: RejectionReason | None = None


@dataclass
class RegistrationResponse:
    """Response to a participant registration request.

    Attributes:
        participant_id: The assigned participant ID.
    """
    participant_id: int
