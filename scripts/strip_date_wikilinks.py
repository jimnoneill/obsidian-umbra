#!/usr/bin/env python3
"""One-shot cleanup: strip [[MM-DD-YYYY]] wikilinks from Umbra topic notes.

Rewrites in-place:
  - `sources:` YAML list items `'[[05-05-2023]]'` → `'05-05-2023'`
  - Body `> First entry: [[daily]] · DATE` → `> First entry: DATE`
  - Body `> Source: [[daily]]` lines → removed
Leaves all other content untouched.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

DAILY_RE = re.compile(r"^\d{2}-\d{2}-\d{4}$|^\d{4}-\d{2}-\d{2}$")
WIKI_DATE = re.compile(r"\[\[(\d{2}-\d{2}-\d{4}|\d{4}-\d{2}-\d{2})\]\]")
FIRST_ENTRY = re.compile(
    r"^>\s*First entry:\s*\[\[(\d{2}-\d{2}-\d{4}|\d{4}-\d{2}-\d{2})\]\]\s*·\s*(\S+)\s*$",
    re.MULTILINE,
)
SOURCE_LINE = re.compile(
    r"^>\s*Source:\s*\[\[(?:\d{2}-\d{2}-\d{4}|\d{4}-\d{2}-\d{2})\]\]\s*\n\n?",
    re.MULTILINE,
)
FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n", re.DOTALL)


def clean_file(path: Path) -> bool:
    text = path.read_text()
    orig = text

    m = FRONTMATTER_RE.match(text)
    if m:
        fm_raw = m.group(1)
        fm_new = WIKI_DATE.sub(r"\1", fm_raw)
        if fm_new != fm_raw:
            text = f"---\n{fm_new}\n---\n" + text[m.end():]

    text = FIRST_ENTRY.sub(r"> First entry: \1", text)
    text = SOURCE_LINE.sub("", text)

    if text != orig:
        path.write_text(text)
        return True
    return False


def main():
    if len(sys.argv) != 2:
        print("usage: strip_date_wikilinks.py <umbra_dir>")
        sys.exit(1)
    root = Path(sys.argv[1])
    files = sorted(p for p in root.glob("*.md") if p.name != "NOTE_INDEX.md")
    changed = 0
    for p in files:
        if clean_file(p):
            changed += 1
    print(f"scanned {len(files)}, rewrote {changed}")


if __name__ == "__main__":
    main()
