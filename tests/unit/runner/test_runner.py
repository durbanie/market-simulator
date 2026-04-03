"""Tests for the Runner: CSV replay through an exchange."""

import io

import pytest
from decimal import Decimal

from market_simulator.core.clock import ClockMode
from market_simulator.core.exchange_enums import (
    OrderStatus,
    RequestStatus,
)
from market_simulator.core.messages import (
    DepthRequest,
    TransactionsRequest,
)
from market_simulator.exchange.exchange import ExchangeConfig
from market_simulator.runner.config import PrintConfig, RunnerConfig
from market_simulator.runner.runner import Runner


CSV_HEADER = "timestamp,action,participant_id,instrument,side,order_type,price,quantity,order_id"


def _write_csv(tmp_path, rows: list[str]) -> str:
    """Write a CSV file and return its path."""
    content = CSV_HEADER + "\n" + "\n".join(rows) + "\n"
    path = tmp_path / "orders.csv"
    path.write_text(content)
    return str(path)


def _make_config(csv_path: str, **overrides) -> RunnerConfig:
    """Build a RunnerConfig with sensible defaults."""
    return RunnerConfig(
        csv_path=csv_path,
        clock_mode=overrides.get("clock_mode", ClockMode.FAST_SIMULATION),
        exchange=overrides.get(
            "exchange",
            ExchangeConfig(instruments=["XYZ"]),
        ),
        num_participants=overrides.get("num_participants", 2),
        print_config=overrides.get("print_config", PrintConfig()),
    )


class TestRunnerSetup:

    def test_creates_exchange_and_clients(self, tmp_path) -> None:
        csv_path = _write_csv(tmp_path, [])
        config = _make_config(csv_path, num_participants=3)
        runner = Runner(config)

        assert len(runner.clients) == 3
        assert runner.exchange is not None
        # Participant IDs should be sequential starting from 1.
        assert sorted(runner.clients.keys()) == [1, 2, 3]

    def test_opens_and_closes_exchange(self, tmp_path) -> None:
        csv_path = _write_csv(tmp_path, [])
        runner = Runner(_make_config(csv_path))

        assert runner.exchange.is_open is False
        runner.run()
        assert runner.exchange.is_open is False

    def test_exchange_open_during_run(self, tmp_path) -> None:
        """Exchange is open while processing rows."""
        rows = [
            "1000,SUBMIT,1,XYZ,BUY,LIMIT,100,10,",
        ]
        csv_path = _write_csv(tmp_path, rows)
        runner = Runner(_make_config(csv_path))
        runner.run()

        # If the exchange were closed during run, the submit would be
        # rejected. Verify it was accepted by querying the order.
        order = runner.exchange._find_order(1)
        assert order is not None
        assert order.status == OrderStatus.ACCEPTED


