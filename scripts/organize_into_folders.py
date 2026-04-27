#!/usr/bin/env python3
"""Bin Umbra topic notes into subfolders by their dominant tag.

For each note in the umbra output dir, picks the tag from its YAML `tags`
list that occurs the most across the whole collection. Notes whose chosen
tag has fewer than CUTOFF (default 3) members all collapse into `_misc/`.

Stem uniqueness is preserved by Phase 1, so [[wikilinks]] keep resolving
no matter which subfolder a note lives in.

Idempotent: re-running flattens what's there, recounts tags, re-bins.

Usage:
    python scripts/organize_into_folders.py <umbra_dir> [--cutoff N]
"""
from __future__ import annotations

import argparse
import re
import shutil
import sys
from collections import Counter
from pathlib import Path

import yaml

DEFAULT_CUTOFF = 3


def slugify_dir(s: str) -> str:
    s = s.lower().strip()
    s = re.sub(r"[^a-z0-9\s/_-]", "", s)
    s = re.sub(r"[\s/]+", "-", s)
    return s.strip("-_") or "_misc"


def load_tags(path: Path) -> list[str]:
    text = path.read_text(errors="replace")
    if not text.startswith("---"):
        return []
    end = text.find("---", 3)
    if end < 0:
        return []
    try:
        fm = yaml.safe_load(text[3:end]) or {}
    except yaml.YAMLError:
        return []
    raw = fm.get("tags") or []
    if not isinstance(raw, list):
        return []
    return [str(t).lower() for t in raw if t]


def flatten(root: Path) -> None:
    """Move every .md back to root and remove now-empty subfolders."""
    for md in list(root.rglob("*.md")):
        if md.parent == root:
            continue
        dest = root / md.name
        if dest.exists() and dest.resolve() != md.resolve():
            sys.stderr.write(f"WARN: collision flattening {md}\n")
            continue
        shutil.move(str(md), str(dest))
    for sub in sorted(root.iterdir(), reverse=True):
        if sub.is_dir():
            try:
                sub.rmdir()
            except OSError:
                pass


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("umbra_dir", type=Path)
    ap.add_argument("--cutoff", type=int, default=DEFAULT_CUTOFF,
                    help=f"min notes per folder (default {DEFAULT_CUTOFF}); "
                         "smaller bins collapse into _misc/")
    args = ap.parse_args(argv)

    root: Path = args.umbra_dir
    if not root.is_dir():
        sys.stderr.write(f"not a directory: {root}\n")
        return 1

    flatten(root)

    notes: list[tuple[Path, list[str]]] = []
    tag_counter: Counter[str] = Counter()
    for p in root.glob("*.md"):
        if p.name == "NOTE_INDEX.md":
            continue
        tags = load_tags(p)
        notes.append((p, tags))
        for t in tags:
            tag_counter[t] += 1

    chosen: dict[Path, str | None] = {}
    for p, tags in notes:
        chosen[p] = max(tags, key=lambda t: tag_counter[t]) if tags else None

    bin_counts: Counter[str] = Counter()
    for tag in chosen.values():
        bin_counts[slugify_dir(tag) if tag else "_misc"] += 1

    moved = 0
    for p, tag in chosen.items():
        folder = slugify_dir(tag) if tag else "_misc"
        if bin_counts[folder] < args.cutoff:
            folder = "_misc"
        dest_dir = root / folder
        dest_dir.mkdir(exist_ok=True)
        dest = dest_dir / p.name
        if dest.exists() and dest.resolve() == p.resolve():
            continue
        if dest.exists():
            sys.stderr.write(f"WARN: {dest} exists, skipping\n")
            continue
        shutil.move(str(p), str(dest))
        moved += 1

    final: Counter[str] = Counter()
    for sub in root.iterdir():
        if sub.is_dir():
            final[sub.name] = len(list(sub.glob("*.md")))

    print(f"moved {moved} notes into {len(final)} folders (cutoff={args.cutoff})")
    for name, n in sorted(final.items(), key=lambda x: (-x[1], x[0])):
        print(f"  {n:>3}  {name}/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
