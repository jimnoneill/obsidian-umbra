# Phases

Umbra runs four sequential phases. Each is idempotent and can be run
alone. Each writes only to bracketed sections in your notes so your
prose is never touched.

---

## Phase 1 — Daily Note Splitter (`umbra split`)

Phase 1 scans daily notes (filenames matching `MM-DD-YYYY.md` or
`YYYY-MM-DD.md`, plus the `ZJournal Notes/` and `Journal/`
sub-directories if they exist), asks the local LLM to pull out each
distinct topic, and then either appends to an existing topic note or
creates a new one.

The model is Qwen3-4B-Instruct by default (Q8_0 for 24GB+ VRAM, Q4_K_M
for 12GB), loaded through llama-cpp-python with JSON output enforced.
Any other GGUF instruct model works once `chat_format` is set to match.

### The match-before-writing flow

For each topic the LLM extracts from a daily entry, the splitter
embeds `title + content[:500]` with Potion-32M (the same 256-dim
static embeddings Phase 2 uses) and compares against every existing
topic note. If cosine similarity clears `merge_similarity_threshold`
(default 0.65), the topic gets appended to that file as a new
`## Update YYYY-MM-DD` section. Otherwise it becomes a fresh topic
note.

The default threshold was chosen by running 50 pairs from real
journaling data through the matcher. At 0.65 the sample had zero
false-positive merges with 80% recall. Most of the "missed" pairs
were really different concepts that an earlier clustering pass had
grouped together too aggressively, so true-human recall is higher
than the benchmark suggests. Push the threshold up for more
conservative matching (fewer merges, more files), down for more
aggressive merging (more merges, slightly higher false-positive risk).

### What a topic note looks like

Fresh notes get a clean filename (`<slug>.md`, no date suffix) and
multi-date frontmatter from day one:

```yaml
---
title: Gastroparesis Flare
date_first: 2024-01-15
date_last: 2026-04-21
dates: [2024-01-15, 2024-03-22, 2026-04-21]
sources: [01-15-2024, 03-22-2024, 04-21-2026]
tags: [health, gastroparesis]
auto_generated: true
---
```

Body starts with an H1 title and a plain-text `> First entry: DATE`
marker. Each subsequent merge appends an `## Update YYYY-MM-DD`
section — the heading itself carries the date, so there's no separate
source line. Daily references stay in the frontmatter as plain stems
(not `[[wikilinks]]`) so your Obsidian graph doesn't flood with
date-node clutter (0.2.1+).

### Legacy notes

Topic notes left behind by 0.1.0 use the older `<slug>-YYYY-MM-DD.md`
filename and single-date (`date`, `source`) frontmatter. They're
still indexed as match targets and get their frontmatter upgraded
the first time a newer daily entry merges into them. No mass
migration, no rename.

### Same-day coalescing

If the LLM splits a single daily entry into multiple topics that
happen to match the same existing file, they coalesce into one
combined `## Update` section instead of producing two same-day
sections. Keeps the target file clean when a day's thoughts orbit
the same concept from multiple angles.

### Idempotency

`state.json` in `state_dir/` tracks processed daily notes by mtime.
Only new or modified daily notes are re-processed. The topic index
is cached at `state_dir/cache/topic_index.{npz,meta.json}` keyed by
path+mtime, so only changed or new topic notes get re-embedded on
each run.

### CLI

```bash
umbra split                             # incremental
umbra split --all                       # reprocess everything
umbra split --since 2024-06-01          # notes with date >= 2024-06-01
umbra split --dry-run                   # extract, log, don't write
umbra split --one vault/2024-06-15.md   # single file
```

`--dry-run` is especially useful after changing the threshold: it
prints `MERGE` vs `NEW` for every extracted topic without touching
disk.

---

## Phase 2 — Semantic Backlinks (`umbra semantic`)

**Model**: Potion-32M (`minishlab/potion-science-32M`) — 256-dim static
embeddings. Deterministic. Fast (~1s for 1000 notes on CPU).

**Algorithm**:
1. Parse all vault notes (skipping `skip_dirs`). Extract title, tags, content.
2. Embed `title + content[:800]` with Potion-32M.
3. Compute pairwise cosine similarity.
4. Add tag-overlap bonus: +0.05 per shared tag, capped at +0.15.
5. For each note, keep top-5 matches with combined score ≥ `min_similarity` (default 0.30).
6. Write `## Related Notes` section with `[[wikilinks]]` and similarity %.

