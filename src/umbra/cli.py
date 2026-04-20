"""Unified CLI: `umbra <phase|all> [args]`."""

from __future__ import annotations

import argparse
import sys

from . import daily_splitter, keyword_linker, semantic_backlinks, synonym_linker


def main():
    parser = argparse.ArgumentParser(
        prog="umbra",
        description="Obsidian Umbra — local LLM-powered Zettelkasten pipeline",
    )
    parser.add_argument(
        "phase",
        choices=["split", "semantic", "keywords", "synonyms", "all"],
        help="Which phase to run (or 'all' for the full pipeline)",
    )
    parser.add_argument("--config", type=str, default=None)
    args, extra = parser.parse_known_args()

    base = []
    if args.config:
        base = ["--config", args.config]

    if args.phase == "split":
        sys.exit(daily_splitter.main(base + extra))
    if args.phase == "semantic":
        sys.exit(semantic_backlinks.main(base + extra))
    if args.phase == "keywords":
        sys.exit(keyword_linker.main(base + extra))
    if args.phase == "synonyms":
        sys.exit(synonym_linker.main(base + extra))
    if args.phase == "all":
        for mod in (daily_splitter, semantic_backlinks,
                    keyword_linker, synonym_linker):
            rc = mod.main(base)
            if rc not in (0, 2):
                sys.exit(rc)
        sys.exit(0)


if __name__ == "__main__":
    main()
