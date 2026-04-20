#!/usr/bin/env python3
"""Phase 3 — Keyword Linker.

Builds a keyword→note index from non-daily note stems, titles, and folder
names. Injects inline [[wikilinks]] wherever keywords appear in note body
text. Folder/category-aware. No LLM needed — pure keyword matching.

Protected regions: YAML frontmatter, code blocks, existing links, URLs,
HTML comments, markdown headings. Per-note convergence loop handles
position shifts from link injection.
"""

from __future__ import annotations

import argparse
import re
import sys
from collections import defaultdict
from pathlib import Path

import yaml

from .common import (
    MARKER_RELATED, MARKER_SYNONYMS, MARKER_TOPICS,
    camel_to_words, is_daily_note, log_line, should_skip,
)
from .config import Config, load_config


STOP_WORDS = {
    "the", "and", "but", "for", "with", "this", "that", "from", "have",
    "been", "will", "done", "need", "todo", "note", "notes", "make",
    "also", "just", "some", "more", "like", "then", "than", "what",
    "when", "where", "here", "there", "about", "after", "before",
    "should", "would", "could", "their", "them", "they", "each",
    "only", "into", "over", "under", "between", "through", "these",
    "those", "very", "much", "many", "most", "other", "same", "such",
    "well", "back", "still", "even", "going", "want", "look",
    "readme", "untitled", "cursor_prompt", "codebase",
}


def is_specific_keyword(keyword: str) -> bool:
    """Single-word keywords must be specific enough — not common English."""
    kl = keyword.lower().strip()
    if " " in kl:
        return True
    if keyword.isupper() and len(keyword) >= 3:
        return True
    if any(c.isdigit() for c in keyword):
        return True
    if keyword != keyword.lower() and keyword != keyword.upper():
        return True
    if "_" in keyword or "-" in keyword:
        return True
    return False


class LinkTarget:
    __slots__ = ("stem", "title", "category", "keywords")

    def __init__(self, stem, title, category):
        self.stem = stem
        self.title = title
        self.category = category
        self.keywords: list[str] = []


def get_note_title(text: str, stem: str) -> str:
    if text.startswith("---"):
        end = text.find("---", 3)
        if end > 0:
            try:
                fm = yaml.safe_load(text[3:end])
                if isinstance(fm, dict) and fm.get("title"):
                    return str(fm["title"])
            except yaml.YAMLError:
                pass
    h1 = re.search(r"^#\s+(.+)$", text, re.MULTILINE)
    return h1.group(1).strip() if h1 else stem


def build_keyword_index(cfg: Config) -> tuple[dict, list]:
    kw: dict[str, LinkTarget] = {}
    targets: list[LinkTarget] = []

    def register(keyword: str, target: LinkTarget):
        kl = keyword.lower().strip()
        if (len(kl) < cfg.min_keyword_len or kl in STOP_WORDS
                or kl.isdigit() or not is_specific_keyword(keyword)):
            return
        existing = kw.get(kl)
        if existing is None or len(target.stem) > len(existing.stem):
            kw[kl] = target
            target.keywords.append(kl)

    for path in sorted(cfg.vault.rglob("*.md")):
        if should_skip(path, cfg.vault, cfg.skip_dirs):
            continue
        if path.name in cfg.skip_files:
            continue
        stem = path.stem
        if is_daily_note(path):
            continue
        if len(stem) < cfg.min_keyword_len:
            continue

        try:
            rel = path.relative_to(cfg.vault)
            category = str(rel.parent) if rel.parent != Path(".") else ""
        except ValueError:
            category = ""
        try:
            text = path.read_text(errors="replace")[:2000]
        except Exception:
            text = ""
        title = get_note_title(text, stem)
        t = LinkTarget(stem, title, category)
        targets.append(t)
        register(stem, t)
        spaced = camel_to_words(stem)
        if spaced != stem.lower():
            register(spaced, t)
        cleaned = re.sub(r"[_\-]", " ", stem.lower()).strip()
        if cleaned != stem.lower():
            register(cleaned, t)
        if title and title != stem and cfg.min_keyword_len <= len(title) <= 60:
            register(title, t)

    # Folder names (top-level + subfolders) as keywords
    for path in sorted(cfg.vault.rglob("*")):
        if not path.is_dir():
            continue
        if should_skip(path, cfg.vault, cfg.skip_dirs):
            continue
        name = path.name
        if name.startswith(".") or name in cfg.skip_dirs:
            continue
        if len(name) < cfg.min_keyword_len or name.lower() in STOP_WORDS:
            continue
        try:
            rel = path.relative_to(cfg.vault)
            cat = str(rel.parent) if rel.parent != Path(".") else ""
        except ValueError:
            cat = ""
        t = LinkTarget(name, name, cat)
        register(name, t)
        cleaned = re.sub(r"[_\-]", " ", name.lower()).strip()
        if cleaned != name.lower():
            register(cleaned, t)

    return kw, targets


