"""Shared helpers for all phases."""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

# Daily-note patterns
DAILY_ISO = re.compile(r"^\d{4}-\d{2}-\d{2}$")        # YYYY-MM-DD
DAILY_US = re.compile(r"^\d{2}-\d{2}-\d{4}$")         # MM-DD-YYYY

# Markers used to safely regenerate sections
MARKER_TOPICS = "<!-- umbra: generated topic links -->"
MARKER_RELATED = "<!-- umbra: related notes -->"
MARKER_SYNONYMS = "<!-- umbra: synonyms -->"


def log_line(log_file: Path, msg: str) -> None:
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    log_file.parent.mkdir(parents=True, exist_ok=True)
    with open(log_file, "a") as f:
        f.write(line + "\n")


def parse_daily_date(stem: str) -> str | None:
    m = DAILY_ISO.match(stem)
    if m:
        return stem
    m = DAILY_US.match(stem)
    if m:
        mo, da, yr = stem.split("-")
        return f"{yr}-{mo}-{da}"
    return None


def is_daily_note(path: Path) -> bool:
    if not path.is_file() or path.suffix != ".md":
        return False
    if "template" in str(path).lower():
        return False
    return parse_daily_date(path.stem) is not None


def should_skip(path: Path, vault: Path, skip_dirs: list[str]) -> bool:
    try:
        rel = path.relative_to(vault)
    except ValueError:
        return True
    return any(part in skip_dirs for part in rel.parts)


def slugify(s: str) -> str:
    s = s.lower().strip()
    s = re.sub(r"[^a-z0-9\s-]", "", s)
    s = re.sub(r"[\s-]+", "-", s)
    return s.strip("-")[:60] or "topic"


def camel_to_words(s: str) -> str:
    spaced = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", s)
    spaced = re.sub(r"(?<=[A-Z])(?=[A-Z][a-z])", " ", spaced)
    return spaced.lower()
