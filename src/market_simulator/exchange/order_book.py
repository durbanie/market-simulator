"""Order book with price-time priority using SortedDict and deque."""

from collections import deque
from decimal import Decimal

from sortedcontainers import SortedDict

from market_simulator.core.exchange_enums import OrderStatus, Side
from market_simulator.exchange.data import Order

# (price, total_quantity) for a single price level in depth output.
DepthLevel = tuple[Decimal, Decimal]


class OrderBook:
    """Maintains a price-time priority order book for a single instrument.

    Bids use negated price keys in a SortedDict so the highest bid comes
    first. Asks use normal ascending keys. Each price level holds a deque
    of Order references. Cancelled and filled orders are lazily skipped
    during matching and cleaned up explicitly via cleanup().

    Attributes:
        instrument: The ticker symbol this book is for.
    """

    def __init__(self, instrument: str) -> None:
        self.instrument = instrument
        self._bids: SortedDict = SortedDict()  # key: -price
        self._asks: SortedDict = SortedDict()  # key: price
        self._order_map: dict[int, Order] = {}

    def _side_book(self, side: Side) -> SortedDict:
        """Return the SortedDict for the given side."""
        return self._bids if side == Side.BUY else self._asks

    @staticmethod
    def _price_key(side: Side, price: Decimal) -> Decimal:
        """Return the SortedDict key for a price on the given side."""
        return -price if side == Side.BUY else price

    def add_order(self, order: Order) -> None:
        """Add an order to the book at the appropriate price level.

        The order must be a limit order with a non-None price.
        """
        book = self._side_book(order.side)
        key = self._price_key(order.side, order.price)
        if key not in book:
            book[key] = deque()
        book[key].append(order)
        self._order_map[order.order_id] = order

    def cancel_order(self, order_id: int) -> Order | None:
        """Mark an order as cancelled (lazy deletion).

        Returns the order if found, None otherwise.
        """
        order = self._order_map.get(order_id)
        if order is None:
            return None
        order.status = OrderStatus.CANCELLED
        return order

    def get_order(self, order_id: int) -> Order | None:
        """Look up an order by ID."""
        return self._order_map.get(order_id)

    def modify_order(
        self,
        order_id: int,
        new_price: Decimal | None,
        new_remaining: Decimal,
        loses_priority: bool,
    ) -> Order | None:
        """Modify an order's price and/or remaining quantity.

        If loses_priority is True, the order is removed from its current
        queue position and placed at the back of the (possibly new) price
        level. Otherwise, the order is modified in place.

        The caller (Exchange) is responsible for determining whether
        priority is lost and computing the new remaining quantity.

        Returns the modified order, or None if the order is no longer
        active (cancelled/filled).
        """
        order = self._order_map[order_id]

        if not self._is_active(order):
            return None

        if not loses_priority:
            order.remaining_quantity = new_remaining
            return order

        # Remove from current queue position. The order may already have
        # been removed from the deque by lazy deletion in _peek_best, so
        # we silently handle the case where it is not found.
        book = self._side_book(order.side)
        old_key = self._price_key(order.side, order.price)
        if old_key in book:
            queue = book[old_key]
            try:
                queue.remove(order)
            except ValueError:
                pass

        # Update fields.
        if new_price is not None:
            order.price = new_price
        order.remaining_quantity = new_remaining

        # Re-add at back of (possibly new) price level.
        new_key = self._price_key(order.side, order.price)
        if new_key not in book:
            book[new_key] = deque()
        book[new_key].append(order)
        return order

    def best_bid_price(self) -> Decimal | None:
        """Return the highest bid price, or None if no active bids."""
        for neg_price in self._bids:
            queue = self._bids[neg_price]
            if any(self._is_active(o) for o in queue):
                return -neg_price
        return None

    def best_ask_price(self) -> Decimal | None:
        """Return the lowest ask price, or None if no active asks."""
        for price in self._asks:
            queue = self._asks[price]
            if any(self._is_active(o) for o in queue):
                return price
        return None

    def peek_best_bid(self) -> Order | None:
        """Return the first active order at the best bid level.

        Lazily skips cancelled and filled orders at the front of queues.
        """
        return self._peek_best(self._bids)

    def peek_best_ask(self) -> Order | None:
        """Return the first active order at the best ask level.

        Lazily skips cancelled and filled orders at the front of queues.
        """
        return self._peek_best(self._asks)

    def _peek_best(self, book: SortedDict) -> Order | None:
        """Return the first active order from the front of the best level."""
        for key in book:
            queue = book[key]
            # Lazily remove inactive orders from the front.
            while queue and not self._is_active(queue[0]):
                queue.popleft()
            if queue:
                return queue[0]
        return None

    def get_depth(self, levels: int) -> dict[str, list[DepthLevel]]:
        """Return the top N price levels per side.

        Skips empty levels and cancelled/filled orders when summing
        quantities.

        Returns:
            Dict with "bids" and "asks" keys, each containing a list of
            DepthLevel tuples sorted best-to-worst (highest bid first,
            lowest ask first) — ready for display in standard market
            depth format.
        """
        bids = self._get_side_depth(self._bids, Side.BUY, levels)
        asks = self._get_side_depth(self._asks, Side.SELL, levels)
        return {"bids": bids, "asks": asks}

    def _get_side_depth(
        self, book: SortedDict, side: Side, levels: int,
    ) -> list[DepthLevel]:
        """Aggregate depth for one side of the book."""
        result = []
        for key in book:
            if len(result) >= levels:
                break
            queue = book[key]
            total = sum(
                o.remaining_quantity for o in queue if self._is_active(o)
            )
            if total > 0:
                price = -key if side == Side.BUY else key
                result.append((price, total))
        return result

    def cleanup(self) -> None:
        """Remove cancelled/filled orders and empty price levels.

        Typically called at end of trading day or when memory is a concern.
        """
        for book in (self._bids, self._asks):
            keys_to_remove = []
            for key in book:
                queue = book[key]
                # Remove inactive orders from the queue.
                active = deque(o for o in queue if self._is_active(o))
                book[key] = active
                if not active:
                    keys_to_remove.append(key)
            for key in keys_to_remove:
                del book[key]

        # Remove inactive orders from the order map.
        inactive_ids = [
            oid for oid, o in self._order_map.items()
            if not self._is_active(o)
        ]
        for oid in inactive_ids:
            del self._order_map[oid]

    @staticmethod
    def _is_active(order: Order) -> bool:
        """Return True if the order can still be matched or modified."""
        return order.status in (
            OrderStatus.ACCEPTED,
            OrderStatus.PARTIALLY_FILLED,
        )
