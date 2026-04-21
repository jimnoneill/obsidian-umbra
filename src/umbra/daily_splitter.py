#!/usr/bin/env python3
"""Phase 1 — Daily Note Splitter.

Parses daily notes (MM-DD-YYYY and YYYY-MM-DD) in the vault root, calls the
local Qwen3-4B-Instruct GGUF via llama-cpp-python to extract distinct topics,
and writes one titled topic note per theme into VAULT/OUTPUT_SUBDIR/ with
bidirectional backlinks. Idempotent via state.json (mtime-tracked).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import traceback
from datetime import datetime
from pathlib import Path

import yaml

from .common import (
    MARKER_TOPICS,
    is_daily_note,
    log_line,
    parse_daily_date,
    slugify,
)
from .config import Config, load_config


SYSTEM_PROMPT = """You are a personal knowledge organizer. Given a journal entry, identify the distinct topics, projects, or themes discussed and return a structured JSON response.

For each distinct topic in the entry:
- slug: kebab-case identifier, 2-5 words (e.g. "plato-forms-metaphysics", "meno-slave-boy-recollection")
- title: human-readable title in Title Case (5-12 words)
- summary: 1-2 sentence synopsis
- content: the relevant passages from the journal, cleaned up but preserving meaning and first-person voice
- tags: 3-5 lowercase single-word or kebab-case tags

Rules:
- Each topic must be genuinely distinct. Do not split a single coherent thought into multiple topics.
- Prefer 1-4 topics per entry. Only exceed 4 if the entry is very long and multi-threaded.
- Preserve the author's exact voice and phrasing inside "content" — do not paraphrase or sanitize.
- Do not invent facts. Only include what is actually in the entry.
- Return ONLY valid JSON. No markdown fences. No commentary outside the JSON.

Response schema:
{"topics": [{"slug": "...", "title": "...", "summary": "...", "content": "...", "tags": [...]}]}