class TestRunnerReplay:

    def test_submit_orders(self, tmp_path) -> None:
        rows = [
            "1000,SUBMIT,1,XYZ,BUY,LIMIT,100,10,",
            "2000,SUBMIT,2,XYZ,SELL,LIMIT,105,5,",
        ]
        csv_path = _write_csv(tmp_path, rows)
        runner = Runner(_make_config(csv_path))
        runner.run()

        order1 = runner.exchange._find_order(1)
        order2 = runner.exchange._find_order(2)
        assert order1 is not None
        assert order2 is not None
        assert order1.price == Decimal("100")
        assert order2.price == Decimal("105")

    def test_modify_order(self, tmp_path) -> None:
        rows = [
            "1000,SUBMIT,1,XYZ,BUY,LIMIT,100,10,",
            "2000,MODIFY,1,XYZ,,,105,10,1",
        ]
        csv_path = _write_csv(tmp_path, rows)
        runner = Runner(_make_config(csv_path))
        runner.run()

        order = runner.exchange._find_order(1)
        assert order is not None
        assert order.price == Decimal("105")

    def test_cancel_order(self, tmp_path) -> None:
        rows = [
            "1000,SUBMIT,1,XYZ,BUY,LIMIT,100,10,",
            "2000,CANCEL,1,XYZ,,,,, 1",
        ]
        csv_path = _write_csv(tmp_path, rows)
        runner = Runner(_make_config(csv_path))
        runner.run()

        order = runner.exchange._find_order(1)
        assert order is not None
        assert order.status == OrderStatus.CANCELLED

    def test_clock_advances(self, tmp_path) -> None:
        rows = [
            "1000,SUBMIT,1,XYZ,BUY,LIMIT,100,10,",
            "5000,SUBMIT,2,XYZ,SELL,LIMIT,200,5,",
        ]
        csv_path = _write_csv(tmp_path, rows)
        runner = Runner(_make_config(csv_path))
        runner.run()

        assert runner.clock.now() == 5000

    def test_crossing_orders_produce_transaction(self, tmp_path) -> None:
        rows = [
            "1000,SUBMIT,1,XYZ,SELL,LIMIT,50,5,",
            "2000,SUBMIT,2,XYZ,BUY,MARKET,,5,",
        ]
        csv_path = _write_csv(tmp_path, rows)
        runner = Runner(_make_config(csv_path))
        runner.run()

        resp = runner.exchange.handle_transactions_request(
            TransactionsRequest(participant_id=0),
        )
        assert len(resp.transactions) == 1
        assert resp.transactions[0].price == Decimal("50")
        assert resp.transactions[0].quantity == Decimal("5")

    def test_multiple_participants(self, tmp_path) -> None:
        rows = [
            "1000,SUBMIT,1,XYZ,BUY,LIMIT,100,10,",
            "2000,SUBMIT,2,XYZ,SELL,LIMIT,200,5,",
        ]
        csv_path = _write_csv(tmp_path, rows)
        runner = Runner(_make_config(csv_path))
        runner.run()

        order1 = runner.exchange._find_order(1)
        order2 = runner.exchange._find_order(2)
        assert order1.participant_id == 1
        assert order2.participant_id == 2

    def test_unknown_participant_raises(self, tmp_path) -> None:
        rows = [
            "1000,SUBMIT,99,XYZ,BUY,LIMIT,100,10,",
        ]
        csv_path = _write_csv(tmp_path, rows)
        runner = Runner(_make_config(csv_path, num_participants=2))

        with pytest.raises(ValueError, match="Unknown participant_id 99"):
            runner.run()

    def test_market_order_empty_price(self, tmp_path) -> None:
        rows = [
            "1000,SUBMIT,1,XYZ,SELL,LIMIT,50,5,",
            "2000,SUBMIT,2,XYZ,BUY,MARKET,,5,",
        ]
        csv_path = _write_csv(tmp_path, rows)
        runner = Runner(_make_config(csv_path))
        runner.run()

        resp = runner.exchange.handle_transactions_request(
            TransactionsRequest(participant_id=0),
        )
        assert len(resp.transactions) == 1

    def test_empty_csv(self, tmp_path) -> None:
        csv_path = _write_csv(tmp_path, [])
        runner = Runner(_make_config(csv_path))
        runner.run()

        assert runner.exchange.is_open is False