**Also generates** `<vault>/<output_subdir>/NOTE_INDEX.md` — a master
catalog grouped by directory, with every note titled and tagged.

**Caching**: `cache/backlink_embeddings.npz` + `cache/backlink_meta.json`,
keyed by `(path, mtime)`. Only re-embeds notes that actually changed.
Post-write mtime refresh ensures the cache survives Phase 3/4 edits.

**CLI**:

```bash
umbra semantic                # incremental
umbra semantic --rebuild      # re-embed all notes
umbra semantic --dry-run      # compute, don't write
umbra semantic --index-only   # only regenerate NOTE_INDEX.md
```

---

## Phase 3 — Keyword Linker (`umbra keywords`)

**No model.** Pure keyword matching. Fast and deterministic.

**Keyword index built from**:
- Note stems (non-daily only)
- CamelCase splits (`TopicModeling` → `topic modeling`)
- Underscore/hyphen cleanup (`artificial_intel` → `artificial intel`)
- H1 / YAML titles (length 4–60)
- Folder names (top-level and nested)

**Specificity filter**: single-word lowercase English words are rejected.
A keyword is indexed only if it's multi-word, CamelCase, all-uppercase
acronym, contains a digit, or contains an underscore/hyphen. This keeps
`ME490` / `HuggingFace` / `NER` but rejects `images` / `money` / `data`.

**Injection**:
- Sorts keywords longest-first for greedy matching.
- For each match, wraps the first occurrence in `[[stem|text]]`.
- Only one match per (note, target) to avoid clutter.
- Protected regions never modified: YAML frontmatter, code blocks,
  existing links, URLs, HTML comments, markdown headings, Umbra section
  markers.
- Convergence loop (up to 10 passes per note) handles position shifts
  caused by link insertion.

**CLI**:

```bash
umbra keywords                      # process all
umbra keywords --dry-run            # count only
umbra keywords --stats              # print keyword → target mapping
umbra keywords --one vault/foo.md   # single file
```

---

## Phase 4 — Synonym Linker (`umbra synonyms`)

**Model**: GTE-large (`thenlper/gte-large`) — 1024-dim dense embeddings.
Loaded on GPU. Finer semantic granularity than Potion-32M.

**Algorithm**:
1. Collect non-daily notes. Extract a single "phrase" per note — the
   title (YAML → H1 → humanized stem).
2. Embed phrases with GTE-large.
3. Cluster with cuML HDBSCAN:
   - `min_cluster_size=2`, `min_samples=1`
   - `cluster_selection_epsilon=0.35`
   - `cluster_selection_method=leaf`
4. For each cluster:
   - **Small cluster** (≤ `max_cluster_full_crosslink`, default 20):
     every member gets `[[wikilinks]]` to every other member.
   - **Mega cluster** (> 20): find centroid-closest representative.
     Every other member gets one link to the representative. The
     representative gets links to its top-5 closest members.
5. Write `## Same Concept` section with the sibling links.

**Why HDBSCAN?** Density-based clustering finds variable-sized groups
without fixing K. Leaf-method extraction returns the finest-grained
clusters. Noise points (singleton concepts) are left unclustered.

**Caching**: `cache/synonym_embeddings.npz` + `synonym_meta.json`, keyed
by `(path, title)`. Only re-embeds when the title actually changes.
Cluster assignments persisted to `synonym_clusters.pickle` for
inspection.

**CLI**:

```bash
umbra synonyms               # incremental
umbra synonyms --rebuild     # re-embed everything
umbra synonyms --stats       # cluster size histogram
umbra synonyms --dry-run     # compute, don't write
```

---

## Section Markers

Every section Umbra writes is bracketed by HTML comment markers so
Umbra knows exactly what it wrote and can safely replace it on re-run:

```markdown
<!-- umbra: generated topic links -->
## Topics
...
<!-- umbra: generated topic links -->

<!-- umbra: related notes -->
## Related Notes
...
<!-- umbra: related notes -->

<!-- umbra: synonyms -->
## Same Concept
...
<!-- umbra: synonyms -->
```

Don't edit the content between markers — it gets overwritten. Your
prose outside the markers is never touched.
