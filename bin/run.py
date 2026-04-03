"""Run a simulation from a JSON config file.

Usage:
    python scripts/run.py configs/simple_run.json
"""

import sys

from market_simulator.runner.config import load_config
from market_simulator.runner.runner import Runner


def main() -> None:
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} <config.json>", file=sys.stderr)
        sys.exit(1)

    config = load_config(sys.argv[1])
    runner = Runner(config)
    runner.run()


if __name__ == "__main__":
    main()
