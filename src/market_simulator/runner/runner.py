"""Runner: replays a CSV of order messages through an exchange."""

import csv
import sys
from decimal import Decimal
from typing import IO

from market_simulator.core.clock import Clock
from market_simulator.core.exchange_enums import Action, OrderType, Side
from market_simulator.exchange.client.local_dma_client import LocalDMAClient
from market_simulator.exchange.exchange import Exchange
from market_simulator.runner.config import RunnerConfig


class Runner:
    """Replays a time-ordered CSV of order messages through an exchange.

    Creates the clock, exchange, and DMA clients from configuration.
    The ``run`` method opens the exchange, processes every CSV row,
    then closes the exchange.

    Args:
        config: Runner configuration.
        output: Writable stream for optional printing. Defaults to stdout.
    """

    def __init__(
        self,
        config: RunnerConfig,
        output: IO[str] = sys.stdout,
    ) -> None:
        self._config = config
        self._output = output

        self._clock = Clock(
            mode=config.clock_mode,
            offset_us=config.clock_offset_us,
        )
        self._exchange = Exchange(config.exchange, self._clock)

        self._clients: dict[int, LocalDMAClient] = {}
        for _ in range(config.num_participants):
            client = LocalDMAClient(self._exchange)
            resp = client.register()
            self._clients[resp.participant_id] = client

        self._message_count = 0
        self._last_txn_printed = 0

    @property
    def clock(self) -> Clock:
        """The simulation clock."""
        return self._clock

    @property
    def exchange(self) -> Exchange:
        """The exchange instance."""
        return self._exchange

    @property
    def clients(self) -> dict[int, LocalDMAClient]:
        """Registered clients keyed by participant ID."""
        return self._clients

    def run(self) -> None:
        """Open the exchange, replay the CSV, then close."""
        self._exchange.open()

        with open(self._config.csv_path, newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                timestamp = int(row["timestamp"])
                self._clock.fast_forward(timestamp)
                self._process_row(row)

        self._exchange.close()

    def _process_row(self, row: dict[str, str]) -> None:
        """Parse a CSV row and dispatch to the appropriate client."""
        participant_id = int(row["participant_id"])
        client = self._clients.get(participant_id)
        if client is None:
            raise ValueError(
                f"Unknown participant_id {participant_id}. "
                f"Registered: {sorted(self._clients.keys())}",
            )

        action = Action(row["action"])

        if action == Action.SUBMIT:
            price_str = row.get("price", "")
            client.submit_order(
                instrument=row["instrument"],
                side=Side(row["side"]),
                order_type=OrderType(row["order_type"]),
                quantity=Decimal(row["quantity"]),
                price=Decimal(price_str) if price_str else None,
            )
        elif action == Action.MODIFY:
            price_str = row.get("price", "")
            client.modify_order(
                order_id=int(row["order_id"]),
                quantity=Decimal(row["quantity"]),
                price=Decimal(price_str) if price_str else None,
                instrument=row.get("instrument") or None,
            )
        elif action == Action.CANCEL:
            client.cancel_order(
                order_id=int(row["order_id"]),
                instrument=row.get("instrument") or None,
            )

        self._message_count += 1
        self._maybe_print()

    def _maybe_print(self) -> None:
        """Print transactions and/or depth if configured intervals hit."""
        pc = self._config.print_config

        if pc.transactions_every_n > 0:
            if self._message_count % pc.transactions_every_n == 0:
                self._print_transactions()

        if pc.depth_every_n > 0:
            if self._message_count % pc.depth_every_n == 0:
                self._print_depth()

    def _print_transactions(self) -> None:
        """Print transactions added since the last print."""
        from market_simulator.core.messages import TransactionsRequest

        resp = self._exchange.handle_transactions_request(
            TransactionsRequest(participant_id=0),
        )
        new_txns = resp.transactions[self._last_txn_printed:]
        if new_txns:
            self._output.write(f"--- Transactions (message {self._message_count}) ---\n")
            for txn in new_txns:
                self._output.write(
                    f"  txn={txn.transaction_id} {txn.instrument} "
                    f"price={txn.price} qty={txn.quantity}\n",
                )
            self._last_txn_printed = len(resp.transactions)

    def _print_depth(self) -> None:
        """Print order book depth for configured instruments."""
        from market_simulator.core.messages import DepthRequest

        pc = self._config.print_config
        instruments = (
            pc.depth_instruments
            if pc.depth_instruments is not None
            else self._config.exchange.instruments
        )

        self._output.write(f"--- Depth (message {self._message_count}) ---\n")
        for instrument in instruments:
            resp = self._exchange.handle_depth_request(
                DepthRequest(
                    participant_id=0,
                    instrument=instrument,
                    levels=pc.depth_levels,
                ),
            )
            self._output.write(f"  {instrument}:\n")
            if resp.levels is None:
                self._output.write("    (unknown instrument)\n")
                continue
            for side_label in ("asks", "bids"):
                entries = resp.levels.get(side_label, [])
                if entries:
                    for price, qty in entries:
                        self._output.write(
                            f"    {side_label}: price={price} qty={qty}\n",
                        )
                else:
                    self._output.write(f"    {side_label}: (empty)\n")
