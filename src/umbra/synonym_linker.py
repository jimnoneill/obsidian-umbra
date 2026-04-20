#!/usr/bin/env python3
"""Phase 4 — Synonym Linker.

Embeds non-daily note titles with GTE-large (1024-dim), clusters with
cuML HDBSCAN (min_cluster_size=2, epsilon=0.35, leaf), then adds
bidirectional [[wikilinks]] between cluster siblings via a "## Same
Concept" section.

Mega-clusters (>max_cluster_full_crosslink) collapse to hub/spoke:
each member links to the centroid-closest representative; the
representative links to its top-5 closest members.
"""

from __future__ import annotations

import argparse
import json
import pickle
import re
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
import yaml

from .common import (
    MARKER_RELATED, MARKER_SYNONYMS, MARKER_TOPICS,
    is_daily_note, log_line, should_skip,
)
from .config import Config, load_config

MODEL_NAME = "thenlper/gte-large"
EMBED_DIM = 1024
_TOPIC_DATE_SUFFIX = re.compile(r"-(\d{4})-(\d{2})-(\d{2})$")


def humanize_stem(stem: str) -> str:
    no_date = _TOPIC_DATE_SUFFIX.sub("", stem)
    spaced = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", no_date)
    spaced = re.sub(r"(?<=[A-Z])(?=[A-Z][a-z])", " ", spaced)
    return re.sub(r"[_\-]+", " ", spaced).strip()


def strip_syn(text: str) -> str:
    if MARKER_SYNONYMS in text:
        return text.split(MARKER_SYNONYMS)[0].rstrip()
    return text


def parse_note(path: Path) -> dict | None:
    try:
        text = path.read_text(errors="replace")
    except Exception:
        return None
    clean = strip_syn(text)
    for m in (MARKER_RELATED, MARKER_TOPICS):
        if m in clean:
            clean = clean.split(m)[0].rstrip()
    stem = path.stem
    title = None
    if clean.startswith("---"):
        end = clean.find("---", 3)
        if end > 0:
            try:
                fm = yaml.safe_load(clean[3:end])
                if isinstance(fm, dict) and fm.get("title"):
                    title = str(fm["title"]).strip()
            except yaml.YAMLError:
                pass
    if not title:
        body = (clean[clean.find("---", 3) + 3:]
                if clean.startswith("---") else clean)
        h1 = re.search(r"^#\s+(.+)$", body, re.MULTILINE)
        if h1:
            title = h1.group(1).strip()
            title = re.sub(r"\[\[[^\|\]]+\|([^\]]+)\]\]", r"\1", title)
            title = re.sub(r"\[\[([^\]]+)\]\]", r"\1", title)
    if not title or len(title) < 4:
        title = humanize_stem(stem)
    if len(title) < 4:
        return None
    return {"path": str(path), "stem": stem, "title": title,
            "mtime": path.stat().st_mtime}


def collect_concept_notes(cfg: Config) -> list[dict]:
    notes = []
    for path in sorted(cfg.vault.rglob("*.md")):
        if should_skip(path, cfg.vault, cfg.skip_dirs):
            continue
        if path.name in cfg.skip_files:
            continue
        if is_daily_note(path):
            continue
        n = parse_note(path)
        if n:
            notes.append(n)
    return notes


def load_cache(cache_dir: Path) -> tuple[dict, np.ndarray | None]:
    mp = cache_dir / "synonym_meta.json"
    ep = cache_dir / "synonym_embeddings.npz"
    meta = {}
    emb = None
    if mp.exists():
        try:
            meta = json.loads(mp.read_text())
        except (json.JSONDecodeError, OSError):
            pass
    if ep.exists():
        try:
            emb = np.load(ep)["embeddings"]
        except Exception:
            pass
    return meta, emb


def save_cache(cache_dir: Path, meta: dict, emb: np.ndarray) -> None:
    cache_dir.mkdir(parents=True, exist_ok=True)
    (cache_dir / "synonym_meta.json").write_text(json.dumps(meta, indent=2))
    np.savez_compressed(cache_dir / "synonym_embeddings.npz", embeddings=emb)


def build_embeddings(notes: list[dict], cfg: Config, rebuild: bool,
                     log_file: Path) -> np.ndarray:
    from sentence_transformers import SentenceTransformer
    old_meta, old_emb = ({}, None) if rebuild else load_cache(cfg.cache_dir)
    titles = [n["title"] for n in notes]
    new_emb = np.zeros((len(notes), EMBED_DIM), dtype=np.float32)
    to_embed: list[int] = []
    reused = 0
    for i, n in enumerate(notes):
        info = old_meta.get(n["path"])
        if (info and info.get("title") == n["title"]
                and old_emb is not None
                and info.get("idx", -1) < len(old_emb)):
            new_emb[i] = old_emb[info["idx"]]
            reused += 1
        else:
            to_embed.append(i)
    if to_embed:
        log_line(log_file, f"  Loading {MODEL_NAME}...")
        model = SentenceTransformer(MODEL_NAME, device="cuda")
        log_line(log_file,
                 f"  Embedding {len(to_embed)} titles ({reused} cached)")
        fresh = model.encode([titles[i] for i in to_embed],
                             convert_to_numpy=True, show_progress_bar=False,
                             batch_size=32).astype(np.float32)
        for k, i in enumerate(to_embed):
            new_emb[i] = fresh[k]
    else:
        log_line(log_file, f"  All {reused} embeddings cached")
    save_cache(cfg.cache_dir,
               {n["path"]: {"title": n["title"], "idx": i}
                for i, n in enumerate(notes)}, new_emb)
    return new_emb


