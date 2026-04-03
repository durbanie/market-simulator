"""Runner configuration: dataclasses and JSON loading."""

import json
from dataclasses import dataclass, field
from decimal import Decimal

from market_simulator.core.clock import ClockMode
from market_simulator.exchange.exchange import ExchangeConfig


@dataclass
class PrintConfig:
    """Controls optional output during a simulation run.

    Attributes:
        transactions_every_n: Print new transactions every N messages.
            0 disables.
        depth_every_n: Print order book depth every N messages.
            0 disables.
        depth_instruments: Instruments to print depth for. None means
            all exchange instruments.
        depth_levels: Number of price levels per side to print.
    """
    transactions_every_n: int = 0
    depth_every_n: int = 0
    depth_instruments: list[str] | None = None
    depth_levels: int = 5


@dataclass
class RunnerConfig:
    """Top-level configuration for a simulation run.

    Attributes:
        csv_path: Path to the time-ordered CSV of order messages.
        clock_mode: Clock operating mode.
        clock_offset_us: Initial clock offset in microseconds.
        exchange: Exchange configuration.
        num_participants: Number of DMA clients to register.
        print_config: Output configuration.
    """
    csv_path: str
    clock_mode: ClockMode = ClockMode.FAST_SIMULATION
    clock_offset_us: int = 0
    exchange: ExchangeConfig = field(
        default_factory=lambda: ExchangeConfig(instruments=["XYZ"]),
    )
    num_participants: int = 1
    print_config: PrintConfig = field(default_factory=PrintConfig)


def load_config(path: str) -> RunnerConfig:
    """Load a JSON config file and return a RunnerConfig.

    Missing keys use dataclass defaults. The ``exchange`` section
    converts string fee values to ``Decimal``.
    """
    with open(path) as f:
        data = json.load(f)

    clock_section = data.get("clock", {})
    clock_mode = ClockMode(clock_section.get("mode", "FAST_SIMULATION"))
    clock_offset_us = clock_section.get("offset_us", 0)

    exchange_section = data.get("exchange", {})
    exchange_config = ExchangeConfig(
        instruments=exchange_section.get("instruments", ["XYZ"]),
        maker_fee_bps=Decimal(
            str(exchange_section.get("maker_fee_bps", "-3")),
        ),
        taker_fee_bps=Decimal(
            str(exchange_section.get("taker_fee_bps", "7")),
        ),
        starting_order_id=exchange_section.get("starting_order_id", 1),
        starting_transaction_id=exchange_section.get(
            "starting_transaction_id", 1,
        ),
        starting_participant_id=exchange_section.get(
            "starting_participant_id", 1,
        ),
    )

    participants_section = data.get("participants", {})
    num_participants = participants_section.get("num_participants", 1)

    print_section = data.get("print", {})
    print_config = PrintConfig(
        transactions_every_n=print_section.get("transactions_every_n", 0),
        depth_every_n=print_section.get("depth_every_n", 0),
        depth_instruments=print_section.get("depth_instruments"),
        depth_levels=print_section.get("depth_levels", 5),
    )

    return RunnerConfig(
        csv_path=data["csv_path"],
        clock_mode=clock_mode,
        clock_offset_us=clock_offset_us,
        exchange=exchange_config,
        num_participants=num_participants,
        print_config=print_config,
    )