If the entry has no distinct topics (too short, too fragmented), return {"topics": []}."""


def load_state(state_file: Path) -> dict:
    if state_file.exists():
        try:
            return json.loads(state_file.read_text())
        except json.JSONDecodeError:
            pass
    return {"processed": {}}


def save_state(state_file: Path, state: dict) -> None:
    state_file.parent.mkdir(parents=True, exist_ok=True)
    state_file.write_text(json.dumps(state, indent=2, sort_keys=True))


def find_pending(cfg: Config, state: dict, force_all: bool = False,
                 since: str | None = None) -> list[Path]:
    pending = []
    scan_dirs = [cfg.vault] + [cfg.vault / d for d in ("ZJournal Notes", "Journal")]
    seen = set()
    for scan_dir in scan_dirs:
        if not scan_dir.exists() or scan_dir in seen:
            continue
        seen.add(scan_dir)
        for path in scan_dir.glob("*.md"):
            if not is_daily_note(path):
                continue
            norm = parse_daily_date(path.stem)
            if since and norm and norm < since:
                continue
            if force_all:
                pending.append(path)
                continue
            mtime = path.stat().st_mtime
            last = state["processed"].get(path.name, {}).get("mtime", 0)
            if mtime > last:
                pending.append(path)
    return sorted(set(pending))


def extract_topics(llm, cfg: Config, date_str: str, text: str,
                   log_file: Path) -> list[dict]:
    user_msg = (f"DATE: {date_str}\n\nJOURNAL ENTRY:\n{text}\n\n"
                "Return the JSON now.")
    resp = llm.create_chat_completion(
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_msg},
        ],
        temperature=cfg.temperature,
        max_tokens=cfg.max_tokens_per_call,
        response_format={"type": "json_object"},
    )
    raw = resp["choices"][0]["message"]["content"].strip()
    try:
        obj = json.loads(raw)
    except json.JSONDecodeError as e:
        log_line(log_file, f"  WARN JSON decode: {e}")
        return []
    topics = obj.get("topics", []) if isinstance(obj, dict) else []
    valid = []
    for t in topics:
        if not isinstance(t, dict):
            continue
        if not all(k in t and t[k] for k in ("slug", "title", "content")):
            continue
        t.setdefault("summary", "")
        t.setdefault("tags", [])
        if not isinstance(t["tags"], list):
            t["tags"] = []
        valid.append(t)
    return valid


def write_topic_note(topic: dict, date_str: str, source_stem: str,
                     cfg: Config) -> Path:
    out_dir = cfg.vault / cfg.output_subdir
    out_dir.mkdir(parents=True, exist_ok=True)
    slug = slugify(topic["slug"])
    dest = out_dir / f"{slug}-{date_str}.md"

    fm = {
        "title": topic["title"],
        "date": date_str,
        "source": source_stem,
        "tags": topic.get("tags", []),
        "summary": topic.get("summary", ""),
        "auto_generated": True,
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    fm_yaml = yaml.safe_dump(fm, sort_keys=False, allow_unicode=True,
                             default_flow_style=False).strip()

    body = (
        f"---\n{fm_yaml}\n---\n\n"
        f"# {topic['title']}\n\n"
        f"> Source: [[{source_stem}]] · {date_str}\n\n"
        f"{topic['content']}\n\n"
        f"---\n*Auto-generated by umbra on "
        f"{datetime.now().strftime('%Y-%m-%d')}*\n"
    )
    dest.write_text(body)
    return dest


def update_daily_note_with_links(daily_path: Path,
                                 entries: list[tuple[Path, dict]]) -> None:
    current = daily_path.read_text()
    if MARKER_TOPICS in current:
        current = current.split(MARKER_TOPICS)[0].rstrip()

    lines = ["", "", MARKER_TOPICS, "## Topics", ""]
    for dest, topic in entries:
        tags = " ".join(f"#{t}" for t in topic.get("tags", [])[:4])
        lines.append(f"- [[{dest.stem}|{topic['title']}]] {tags}".rstrip())
    lines += ["", MARKER_TOPICS, ""]
    daily_path.write_text(current.rstrip() + "\n".join(lines))


def process_one(llm, daily_path: Path, cfg: Config, state: dict,
                log_file: Path, dry_run: bool = False) -> None:
    date_str = parse_daily_date(daily_path.stem) or daily_path.stem
    text = daily_path.read_text().strip()

    if len(text) < cfg.min_daily_note_chars:
        log_line(log_file, f"  {daily_path.name}: too short, skipping")
        state["processed"][daily_path.name] = {
            "mtime": daily_path.stat().st_mtime,
            "topics": [], "skipped": "too_short",
        }
        return

    if MARKER_TOPICS in text:
        text = text.split(MARKER_TOPICS)[0].rstrip()

    log_line(log_file, f"  {daily_path.name}: {len(text)} chars → extracting")
    topics = extract_topics(llm, cfg, date_str, text, log_file)
    if not topics:
        log_line(log_file, f"  {daily_path.name}: no topics")
        state["processed"][daily_path.name] = {
            "mtime": daily_path.stat().st_mtime, "topics": [],
        }
        return

    log_line(log_file, f"  {daily_path.name}: {len(topics)} topics")
    if dry_run:
        for t in topics:
            log_line(log_file, f"    [dry] {t['slug']} — {t['title']}")
        return

    entries = []
    for topic in topics:
        dest = write_topic_note(topic, date_str, daily_path.stem, cfg)
        entries.append((dest, topic))
        log_line(log_file, f"    → {dest.relative_to(cfg.vault)}")

    update_daily_note_with_links(daily_path, entries)
    state["processed"][daily_path.name] = {
        "mtime": daily_path.stat().st_mtime,
        "topics": [e[0].name for e in entries],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Umbra Phase 1: daily splitter")
    parser.add_argument("--config", type=str, default=None)
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--since", type=str, default=None)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--one", type=str, default=None)
    args = parser.parse_args(argv)

    cfg = load_config(args.config)
    log_file = cfg.log_dir / "daily_splitter.log"
    state_file = cfg.state_dir / "daily_splitter_state.json"

    log_line(log_file, "=== daily_splitter run start ===")
    state = load_state(state_file)

    if args.one:
        one = Path(args.one).expanduser()
        if not is_daily_note(one):
            log_line(log_file, f"ERROR not a daily note: {one}")
            return 1
        pending = [one]
    else:
        pending = find_pending(cfg, state, force_all=args.all, since=args.since)

    if not pending:
        log_line(log_file, "No new or modified daily notes. Done.")
        return 0

    log_line(log_file, f"Found {len(pending)} daily notes")

    # Import llama_cpp lazily so --help doesn't require GPU stack
    from llama_cpp import Llama
    log_line(log_file, f"Loading model: {cfg.model_name} ({cfg.model_path})")
    llama_kwargs = dict(
        model_path=str(cfg.model_path),
        n_ctx=cfg.n_ctx,
        n_gpu_layers=cfg.n_gpu_layers,
        verbose=False,
    )
    if cfg.chat_format:
        llama_kwargs["chat_format"] = cfg.chat_format
    if cfg.n_threads:
        llama_kwargs["n_threads"] = cfg.n_threads
    llm = Llama(**llama_kwargs)
    log_line(log_file, "Model loaded.")

    ok = failed = 0
    for path in pending:
        try:
            process_one(llm, path, cfg, state, log_file, dry_run=args.dry_run)
            ok += 1
            if not args.dry_run:
                save_state(state_file, state)
        except Exception as e:
            failed += 1
            log_line(log_file, f"  ERROR {path.name}: {e}")
            log_line(log_file, traceback.format_exc())

    log_line(log_file, f"=== done: {ok} ok, {failed} failed ===")
    return 0 if failed == 0 else 2


if __name__ == "__main__":
    sys.exit(main())