def cluster_embeddings(emb: np.ndarray, cfg: Config) -> np.ndarray:
    import cupy as cp
    from cuml.cluster import HDBSCAN
    e_cp = cp.asarray(emb).astype(cp.float32)
    clusterer = HDBSCAN(
        min_cluster_size=cfg.hdbscan_min_cluster_size,
        min_samples=cfg.hdbscan_min_samples,
        cluster_selection_epsilon=cfg.hdbscan_epsilon,
        cluster_selection_method=cfg.hdbscan_method,
    )
    labels = clusterer.fit_predict(e_cp)
    return cp.asnumpy(labels)


def write_synonym_section(path_str: str, siblings: list[tuple[str, str]]
                          ) -> bool:
    path = Path(path_str)
    try:
        current = path.read_text(errors="replace")
    except Exception:
        return False
    cleaned = strip_syn(current).rstrip()
    if not siblings:
        if MARKER_SYNONYMS in current:
            path.write_text(cleaned + "\n")
            return True
        return False
    lines = ["", "", MARKER_SYNONYMS, "## Same Concept", ""]
    for stem, title in siblings:
        lines.append(f"- [[{stem}|{title}]]")
    lines += ["", MARKER_SYNONYMS, ""]
    new = cleaned + "\n".join(lines)
    if new == current:
        return False
    path.write_text(new)
    return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Umbra Phase 4: synonym linker")
    parser.add_argument("--config", type=str, default=None)
    parser.add_argument("--rebuild", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--stats", action="store_true")
    args = parser.parse_args(argv)

    cfg = load_config(args.config)
    log_file = cfg.log_dir / "synonym_linker.log"
    log_line(log_file, "=== synonym_linker run start ===")

    notes = collect_concept_notes(cfg)
    log_line(log_file, f"  {len(notes)} concept notes")
    if len(notes) < 4:
        return 0

    emb = build_embeddings(notes, cfg, args.rebuild, log_file)
    labels = cluster_embeddings(emb, cfg)
    clusters: dict[int, list[int]] = defaultdict(list)
    for i, lab in enumerate(labels):
        if lab != -1:
            clusters[int(lab)].append(i)
    total_in = sum(len(v) for v in clusters.values())
    log_line(log_file, f"  {len(clusters)} clusters, {total_in} clustered, "
             f"{len(notes) - total_in} solo/noise")

    if not args.dry_run:
        dump = {int(k): [(notes[i]["stem"], notes[i]["title"], notes[i]["path"])
                         for i in v] for k, v in clusters.items()}
        with open(cfg.cache_dir / "synonym_clusters.pickle", "wb") as f:
            pickle.dump(dump, f)

    if args.stats:
        sizes = defaultdict(int)
        for v in clusters.values():
            sizes[len(v)] += 1
        for s in sorted(sizes.keys()):
            log_line(log_file, f"  size {s}: {sizes[s]} clusters")
        return 0

    from scipy.spatial.distance import cdist

    def rep(idx_list):
        embs = emb[idx_list]
        centroid = embs.mean(axis=0, keepdims=True)
        d = cdist(centroid, embs, metric="euclidean")[0]
        return idx_list[int(np.argmin(d))]

    note_siblings: dict[str, list[tuple[str, str]]] = {}
    mega = 0
    for cid, idx_list in clusters.items():
        if len(idx_list) <= cfg.max_cluster_full_crosslink:
            for i in idx_list:
                note_siblings[notes[i]["path"]] = [
                    (notes[j]["stem"], notes[j]["title"])
                    for j in idx_list if j != i
                ]
        else:
            mega += 1
            rep_i = rep(idx_list)
            rep_entry = (notes[rep_i]["stem"], notes[rep_i]["title"])
            for i in idx_list:
                if i != rep_i:
                    note_siblings[notes[i]["path"]] = [rep_entry]
            other_idx = [j for j in idx_list if j != rep_i]
            dists = cdist(emb[rep_i:rep_i + 1], emb[other_idx],
                          metric="euclidean")[0]
            top5 = np.argsort(dists)[:5]
            note_siblings[notes[rep_i]["path"]] = [
                (notes[other_idx[k]]["stem"], notes[other_idx[k]]["title"])
                for k in top5
            ]
    log_line(log_file, f"  {mega} mega-clusters collapsed to hub/spoke")

    written = noop = 0
    for path_str, sibs in note_siblings.items():
        if args.dry_run:
            written += 1
            continue
        if write_synonym_section(path_str, sibs):
            written += 1
        else:
            noop += 1

    # Clear stale
    if not args.dry_run:
        clustered_paths = set(note_siblings.keys())
        for n in notes:
            if n["path"] in clustered_paths:
                continue
            try:
                text = Path(n["path"]).read_text(errors="replace")
            except Exception:
                continue
            if MARKER_SYNONYMS in text:
                write_synonym_section(n["path"], [])

    log_line(log_file, f"=== done: {written} linked, {noop} unchanged ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