def find_protected_regions(text: str) -> list[tuple[int, int]]:
    regions = []
    if text.startswith("---"):
        end = text.find("---", 3)
        if end > 0:
            regions.append((0, end + 3))
    for m in re.finditer(r"```[\s\S]*?```", text):
        regions.append((m.start(), m.end()))
    for m in re.finditer(r"`[^`]+`", text):
        regions.append((m.start(), m.end()))
    for m in re.finditer(r"\[\[[^\]]+\]\]", text):
        regions.append((m.start(), m.end()))
    for m in re.finditer(r"\[[^\]]*\]\([^)]*\)", text):
        regions.append((m.start(), m.end()))
    for m in re.finditer(r"^#{1,6}\s+.+$", text, re.MULTILINE):
        regions.append((m.start(), m.end()))
    for m in re.finditer(r"https?://\S+", text):
        regions.append((m.start(), m.end()))
    for m in re.finditer(r"<!--[\s\S]*?-->", text):
        regions.append((m.start(), m.end()))
    for marker in (MARKER_RELATED, MARKER_SYNONYMS, MARKER_TOPICS):
        start = text.find(marker)
        if start >= 0:
            regions.append((start, len(text)))
    regions.sort()
    merged = []
    for s, e in regions:
        if merged and s <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], e))
        else:
            merged.append((s, e))
    return merged


def is_protected(pos: int, end: int, regions) -> bool:
    for rs, re_ in regions:
        if rs > end:
            break
        if pos < re_ and end > rs:
            return True
    return False


def inject_links(text: str, kw_index: dict, self_stem: str
                 ) -> tuple[str, int]:
    protected = find_protected_regions(text)
    sorted_kws = sorted(kw_index.keys(), key=len, reverse=True)
    linked_stems: set[str] = set()
    replacements: list[tuple[int, int, str]] = []
    for kw in sorted_kws:
        target = kw_index[kw]
        if target.stem.lower() == self_stem.lower():
            continue
        if target.stem.lower() in linked_stems:
            continue
        pattern = re.compile(r"\b" + re.escape(kw) + r"\b", re.IGNORECASE)
        for match in pattern.finditer(text):
            pos, end = match.start(), match.end()
            if is_protected(pos, end, protected):
                continue
            if any(pos < re and end > rs for rs, re, _ in replacements):
                continue
            link = f"[[{target.stem}|{match.group(0)}]]"
            replacements.append((pos, end, link))
            linked_stems.add(target.stem.lower())
            break
    if not replacements:
        return text, 0
    replacements.sort(key=lambda x: x[0], reverse=True)
    result = text
    for s, e, r in replacements:
        result = result[:s] + r + result[e:]
    return result, len(replacements)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Umbra Phase 3: keyword linker")
    parser.add_argument("--config", type=str, default=None)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--one", type=str, default=None)
    parser.add_argument("--stats", action="store_true")
    args = parser.parse_args(argv)

    cfg = load_config(args.config)
    log_file = cfg.log_dir / "keyword_linker.log"
    log_line(log_file, "=== keyword_linker run start ===")
    kw_index, targets = build_keyword_index(cfg)
    log_line(log_file,
             f"  {len(kw_index)} keywords → {len(targets)} link targets")

    if args.stats:
        by_stem = defaultdict(list)
        for k, t in kw_index.items():
            by_stem[t.stem].append(k)
        for stem in sorted(by_stem.keys()):
            log_line(log_file, f"  {stem}: {', '.join(by_stem[stem])}")
        return 0

    notes = []
    for path in sorted(cfg.vault.rglob("*.md")):
        if should_skip(path, cfg.vault, cfg.skip_dirs):
            continue
        if path.name in cfg.skip_files:
            continue
        if args.one and str(path) != args.one:
            continue
        notes.append(path)

    log_line(log_file, f"  {len(notes)} notes to process")
    total_links = files_modified = 0
    for path in notes:
        try:
            text = path.read_text(errors="replace")
        except Exception:
            continue
        if len(text) < 30:
            continue
        stem = path.stem
        current = text
        note_total = 0
        for _ in range(cfg.max_keyword_passes):
            new, count = inject_links(current, kw_index, stem)
            if count == 0:
                break
            note_total += count
            current = new
        if note_total > 0:
            total_links += note_total
            files_modified += 1
            if not args.dry_run:
                path.write_text(current)

    log_line(log_file,
             f"=== done: {total_links} links in {files_modified} files ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
