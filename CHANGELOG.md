# Changelog

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
