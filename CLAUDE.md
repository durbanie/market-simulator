# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Market simulator: a stochastic model of asset markets with individual participants making buy/sell decisions. `DESIGNDOC.md` is the single source of truth for all architecture and design decisions. Always read it before starting new features or making architectural decisions. Do not amend `DESIGNDOC.md` without consulting the user. If an architectural decision conflicts with `DESIGNDOC.md`, consult the user first and update the design doc before implementing the change.

## Build & Test Commands

```bash
# Install dependencies (once pyproject.toml is set up)
pip install -e ".[dev]"

# Run all tests
pytest

# Run a single test file
pytest tests/unit/test_exchange.py

# Run a specific test
pytest tests/unit/test_exchange.py::test_limit_order_matching -v

# Run with coverage
pytest --cov=market_simulator
```

## Development Workflow

- **Branching**: `feat/short-description` or `fix/short-description`. Always `git checkout main && git pull` before creating a new branch
- **Versioning**: `vX.Y.Z` — major = phase, minor = iteration (0 = pre-iteration setup), micro = PR
- **PRs**: One logical change per PR. Include version bump in `CHANGELOG.md`
- **PR description format**:
  ```
  <branch name> - <one sentence description>

  <bullet points describing changes>
  ```
- **New packages**: Flag in PR description; ideally decide at planning time
- **Architectural decisions**: Stop and ask before making decisions beyond the scope of the task

## Code Style

- Python: [Google Python Style Guide](https://google.github.io/styleguide/pyguide.html)
- Prefer readable over concise-but-cryptic unless performance-critical
- Enums use all-caps constant values (e.g., `BUY`, `SELL`, `LIMIT`, `MARKET`)
- IDs: integers. Timestamps: integer microseconds from Unix epoch
- Prices: `Decimal` in USD. Quantities: `Decimal` (min tick 0.0001)

## Testing

- pytest for both unit and integration tests
- Target 95-100% unit test coverage
- Test behavior, not implementation — avoid brittle tests
- Integration tests use JSON configs + CSV input/output in `tests/fixtures/`
- All tests must pass before merging to `main`

