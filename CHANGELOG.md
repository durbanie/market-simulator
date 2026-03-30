# Changelog

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
