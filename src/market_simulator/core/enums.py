"""Core enums for the market simulator."""

from enum import StrEnum


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


class Action(StrEnum):
    """Order message action type for CSV parsing."""
    SUBMIT = "SUBMIT"
    MODIFY = "MODIFY"
    CANCEL = "CANCEL"
