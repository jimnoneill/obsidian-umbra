#!/usr/bin/env python3
"""Phase 1 — Daily Note Splitter.

Parses daily notes (MM-DD-YYYY and YYYY-MM-DD) in the vault root, calls the
local Qwen3-4B-Instruct GGUF via llama-cpp-python to extract distinct topics,
and either:

* Appends the extracted topic into an existing topic note when Potion-32M
  cosine similarity against an existing title+content clears
  `merge_similarity_threshold` (default 0.65). The existing file grows by
  an `## Update YYYY-MM-DD` section with its own source backlink, and the
  frontmatter's `dates` + `sources` arrays gain the new entry.
* Writes a brand-new topic note otherwise, using the clean `slug.md`
  filename (no date suffix) and multi-date frontmatter from the start.

Backwards compatible with the pre-0.2.0 `slug-YYYY-MM-DD.md` filename scheme:
those files are still indexed as candidate match targets and get their
frontmatter upgraded to the multi-date schema the first time a new entry
merges into them.

Idempotent via state.json (mtime-tracked per daily note).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import traceback
from datetime import datetime
from pathlib import Path

import numpy as np
import yaml

from .common import (
    MARKER_RELATED,
    MARKER_SYNONYMS,
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


# ============================================================================
# State
# ============================================================================


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


# ============================================================================
# LLM topic extraction
# ============================================================================


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


# ============================================================================
# Topic-note parsing + writing (new multi-date schema)
# ============================================================================


FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)


def _strip_umbra_sections(text: str) -> str:
    """Remove Related Notes, Same Concept, and Topics blocks so they're
    not included when we embed or append."""
    for marker in (MARKER_RELATED, MARKER_SYNONYMS, MARKER_TOPICS):
        if marker in text:
            text = text.split(marker)[0].rstrip() + "\n"
    return text


def parse_topic_note(path: Path) -> dict | None:
    """Return dict with title, content (stripped of umbra sections),
    frontmatter dict, and body-after-frontmatter. Returns None on error."""
    try:
        text = path.read_text(errors="replace")
    except Exception:
        return None

    fm = {}
    body = text
    m = FRONTMATTER_RE.match(text)
    if m:
        try:
            fm = yaml.safe_load(m.group(1)) or {}
            if not isinstance(fm, dict):
                fm = {}
            body = text[m.end():]
        except yaml.YAMLError:
            fm = {}
            body = text

    body_stripped = _strip_umbra_sections(body)

    title = fm.get("title")
    if not title:
        h1 = re.search(r"^#\s+(.+)$", body_stripped, re.MULTILINE)
        title = h1.group(1).strip() if h1 else path.stem

    return {
        "path": str(path),
        "title": str(title),
        "frontmatter": fm,
        "body": body,                # original body including umbra sections
        "content": body_stripped,    # body with umbra sections removed
    }


def _fmt_yaml(fm: dict) -> str:
    return yaml.safe_dump(fm, sort_keys=False, allow_unicode=True,
                          default_flow_style=False).strip()


def write_topic_note(topic: dict, date_str: str, source_stem: str,
                     cfg: Config) -> Path:
    """Write a brand-new topic note using the clean filename + multi-date schema."""
    out_dir = cfg.vault / cfg.output_subdir
    out_dir.mkdir(parents=True, exist_ok=True)
    slug = slugify(topic["slug"])
    dest = out_dir / f"{slug}.md"
    # If a file at that path already exists from a prior run (same title
    # extracted but different content), disambiguate with the date. This is
    # an edge case; the normal merge path should catch matching topics
    # before we get here.
    if dest.exists():
        dest = out_dir / f"{slug}-{date_str}.md"

    fm = {
        "title": topic["title"],
        "date_first": date_str,
        "date_last": date_str,
        "dates": [date_str],
        "sources": [source_stem],
        "tags": topic.get("tags", []),
        "summary": topic.get("summary", ""),
        "auto_generated": True,
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }

    body = (
        f"---\n{_fmt_yaml(fm)}\n---\n\n"
        f"# {topic['title']}\n\n"
        f"> First entry: {date_str}\n\n"
        f"{topic['content']}\n"
    )
    dest.write_text(body)
    return dest


def append_to_topic_note(target: dict, topic: dict, date_str: str,
                         source_stem: str, cfg: Config) -> Path:
    """Append a new `## Update YYYY-MM-DD` section to an existing topic
    note. Upgrades the frontmatter to the multi-date schema if needed."""
    path = Path(target["path"])
    fm = dict(target["frontmatter"])
    body = _strip_umbra_sections(target["body"]).rstrip()

    # Upgrade legacy single-date schema (pre-0.2.0) to multi-date schema
    if "dates" not in fm:
        old_date = fm.pop("date", None) or target.get("first_date", "")
        old_src = fm.pop("source", None) or ""
        if isinstance(old_src, str) and old_src.startswith("[[") and old_src.endswith("]]"):
            old_src = old_src[2:-2]
        fm["date_first"] = old_date or date_str
        fm["date_last"] = old_date or date_str
        fm["dates"] = [old_date] if old_date else []
        fm["sources"] = [old_src] if old_src else []

    if date_str not in fm["dates"]:
        fm["dates"].append(date_str)
    fm["date_last"] = max(fm["dates"])

    if source_stem not in fm["sources"]:
        fm["sources"].append(source_stem)

    # Merge tags
    tags = list(fm.get("tags") or [])
    for t in topic.get("tags", []):
        if t not in tags:
            tags.append(t)
    fm["tags"] = tags
    fm["auto_generated"] = True
    fm["generated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    heading = cfg.append_section_heading_format.format(date=date_str)

    # Strip any existing YAML from the body so we can re-emit it cleanly
    m = FRONTMATTER_RE.match(body)
    if m:
        body = body[m.end():].rstrip()

    append_block = (
        f"\n\n---\n\n"
        f"{heading}\n\n"
        f"{topic['content']}\n"
    )

    new_text = f"---\n{_fmt_yaml(fm)}\n---\n\n{body.lstrip()}{append_block}"
    path.write_text(new_text)
    return path


# ============================================================================
# Topic match index (Potion-32M cosine)
# ============================================================================


class TopicIndex:
    """Incremental Potion-32M index over every existing topic note in
    `vault/<output_subdir>/`. Skips the generated NOTE_INDEX.md."""

    def __init__(self, cfg: Config, log_file: Path):
        self.cfg = cfg
        self.log_file = log_file
        self.dir = cfg.vault / cfg.output_subdir
        self.cache_path = cfg.cache_dir / "topic_index.npz"
        self.meta_path = cfg.cache_dir / "topic_index_meta.json"
        self.topics: list[dict] = []  # parsed notes
        self.embeddings: np.ndarray | None = None
        self._model = None

    def _get_model(self):
        if self._model is None:
            from model2vec import StaticModel
            self._model = StaticModel.from_pretrained("minishlab/potion-science-32M")
        return self._model

    def _embed_text(self, title: str, content: str) -> np.ndarray:
        snippet = f"{title}. {content[:self.cfg.merge_embed_snippet_len]}"
        return self._get_model().encode([snippet],
                                        show_progress_bar=False).astype(np.float32)[0]

    def _load_cache(self) -> tuple[dict, np.ndarray | None]:
        meta = {}
        emb = None
        if self.meta_path.exists():
            try:
                meta = json.loads(self.meta_path.read_text())
            except (json.JSONDecodeError, OSError):
                meta = {}
        if self.cache_path.exists():
            try:
                emb = np.load(self.cache_path)["embeddings"]
            except Exception:
                emb = None
        return meta, emb

    def _save_cache(self, meta: dict, emb: np.ndarray) -> None:
        self.cfg.cache_dir.mkdir(parents=True, exist_ok=True)
        self.meta_path.write_text(json.dumps(meta, indent=2))
        np.savez_compressed(self.cache_path, embeddings=emb)

    def build(self) -> None:
        if not self.cfg.merge_into_existing_topics:
            return
        self.dir.mkdir(parents=True, exist_ok=True)
        self.topics = []
        paths = [p for p in sorted(self.dir.glob("*.md"))
                 if p.name != "NOTE_INDEX.md"]

        for p in paths:
            t = parse_topic_note(p)
            if t is None:
                continue
            self.topics.append(t)

        if not self.topics:
            self.embeddings = None
            return

        old_meta, old_emb = self._load_cache()
        new_emb = np.zeros((len(self.topics), 256), dtype=np.float32)
        need: list[int] = []
        reused = 0

        for i, note in enumerate(self.topics):
            key = note["path"]
            path_mtime = Path(key).stat().st_mtime
            info = old_meta.get(key)
            if (info and old_emb is not None
                    and info.get("mtime", 0) >= path_mtime
                    and info.get("idx", -1) < len(old_emb)):
                new_emb[i] = old_emb[info["idx"]]
                reused += 1
            else:
                need.append(i)

        if need:
            log_line(self.log_file,
                     f"  Embedding {len(need)} new/modified topic notes "
                     f"({reused} cached)")
            fresh = []
            for i in need:
                t = self.topics[i]
                fresh.append(self._embed_text(t["title"], t["content"]))
            for k, i in enumerate(need):
                new_emb[i] = fresh[k]

        # Refresh cache with current mtimes
        meta = {
            t["path"]: {"mtime": Path(t["path"]).stat().st_mtime, "idx": i}
            for i, t in enumerate(self.topics)
        }
        self._save_cache(meta, new_emb)
        self.embeddings = new_emb

    def find_match(self, title: str, content: str) -> tuple[dict, float] | None:
        if not self.cfg.merge_into_existing_topics:
            return None
        if self.embeddings is None or len(self.topics) == 0:
            return None
        query_emb = self._embed_text(title, content)
        qn = query_emb / max(np.linalg.norm(query_emb), 1e-10)
        # Normalize existing embeddings once per index build
        norms = np.linalg.norm(self.embeddings, axis=1, keepdims=True)
        norms = np.maximum(norms, 1e-10)
        cand = self.embeddings / norms
        sims = cand @ qn
        best = int(np.argmax(sims))
        score = float(sims[best])
        if score >= self.cfg.merge_similarity_threshold:
            return self.topics[best], score
        return None

    def add_or_update(self, topic_path: Path) -> None:
        """Re-read and re-embed a single topic note. Called after we
        append or create, so a second topic in the same daily note can
        match the file we just wrote."""
        if not self.cfg.merge_into_existing_topics:
            return
        parsed = parse_topic_note(topic_path)
        if not parsed:
            return
        emb = self._embed_text(parsed["title"], parsed["content"])
        path_str = parsed["path"]
        existing_idx = next(
            (i for i, t in enumerate(self.topics) if t["path"] == path_str),
            None,
        )
        if existing_idx is not None:
            self.topics[existing_idx] = parsed
            if self.embeddings is not None:
                self.embeddings[existing_idx] = emb
        else:
            self.topics.append(parsed)
            if self.embeddings is None:
                self.embeddings = emb.reshape(1, -1)
            else:
                self.embeddings = np.vstack([self.embeddings, emb.reshape(1, -1)])


# ============================================================================
# Topic coalescing within a single daily note
# ============================================================================


def _merge_topics_for_single_append(topics: list[dict]) -> dict:
    """Combine multiple LLM-extracted topics (all from one daily note and
    all matching the same existing target) into one synthetic topic so
    they produce a single `## Update` section."""
    if len(topics) == 1:
        return topics[0]
    titles = [t["title"] for t in topics]
    tags: list[str] = []
    for t in topics:
        for tag in t.get("tags", []):
            if tag not in tags:
                tags.append(tag)
    parts = []
    for t in topics:
        parts.append(f"**{t['title']}**\n\n{t['content']}")
    combined_content = "\n\n".join(parts)
    return {
        "slug": topics[0]["slug"],
        "title": " · ".join(titles),
        "summary": "Multiple related threads from the same entry.",
        "content": combined_content,
        "tags": tags,
    }


# ============================================================================
# Daily-note update with topic backlinks
# ============================================================================


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


# ============================================================================
# Per-daily-note pipeline
# ============================================================================


def process_one(llm, daily_path: Path, cfg: Config, state: dict,
                log_file: Path, topic_index: TopicIndex,
                dry_run: bool = False) -> None:
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
            match = topic_index.find_match(t["title"], t["content"])
            if match:
                existing, score = match
                log_line(log_file,
                         f"    [dry] MERGE {t['slug']} → "
                         f"{Path(existing['path']).name} ({score:.2f})")
            else:
                log_line(log_file, f"    [dry] NEW   {t['slug']} — {t['title']}")
        return

    # First pass: decide new vs merge target for every topic in this daily
    # note, BEFORE doing any disk writes. This way two topics from the same
    # daily note that both match the same existing note get coalesced into
    # a single `## Update` section rather than producing two same-day
    # sections in the target file.
    decisions: list[dict] = []
    claimed_targets: dict[str, dict] = {}  # target path → decision slot
    for topic in topics:
        match = topic_index.find_match(topic["title"], topic["content"])
        if match:
            existing, score = match
            target_path = existing["path"]
            if target_path in claimed_targets:
                claimed_targets[target_path]["merged_topics"].append(topic)
                claimed_targets[target_path]["scores"].append(score)
                continue
            slot = {
                "kind": "append",
                "target": existing,
                "topic": topic,
                "merged_topics": [topic],
                "scores": [score],
            }
            claimed_targets[target_path] = slot
            decisions.append(slot)
        else:
            decisions.append({"kind": "new", "topic": topic})

    entries = []
    for d in decisions:
        if d["kind"] == "append":
            combined = _merge_topics_for_single_append(d["merged_topics"])
            dest = append_to_topic_note(
                d["target"], combined, date_str, daily_path.stem, cfg
            )
            scores = "+".join(f"{s:.2f}" for s in d["scores"])
            extra = (f" (coalesced {len(d['merged_topics'])} topics)"
                     if len(d["merged_topics"]) > 1 else "")
            log_line(log_file,
                     f"    ↪ append ({scores}) "
                     f"{dest.relative_to(cfg.vault)}{extra}")
        else:
            dest = write_topic_note(d["topic"], date_str, daily_path.stem, cfg)
            log_line(log_file, f"    → new {dest.relative_to(cfg.vault)}")

        # Keep the index fresh so the next topic in this same daily note
        # can still match this file (or a sibling one) via semantic search.
        topic_index.add_or_update(dest)
        # For the daily-note topics-section backlink, use the originating
        # topic for the title/tags so the link text matches what the LLM
        # actually extracted.
        display_topic = d["topic"] if d["kind"] == "new" else d["merged_topics"][0]
        entries.append((dest, display_topic))

    update_daily_note_with_links(daily_path, entries)
    state["processed"][daily_path.name] = {
        "mtime": daily_path.stat().st_mtime,
        "topics": [e[0].name for e in entries],
    }


# ============================================================================
# CLI entry
# ============================================================================


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

    # Build the topic index once per run so merges cross-reference
    # everything already on disk.
    topic_index = TopicIndex(cfg, log_file)
    log_line(log_file, "Building topic match index (Potion-32M)...")
    topic_index.build()
    n_idx = len(topic_index.topics)
    log_line(log_file,
             f"  {n_idx} existing topic notes indexed, "
             f"merge threshold={cfg.merge_similarity_threshold}")

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
            process_one(llm, path, cfg, state, log_file, topic_index,
                        dry_run=args.dry_run)
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
