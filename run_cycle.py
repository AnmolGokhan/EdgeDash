"""Entry point — run one full EdgeDash cycle.

Usage:
    python run_cycle.py
"""

from edgedash.config import load_config
from edgedash.orchestrator import run_cycle


def main() -> None:
    config = load_config()
    run_cycle(config)


if __name__ == "__main__":
    main()