class TestRunnerPrinting:

    def test_print_transactions(self, tmp_path) -> None:
        rows = [
            "1000,SUBMIT,1,XYZ,SELL,LIMIT,50,5,",
            "2000,SUBMIT,2,XYZ,BUY,MARKET,,5,",
        ]
        csv_path = _write_csv(tmp_path, rows)
        config = _make_config(
            csv_path,
            print_config=PrintConfig(transactions_every_n=2),
        )
        output = io.StringIO()
        runner = Runner(config, output=output)
        runner.run()

        text = output.getvalue()
        assert "Transactions" in text
        assert "price=50" in text
        assert "qty=5" in text

    def test_print_depth(self, tmp_path) -> None:
        rows = [
            "1000,SUBMIT,1,XYZ,BUY,LIMIT,100,10,",
            "2000,SUBMIT,2,XYZ,SELL,LIMIT,200,5,",
            "3000,SUBMIT,1,XYZ,BUY,LIMIT,99,3,",
        ]
        csv_path = _write_csv(tmp_path, rows)
        config = _make_config(
            csv_path,
            print_config=PrintConfig(depth_every_n=3),
        )
        output = io.StringIO()
        runner = Runner(config, output=output)
        runner.run()

        text = output.getvalue()
        assert "Depth" in text
        assert "bid" in text
        assert "ask" in text

    def test_depth_asks_printed_highest_first(self, tmp_path) -> None:
        rows = [
            "1000,SUBMIT,1,XYZ,SELL,LIMIT,200,5,",
            "2000,SUBMIT,2,XYZ,SELL,LIMIT,300,3,",
            "3000,SUBMIT,1,XYZ,BUY,LIMIT,100,10,",
        ]
        csv_path = _write_csv(tmp_path, rows)
        config = _make_config(
            csv_path,
            print_config=PrintConfig(depth_every_n=3),
        )
        output = io.StringIO()
        runner = Runner(config, output=output)
        runner.run()

        lines = output.getvalue().splitlines()
        ask_lines = [l for l in lines if l.strip().startswith("ask")]
        assert len(ask_lines) == 2
        # Highest ask should appear first.
        assert "300" in ask_lines[0]
        assert "200" in ask_lines[1]

    def test_depth_volume_and_depth_columns(self, tmp_path) -> None:
        rows = [
            "1000,SUBMIT,1,XYZ,BUY,LIMIT,100,10,",
            "2000,SUBMIT,2,XYZ,BUY,LIMIT,99,5,",
            "3000,SUBMIT,1,XYZ,SELL,LIMIT,200,3,",
        ]
        csv_path = _write_csv(tmp_path, rows)
        config = _make_config(
            csv_path,
            print_config=PrintConfig(depth_every_n=3),
        )
        output = io.StringIO()
        runner = Runner(config, output=output)
        runner.run()

        lines = output.getvalue().splitlines()
        # Header row should contain volume and depth.
        header = [l for l in lines if "volume" in l and "depth" in l]
        assert len(header) == 1

        bid_lines = [l for l in lines if l.strip().startswith("bid")]
        # Best bid (100, qty=10): volume=10, depth=10.
        assert "10" in bid_lines[0]
        # Second bid (99, qty=5): volume=5, depth=15.
        parts = bid_lines[1].split()
        assert parts[-2] == "5"   # volume
        assert parts[-1] == "15"  # cumulative depth

    def test_depth_last_txn_price_shown(self, tmp_path) -> None:
        rows = [
            "1000,SUBMIT,1,XYZ,SELL,LIMIT,50,5,",
            "2000,SUBMIT,2,XYZ,BUY,MARKET,,5,",
            "3000,SUBMIT,1,XYZ,SELL,LIMIT,60,5,",
        ]
        csv_path = _write_csv(tmp_path, rows)
        config = _make_config(
            csv_path,
            print_config=PrintConfig(depth_every_n=3),
        )
        output = io.StringIO()
        runner = Runner(config, output=output)
        runner.run()

        text = output.getvalue()
        assert "last txn price: 50" in text

    def test_depth_last_txn_price_none_when_no_transactions(self, tmp_path) -> None:
        rows = [
            "1000,SUBMIT,1,XYZ,BUY,LIMIT,100,10,",
            "2000,SUBMIT,2,XYZ,SELL,LIMIT,200,5,",
            "3000,SUBMIT,1,XYZ,BUY,LIMIT,99,3,",
        ]
        csv_path = _write_csv(tmp_path, rows)
        config = _make_config(
            csv_path,
            print_config=PrintConfig(depth_every_n=3),
        )
        output = io.StringIO()
        runner = Runner(config, output=output)
        runner.run()

        text = output.getvalue()
        assert "last txn price: (none)" in text

    def test_no_print_when_disabled(self, tmp_path) -> None:
        rows = [
            "1000,SUBMIT,1,XYZ,BUY,LIMIT,100,10,",
        ]
        csv_path = _write_csv(tmp_path, rows)
        config = _make_config(csv_path)
        output = io.StringIO()
        runner = Runner(config, output=output)
        runner.run()

        assert output.getvalue() == ""
