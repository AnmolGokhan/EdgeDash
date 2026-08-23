"""Manual rescore escape hatch for intentionally re-running scoring."""

from __future__ import annotations

import argparse
import edgedash.storage as storage
from edgedash.config import load_config


def _confirm_all() -> bool:
    try:
        answer = input("Type 'RESET ALL SCORES' to continue: ").strip()
    except EOFError:
        print("Confirmation declined.")
        return False
    return answer == "RESET ALL SCORES"


def main() -> None:
    parser = argparse.ArgumentParser(description="Manually clear listing scores without deleting extraction cache.")
    parser.add_argument("--all", action="store_true", help="clear every listing score")
    parser.add_argument("--id", dest="listing_id", help="clear one listing's score by listing id")
    args = parser.parse_args()

    if args.all and args.listing_id:
        raise SystemExit("Choose either --all or --id, not both.")
    if not args.all and not args.listing_id:
        raise SystemExit("Pass either --all or --id <listing_id>.")

    cfg = load_config()
    storage.init_db(cfg.db_path)

    if args.all:
        if not _confirm_all():
            print("Aborted. No scores were cleared.")
            raise SystemExit(0)
        cleared = storage.clear_listing_scores(cfg.db_path)
        print(f"Cleared {cleared} scores. Extraction cache preserved. Run the cycle to re-score.")
        raise SystemExit(0)

    cleared = storage.clear_listing_scores(cfg.db_path, args.listing_id)
    print(f"Cleared {cleared} score(s) for listing {args.listing_id}. Extraction cache preserved. Run the cycle to re-score.")


if __name__ == "__main__":
    main()
