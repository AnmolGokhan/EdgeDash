"""Entry point — run one full EdgeDash cycle.

Usage:
    python run_cycle.py [--dry-run] [--force AGENT]... [--explain]
"""

import argparse

from edgedash.config import load_config
from edgedash.orchestrator import run_cycle


def main() -> None:
    parser = argparse.ArgumentParser(description="Run an EdgeDash cycle.")
    parser.add_argument("--dry-run", action="store_true", help="print the plan without executing or writing")
    parser.add_argument("--force", action="append", default=[], metavar="AGENT", help="force a named planned agent")
    parser.add_argument("--explain", action="store_true", help="print every state value and its decision")
    args = parser.parse_args()
    config = load_config()
    run_cycle(config, dry_run=args.dry_run, force=args.force, explain=args.explain)


if __name__ == "__main__":
    main()
