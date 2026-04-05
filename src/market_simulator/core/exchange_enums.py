"""Exchange-related enums shared across components."""

from enum import StrEnum


class APILevel(StrEnum):
    """API access level for DMA clients."""
    L1 = "L1"
    L2 = "L2"
    L3 = "L3"


class Side(StrEnum):
    """Order side: buy or sell."""
    BUY = "BUY"
    SELL = "SELL"


class OrderType(StrEnum):
    """Order type."""
    MARKET = "MARKET"
    LIMIT = "LIMIT"


class OrderStatus(StrEnum):
    """Order lifecycle status."""
    ACCEPTED = "ACCEPTED"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"


class RejectionReason(StrEnum):
    """Reason an order was rejected."""
    UNREGISTERED_PARTICIPANT = "UNREGISTERED_PARTICIPANT"
    UNSUPPORTED_INSTRUMENT = "UNSUPPORTED_INSTRUMENT"
    UNSUPPORTED_ORDER_TYPE = "UNSUPPORTED_ORDER_TYPE"
    NON_POSITIVE_PRICE = "NON_POSITIVE_PRICE"
    NON_POSITIVE_QUANTITY = "NON_POSITIVE_QUANTITY"
    EXCHANGE_CLOSED = "EXCHANGE_CLOSED"
    NO_LIQUIDITY = "NO_LIQUIDITY"
    UNAUTHORIZED_PARTICIPANT = "UNAUTHORIZED_PARTICIPANT"
    INSUFFICIENT_API_LEVEL = "INSUFFICIENT_API_LEVEL"


class ExchangeState(StrEnum):
    """Exchange operational state."""
    OPEN = "OPEN"
    CLOSED = "CLOSED"


class Action(StrEnum):
    """Order message action type for CSV parsing."""
    SUBMIT = "SUBMIT"
    MODIFY = "MODIFY"
    CANCEL = "CANCEL"


class RequestStatus(StrEnum):
    """Status of an order message request.

    Describes the outcome of a request, distinct from the order's
    lifecycle status (OrderStatus).
    """
    ACCEPTED = "ACCEPTED"
    FILLED = "FILLED"
    MODIFIED = "MODIFIED"
    MODIFIED_PRIORITY_RESET = "MODIFIED_PRIORITY_RESET"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"
    ORDER_NOT_FOUND = "ORDER_NOT_FOUND"
    ORDER_INACTIVE = "ORDER_INACTIVE"
    INTERNAL_ERROR = "INTERNAL_ERROR"
