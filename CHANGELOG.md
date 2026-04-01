# Changelog

## v1.1.8 — DMA Client

- Add `DMAClient` ABC in `exchange/client/dma_client.py` using the template method pattern: concrete public API enforces invariants (single registration, must-be-registered), abstract `_send_*` transport methods for subclasses
- Add `LocalDMAClient` in `exchange/client/local_dma_client.py`: in-process dummy/puppet client that calls `Exchange` directly, driven externally by runner or test fixtures
- Single registration per client: `register()` raises `RuntimeError` on second call
- Client stores `participant_id` internally and sets it on all outgoing requests
- Callback-based response pattern (`Callable[[ResponseType], None]`) on all methods for future network transport compatibility
- Add query response dataclasses in `core/messages.py`: `ExchangeStatusResponse`, `DepthResponse`, `OrderQueryResponse`, `TransactionsResponse`
- 16 new tests covering registration, order lifecycle, query methods, and invariant enforcement

## v1.1.7 — Order matching engine

- Add `_match_order` to `Exchange`: fills incoming orders against resting orders at the maker's price, computes maker/taker fees, creates `Transaction` records
- Market orders fill available liquidity; if partially filled, remainder rests on the book at the last fill price
- Market orders with no liquidity rejected with `NO_LIQUIDITY`
- Crossing limit orders fill at the resting (maker) price; unfilled remainder rests on the book
- 18 new tests covering market fills, crossing limits, partial fills, fees, transactions, and edge cases
- Update `DESIGNDOC.md` with market order resting semantics

## v1.1.6 — OrderBook refactor (pure data structure)

- Remove `cancel_order` from `OrderBook` — cancellation now handled entirely by `Exchange`
- Rename `modify_order` to `reposition_order` — only handles queue repositioning; all field updates done by `Exchange`
- `reposition_order` takes `old_price` parameter; caller sets all fields (including price) before calling
- Remove `OrderStatus` import from `order_book.py`
- Update `DESIGNDOC.md` to reflect OrderBook/Exchange boundary

## v1.1.5 — Exchange core (order processing and validation)

- Add `Exchange` class in `exchange/exchange.py` with configurable instruments, fee bps, and starting IDs
- Add `ExchangeConfig` dataclass for exchange constructor configuration
- Unified request/response API mirroring future proto-based network interface:
  - `handle_registration_request() -> RegistrationResponse`
  - `handle_order_message(OrderMessageRequest) -> OrderMessageResponse`
  - Submit, modify, and cancel are private to the exchange
- Add `OrderMessageRequest`, `OrderMessageResponse`, `RegistrationResponse` dataclasses in `core/messages.py`
- Add `RequestStatus` enum in `core/exchange_enums.py` (distinct from `OrderStatus`)
- Full validation with rejection reasons: exchange closed, unregistered participant, unsupported instrument/order type, non-positive price/quantity
- Market orders rejected with `NO_LIQUIDITY` (matching engine deferred to next PR)
- Modify semantics per design doc: quantity decrease keeps priority, price change or quantity increase loses priority, new total <= filled marks FILLED
- Query methods: `get_transactions`, `get_depth`, `get_order`
- Add `ExchangeState` enum (`OPEN`, `CLOSED`) to future-proof exchange operational states
- Add `Order.is_active` property shared by `OrderBook` and `Exchange` (replaces private `_is_active`)
- `OrderMessageResponse` includes full order state fields for DMA client reconstruction
- `get_depth` returns `None` for unknown instruments
- `get_order` / `_find_order` accept optional `instrument` for targeted lookup
- Update `DESIGNDOC.md` with request/response architecture and rationale

## v1.1.4 — Order book

- Add `OrderBook` class in `exchange/order_book.py` with price-time priority using `SortedDict` and `deque`
- Bids use negated price keys for descending sort; asks use natural ascending sort
- Lazy deletion of cancelled/filled orders during peek operations, explicit `cleanup()` for bulk removal
- Methods: `add_order`, `cancel_order`, `get_order`, `modify_order` (with priority loss flag), `best_bid`/`best_ask`, `peek_best_bid`/`peek_best_ask`, `get_depth`, `cleanup`
- Add 42 unit tests covering empty book, price-time priority, FIFO within level, cancel, lazy deletion, modify with/without priority loss, depth reporting, cleanup, and edge cases (98% coverage)

## v1.1.3 — Order and Transaction data classes

- Add `Order` dataclass in `exchange/data.py` with all fields from the design doc (IDs, timestamps, instrument, side, order type, price, quantity, status, rejection reason)
- Add `Transaction` dataclass for matched trades (IDs, timestamp, instrument, price, quantity, maker/taker order and participant IDs, fees)
- Add unit tests for both data classes

## v1.1.2 — Clock

- Add `Clock` class in `core/clock.py` with three modes: REAL_TIME (wall time passthrough with optional offset), FAST_SIMULATION (modeled time with explicit advance/fast-forward), and REAL_TIME_SIMULATION (modeled time with sleep-to-sync)
- Add `ClockMode` enum
- Add unit tests for all clock modes, mode switching, and error handling

## v1.1.1 — Project scaffolding and enums

- Create directory structure: `src/market_simulator/{core,exchange,exchange/client,runner}`, `tests/{unit,e2e,fixtures}`, `scripts/`, `configs/`
- Add core enums using `StrEnum`: `Side`, `OrderType`, `OrderStatus`, `RejectionReason`, `Action`
- Fix `pyproject.toml` build backend (`setuptools.build_meta`)
- Add unit tests for all enums

## v1.0.0 — Initial project setup

- Add `DESIGNDOC.md` with full project design: overview, feasibility analysis, 8-phase roadmap, software engineering principles, directory structure, and Phase 1 Iteration 1 detailed design
- Add Phase 1 architecture diagram (`images/design-fig-1.png`)
- Add `CLAUDE.md` with development workflow and guidelines
- Add `pyproject.toml` with initial dependencies
- Add `CHANGELOG.md`
