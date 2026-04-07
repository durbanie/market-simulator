# Changelog

## v1.1.13 — Shared broadcast transaction feed

- Add `TransactionFeed` class in `exchange/transaction_feed.py`: shared append-only feed with cursor-based reads using O(1) index calculation from sequential transaction IDs
- Replace `Exchange._transactions` list with `TransactionFeed`; matching appends to feed
- Add `TransactionFeedSubscribeRequest` / `TransactionFeedSubscribeResponse` messages
- Add `handle_transaction_feed_subscribe` on `Exchange`: validates L3 access, returns feed reference out-of-band as tuple for network-mode extensibility
- Add `subscribe_transaction_feed`, `poll_transactions`, `peek_last_transaction` to `DMAClient` base class
- Runner uses feed for transaction printing (poll) and last txn price (peek) instead of `handle_transactions_request`
- Append validates transaction ID matches expected sequential position
- Backward-compatible `handle_transactions_request` still works via `read_from(0)`
- 26 new tests: 15 for TransactionFeed, 5 for exchange subscribe, 8 for client feed methods

## v1.1.12 — API levels (L1, L2, L3)

- Add `APILevel` enum (`L1`, `L2`, `L3`) to `exchange_enums.py` with hierarchical comparison
- Add `RegistrationRequest(api_level)` dataclass; `handle_registration_request` now accepts it
- Exchange stores participant API level in `_participants: dict[int, APILevel]`
- Dual-layer enforcement: client-side `RuntimeError` in `DMAClient` base class + exchange-side `INSUFFICIENT_API_LEVEL` rejection in `_validate_request_participant`
- Add `NBBORequest` / `NBBOResponse` messages and `handle_nbbo_request` on Exchange (L1+)
- Depth requires L2+, transactions query requires L3
- Runner config changes from `num_participants` to per-level `ParticipantsConfig(L1, L2, L3)`
- Add `INSUFFICIENT_API_LEVEL` rejection reason
- Full capability inheritance tests for each API level

## v1.1.11 — Participant ID validation on query requests

- Add participant ID validation to all query request handlers (`handle_exchange_status_request`, `handle_depth_request`, `handle_order_query_request`, `handle_transactions_request`)
- Unify validation into `_validate_request_participant` helper method on Exchange
- Queries from unregistered participants are rejected with `UNREGISTERED_PARTICIPANT`

## v1.1.10 — Runner and config

- Add `RunnerConfig` and `PrintConfig` dataclasses in `runner/config.py` with `load_config()` for JSON parsing
- Add `Runner` class in `runner/runner.py`: creates Clock, Exchange, and N LocalDMAClients from config; replays a time-ordered CSV of order messages through the exchange with clock advancement
- Runner dispatches SUBMIT, MODIFY, and CANCEL actions to the correct client by participant ID
- Optional printing of new transactions and order book depth at configurable message intervals
- Runner accepts `output: IO[str]` parameter for testable output capture
- 20 new tests: 5 for config loading, 15 for runner behavior (setup, replay, printing)

## v1.1.9 — Query request/response symmetry

- Add request dataclasses to pair with each query response: `ExchangeStatusRequest`, `DepthRequest`, `OrderQueryRequest`, `TransactionsRequest` in `core/messages.py`
- Add `handle_*` methods on `Exchange` for each query type: `handle_exchange_status_request`, `handle_depth_request`, `handle_order_query_request`, `handle_transactions_request` — these unwrap the request, formulate the response, and return it
- Remove old `get_depth`, `get_order`, `get_transactions` methods from `Exchange` — all query communication now goes through the request/response handle methods
- `DMAClient` base class query methods now accept request objects and call the exchange's handle methods
- `LocalDMAClient` adds field-level query convenience methods: `query_exchange_status`, `query_depth`, `query_order`, `query_transactions`
- `OrderQueryResponse` construction moved from `DMAClient` to `Exchange.handle_order_query_request`

## v1.1.8 — DMA Client

- Add `DMAClient` ABC in `exchange/client/dma_client.py`: base class owns all exchange communication (calls exchange, stores `participant_id`, builds query responses), dispatches to abstract `_on_*` response callbacks that subclasses override
- Add `LocalDMAClient` in `exchange/client/local_dma_client.py`: externally controllable puppet with no-op callbacks; field-level convenience methods (`submit_order`, `modify_order`, `cancel_order`) for CSV-driven runner use; inherits `register` and query methods from base
- Single registration per client: `register()` raises `RuntimeError` on second call
- Base class sets `participant_id` on all outgoing `OrderMessageRequest`s
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
