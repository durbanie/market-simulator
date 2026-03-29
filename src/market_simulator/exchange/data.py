"""Data classes for exchange orders and transactions."""

from dataclasses import dataclass
from decimal import Decimal

from market_simulator.core.exchange_enums import (
    OrderStatus,
    OrderType,
    RejectionReason,
    Side,
)


@dataclass
class Order:
    """Represents an order on the exchange.

    Attributes:
        order_id: Unique identifier assigned by the exchange.
        participant_id: ID of the participant who placed the order.
        creation_timestamp: When the order was created (microseconds).
        last_modified_timestamp: When the order was last modified
            (microseconds).
        instrument: Ticker symbol (e.g. "XYZ").
        side: BUY or SELL.
        order_type: MARKET or LIMIT.
        price: Limit price in USD, or None for market orders.
        quantity: Original total order quantity.
        remaining_quantity: Quantity not yet filled.
        status: Current order lifecycle status.
        rejection_reason: Reason for rejection, or None if not rejected.
    """
    order_id: int
    participant_id: int
    creation_timestamp: int
    last_modified_timestamp: int
    instrument: str
    side: Side
    order_type: OrderType
    price: Decimal | None
    quantity: Decimal
    remaining_quantity: Decimal
    status: OrderStatus
    rejection_reason: RejectionReason | None = None


@dataclass
class Transaction:
    """Represents a matched trade on the exchange.

    Attributes:
        transaction_id: Unique identifier assigned by the exchange.
        timestamp: When the match occurred (microseconds).
        instrument: Ticker symbol.
        price: Fill price in USD.
        quantity: Quantity filled.
        maker_order_id: Order ID of the resting (maker) order.
        taker_order_id: Order ID of the incoming (taker) order.
        maker_participant_id: Participant ID of the maker.
        taker_participant_id: Participant ID of the taker.
        maker_fee: Fee charged to maker (negative for rebate).
        taker_fee: Fee charged to taker.
    """
    transaction_id: int
    timestamp: int
    instrument: str
    price: Decimal
    quantity: Decimal
    maker_order_id: int
    taker_order_id: int
    maker_participant_id: int
    taker_participant_id: int
    maker_fee: Decimal
    taker_fee: Decimal
