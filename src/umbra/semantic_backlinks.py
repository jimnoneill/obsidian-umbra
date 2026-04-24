#!/usr/bin/env python3
"""Phase 2 — Semantic Backlinks.

Embeds every note with Potion-32M (256-dim), computes pairwise cosine
similarity + tag overlap bonus, and appends a "## Related Notes" section
with top-K [[wikilinks]] + similarity %. Generates NOTE_INDEX.md as
a master catalog by directory.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import numpy as np
import yaml

from .common import MARKER_RELATED, is_daily_note, log_line, should_skip
from .config import Config, load_config


def parse_frontmatter(text: str) -> dict:
    if not text.startswith("---"):
        return {}
    end = text.find("---", 3)
    if end < 0:
        return {}
    try:
        fm = yaml.safe_load(text[3:end])
        return fm if isinstance(fm, dict) else {}
    except yaml.YAMLError:
        return {}


def strip_related(text: str) -> str:
    if MARKER_RELATED in text:
        return text.split(MARKER_RELATED)[0].rstrip()
    return text


def parse_note(path: Path, vault: Path, min_chars: int) -> dict | None:
    try:
        text = path.read_text(errors="replace")
    except Exception:
        return None
    clean = strip_related(text)
    if len(clean.strip()) < min_chars:
        return None
    fm = parse_frontmatter(clean)
    title = fm.get("title")
    tags = fm.get("tags", [])
    if not isinstance(tags, list):
        tags = []
    tags = [str(t).lower() for t in tags if t]
    if not title:
        h1 = re.search(r"^#\s+(.+)$", clean, re.MULTILINE)
        title = h1.group(1).strip() if h1 else path.stem
    try:
        rel = str(path.relative_to(vault))
    except ValueError:
        rel = path.name
    return {
        "path": str(path), "rel": rel, "stem": path.stem,
        "title": title, "tags": tags, "content": clean,
        "mtime": path.stat().st_mtime,
    }


def collect_notes(cfg: Config) -> list[dict]:
    notes = []
    for path in sorted(cfg.vault.rglob("*.md")):
        if should_skip(path, cfg.vault, cfg.skip_dirs):
            continue
        if path.name in cfg.skip_files:
            continue
        note = parse_note(path, cfg.vault, 50)
        if note:
            notes.append(note)
    return notes


def embed_notes(notes: list[dict], cfg: Config) -> np.ndarray:
    from model2vec import StaticModel
    model = StaticModel.from_pretrained("minishlab/potion-science-32M")
    texts = [n["title"] + ". " + n["content"][:cfg.embed_snippet_len]
             for n in notes]
    return model.encode(texts, show_progress_bar=False).astype(np.float32)


def cosine_matrix(e: np.ndarray) -> np.ndarray:
    norms = np.maximum(np.linalg.norm(e, axis=1, keepdims=True), 1e-10)
    n = e / norms
    return n @ n.T


def tag_bonus_matrix(notes: list[dict], cfg: Config) -> np.ndarray:
    n = len(notes)
    tags = [set(x["tags"]) for x in notes]
    b = np.zeros((n, n), dtype=np.float32)
    for i in range(n):
        if not tags[i]:
            continue
        for j in range(i + 1, n):
            overlap = len(tags[i] & tags[j])
            if overlap > 0:
                v = min(overlap * cfg.tag_bonus, cfg.tag_bonus_cap)
                b[i, j] = v
                b[j, i] = v
    return b


def build_stem_map(notes: list[dict]) -> dict[str, list[int]]:
    sm: dict[str, list[int]] = defaultdict(list)
    for i, n in enumerate(notes):
        sm[n["stem"]].append(i)
    return sm


def link_target(note: dict, stem_map: dict[str, list[int]]) -> str:
    stem = note["stem"]
    if len(stem_map.get(stem, [])) <= 1:
        return stem
    rel = note["rel"]
    return rel[:-3] if rel.endswith(".md") else rel


def write_related_section(note: dict, related: list[tuple[dict, float]],
                          stem_map, dry_run: bool = False) -> bool:
    path = Path(note["path"])
    current = path.read_text(errors="replace")
    cleaned = strip_related(current).rstrip()
    if not related:
        if MARKER_RELATED in current and not dry_run:
            path.write_text(cleaned + "\n")
            return True
        return False
    lines = ["", "", MARKER_RELATED, "## Related Notes", ""]
    for rel, score in related:
        lines.append(
            f"- [[{link_target(rel, stem_map)}|{rel['title']}]] ({int(score * 100)}%)"
        )
    lines += ["", MARKER_RELATED, ""]
    new = cleaned + "\n".join(lines)
    if new == current:
        return False
    if not dry_run:
        path.write_text(new)
    return True


def generate_note_index(notes: list[dict], cfg: Config, stem_map) -> str:
    by_dir: dict[str, list[dict]] = defaultdict(list)
    indexable = [n for n in notes if not is_daily_note(Path(n["path"]))]
    for n in indexable:
        parent = str(Path(n["rel"]).parent)
        if parent == ".":
            parent = "(root)"
        by_dir[parent].append(n)
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    lines = ["---", "title: Note Index", "auto_generated: true",
             f"generated_at: '{ts}'", "---", "", "# Note Index", "",
             f"*{len(indexable)} notes indexed on {ts}*", ""]
    for dirname in sorted(by_dir.keys()):
        lines += [f"## {dirname if dirname != '(root)' else 'Root'}", ""]
        for n in sorted(by_dir[dirname], key=lambda x: x["title"].lower()):
            tag_str = " ".join(f"#{t}" for t in n["tags"][:3])
            lines.append(
                f"- [[{link_target(n, stem_map)}|{n['title']}]] {tag_str}".rstrip()
            )
        lines.append("")
    return "\n".join(lines) + "\n"


def load_cache(cache_dir: Path) -> tuple[dict, np.ndarray | None]:
    meta_p = cache_dir / "backlink_meta.json"
    emb_p = cache_dir / "backlink_embeddings.npz"
    meta = {}
    emb = None
    if meta_p.exists():
        try:
            meta = json.loads(meta_p.read_text())
        except (json.JSONDecodeError, OSError):
            pass
    if emb_p.exists():
        try:
            emb = np.load(emb_p)["embeddings"]
        except Exception:
            pass
    return meta, emb


def save_cache(cache_dir: Path, meta: dict, emb: np.ndarray) -> None:
    cache_dir.mkdir(parents=True, exist_ok=True)
    (cache_dir / "backlink_meta.json").write_text(json.dumps(meta, indent=2))
    np.savez_compressed(cache_dir / "backlink_embeddings.npz", embeddings=emb)


def build_embeddings_incremental(notes: list[dict], cfg: Config,
                                 rebuild: bool, log_file: Path) -> np.ndarray:
    if rebuild:
        emb = embed_notes(notes, cfg)
        save_cache(cfg.cache_dir,
                   {n["path"]: {"mtime": n["mtime"], "idx": i}
                    for i, n in enumerate(notes)}, emb)
        return emb
    old_meta, old_emb = load_cache(cfg.cache_dir)
    dim = 256
    new_emb = np.zeros((len(notes), dim), dtype=np.float32)
    reused = 0
    need = []
    for i, n in enumerate(notes):
        info = old_meta.get(n["path"])
        if (info and old_emb is not None
                and info.get("idx", -1) < len(old_emb)
                and info.get("mtime", 0) >= n["mtime"]):
            new_emb[i] = old_emb[info["idx"]]
            reused += 1
        else:
            need.append(i)
    if need:
        log_line(log_file, f"  Embedding {len(need)} new/modified ({reused} cached)")
        from model2vec import StaticModel
        model = StaticModel.from_pretrained("minishlab/potion-science-32M")
        texts = [notes[i]["title"] + ". "
                 + notes[i]["content"][:cfg.embed_snippet_len]
                 for i in need]
        fresh = model.encode(texts, show_progress_bar=False).astype(np.float32)
        for k, i in enumerate(need):
            new_emb[i] = fresh[k]
    else:
        log_line(log_file, f"  All {reused} embeddings cached")
    save_cache(cfg.cache_dir,
               {n["path"]: {"mtime": n["mtime"], "idx": i}
                for i, n in enumerate(notes)}, new_emb)
    return new_emb


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Umbra Phase 2: semantic backlinks")
    parser.add_argument("--config", type=str, default=None)
    parser.add_argument("--rebuild", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--index-only", action="store_true")
    args = parser.parse_args(argv)

    cfg = load_config(args.config)
    log_file = cfg.log_dir / "semantic_backlinks.log"
    log_line(log_file, "=== semantic_backlinks run start ===")

    notes = collect_notes(cfg)
    log_line(log_file, f"  {len(notes)} notes found")
    if len(notes) < 2:
        return 0
    stem_map = build_stem_map(notes)

    if args.index_only:
        idx = generate_note_index(notes, cfg, stem_map)
        out = cfg.vault / cfg.output_subdir / "NOTE_INDEX.md"
        out.parent.mkdir(parents=True, exist_ok=True)
        if not args.dry_run:
            out.write_text(idx)
        log_line(log_file, f"  Wrote {out}")
        return 0

    emb = build_embeddings_incremental(notes, cfg, args.rebuild, log_file)
    sim = np.clip(cosine_matrix(emb) + tag_bonus_matrix(notes, cfg), 0.0, 1.0)
    daily_mask = np.array([is_daily_note(Path(n["path"])) for n in notes])
    related_map = {}
    for i in range(len(notes)):
        s = sim[i].copy()
        s[i] = -1
        s[daily_mask] = -1  # never surface a daily note as a related target
        top = np.argsort(s)[::-1][:cfg.top_k_related]
        related_map[i] = [(int(j), float(s[j])) for j in top
                          if s[j] >= cfg.min_similarity]

    written = skipped = 0
    for i, note in enumerate(notes):
        rel = [(notes[j], sc) for j, sc in related_map[i]]
        try:
            if write_related_section(note, rel, stem_map, args.dry_run):
                written += 1
            else:
                skipped += 1
        except Exception as e:
            log_line(log_file, f"  WARN {note['path']}: {e}")

    # Refresh mtimes for next-run cache hit
    if not args.dry_run and written > 0:
        new_meta = {}
        for i, n in enumerate(notes):
            try:
                new_meta[n["path"]] = {"mtime": Path(n["path"]).stat().st_mtime,
                                       "idx": i}
            except OSError:
                new_meta[n["path"]] = {"mtime": n["mtime"], "idx": i}
        save_cache(cfg.cache_dir, new_meta, emb)

    # Index
    idx = generate_note_index(notes, cfg, stem_map)
    out = cfg.vault / cfg.output_subdir / "NOTE_INDEX.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    if not args.dry_run:
        out.write_text(idx)
    log_line(log_file,
             f"=== done: {written} updated, {skipped} unchanged ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
