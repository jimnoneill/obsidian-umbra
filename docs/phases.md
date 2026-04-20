# Phases

Umbra runs four sequential phases. Each is idempotent and can be run
alone. Each writes only to bracketed sections in your notes so your
prose is never touched.

---

## Phase 1 — Daily Note Splitter (`umbra split`)

**Input**: daily notes in vault root, filenames matching `MM-DD-YYYY.md`
or `YYYY-MM-DD.md`. (Also scans `ZJournal Notes/` and `Journal/` if
present.)

**Model**: Qwen3-4B-Instruct (Q8_0, ~4GB), loaded locally via
llama-cpp-python. JSON output enforced via `response_format`.

**Output**: one titled topic note per extracted theme, written to
`<vault>/<output_subdir>/<slug>-YYYY-MM-DD.md`. Each has:

- YAML frontmatter: `title`, `date`, `source`, `tags`, `summary`, `auto_generated`
- H1 heading
- Source backlink: `> Source: [[MM-DD-YYYY]] · YYYY-MM-DD`
- Body: excerpted content in the author's first-person voice
- Auto-generated footer

The daily note itself gets a `## Topics` section appended with
`[[wikilinks]]` to each generated topic note.

**Idempotency**: `state.json` in `state_dir/` tracks processed files by
mtime. Only new or modified daily notes are re-processed.

**CLI**:

```bash
umbra split                             # incremental
umbra split --all                       # reprocess everything
umbra split --since 2024-06-01          # notes with date >= 2024-06-01
umbra split --dry-run                   # extract, log, don't write
umbra split --one vault/2024-06-15.md   # single file
```

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
