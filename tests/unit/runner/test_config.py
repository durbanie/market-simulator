"""Tests for runner configuration loading."""

import json
from decimal import Decimal

import pytest

from market_simulator.core.clock import ClockMode
from market_simulator.runner.config import PrintConfig, RunnerConfig, load_config


class TestLoadConfig:

    def test_full_config(self, tmp_path) -> None:
        """All fields map correctly from JSON."""
        cfg = {
            "csv_path": "/data/orders.csv",
            "clock": {"mode": "REAL_TIME_SIMULATION", "offset_us": 5000},
            "exchange": {
                "instruments": ["ABC", "DEF"],
                "maker_fee_bps": "-2",
                "taker_fee_bps": "5",
                "starting_order_id": 100,
                "starting_transaction_id": 200,
                "starting_participant_id": 10,
            },
            "participants": {"num_participants": 50},
            "print": {
                "transactions_every_n": 10,
                "depth_every_n": 20,
                "depth_instruments": ["ABC"],
                "depth_levels": 3,
            },
        }
        path = tmp_path / "config.json"
        path.write_text(json.dumps(cfg))

        rc = load_config(str(path))

        assert rc.csv_path == "/data/orders.csv"
        assert rc.clock_mode == ClockMode.REAL_TIME_SIMULATION
        assert rc.clock_offset_us == 5000
        assert rc.exchange.instruments == ["ABC", "DEF"]
        assert rc.exchange.maker_fee_bps == Decimal("-2")
        assert rc.exchange.taker_fee_bps == Decimal("5")
        assert rc.exchange.starting_order_id == 100
        assert rc.exchange.starting_transaction_id == 200
        assert rc.exchange.starting_participant_id == 10
        assert rc.num_participants == 50
        assert rc.print_config.transactions_every_n == 10
        assert rc.print_config.depth_every_n == 20
        assert rc.print_config.depth_instruments == ["ABC"]
        assert rc.print_config.depth_levels == 3

    def test_minimal_config(self, tmp_path) -> None:
        """Only required fields; defaults apply."""
        cfg = {
            "csv_path": "orders.csv",
            "exchange": {"instruments": ["XYZ"]},
        }
        path = tmp_path / "config.json"
        path.write_text(json.dumps(cfg))

        rc = load_config(str(path))

        assert rc.csv_path == "orders.csv"
        assert rc.clock_mode == ClockMode.FAST_SIMULATION
        assert rc.clock_offset_us == 0
        assert rc.exchange.instruments == ["XYZ"]
        assert rc.exchange.maker_fee_bps == Decimal("-3")
        assert rc.exchange.taker_fee_bps == Decimal("7")
        assert rc.num_participants == 1
        assert rc.print_config.transactions_every_n == 0
        assert rc.print_config.depth_every_n == 0
        assert rc.print_config.depth_instruments is None
        assert rc.print_config.depth_levels == 5

    def test_decimal_fees(self, tmp_path) -> None:
        """Fee string values are converted to Decimal."""
        cfg = {
            "csv_path": "orders.csv",
            "exchange": {
                "instruments": ["XYZ"],
                "maker_fee_bps": "-1.5",
                "taker_fee_bps": "3.25",
            },
        }
        path = tmp_path / "config.json"
        path.write_text(json.dumps(cfg))

        rc = load_config(str(path))

        assert rc.exchange.maker_fee_bps == Decimal("-1.5")
        assert rc.exchange.taker_fee_bps == Decimal("3.25")

    def test_missing_file_raises(self) -> None:
        with pytest.raises(FileNotFoundError):
            load_config("/nonexistent/config.json")

    def test_invalid_json_raises(self, tmp_path) -> None:
        path = tmp_path / "bad.json"
        path.write_text("not json")

        with pytest.raises(json.JSONDecodeError):
            load_config(str(path))
