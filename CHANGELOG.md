# Changelog

All notable changes to obsidian-umbra are documented here. Format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/). Versions follow
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.2.0] 2026-04-21

Phase 1 no longer fragments the same concept across dozens of per-day
files. When the splitter extracts a topic from a daily note, it now
looks for an existing topic note that covers the same concept and
appends to it instead. You get one topic note per concept that grows
over time, with each day's contribution preserved as its own
`## Update YYYY-MM-DD` section.

### Changed
- **Phase 1 matches before writing.** Every extracted topic is embedded
  with Potion-32M (256-dim) and compared against the existing topic
  index by cosine similarity. Clearing the threshold (default 0.65)
  means append; otherwise create a new file.
- **New filename scheme**: `<slug>.md`. No date suffix. Legacy
  `<slug>-YYYY-MM-DD.md` files from 0.1.0 are still indexed as match
  targets and get their frontmatter upgraded the first time something
  merges into them. No destructive migration.
- **Multi-date frontmatter**. Every topic note now carries `date_first`,
  `date_last`, `dates: [...]`, and `sources: [[[daily]]...]` so the
  evolution of a concept stays legible in the YAML without opening the
  file.
- **Same-daily coalescing**. If the LLM extracts two closely-related
  topics from one daily note and both match the same existing file, they
  merge into a single combined `## Update` section instead of two
  same-day sections.
- **Threshold calibrated on real data.** Default 0.65 was picked by
  running 50 pairs from the user's actual vault through the matcher
  and optimizing for precision. At this cutoff the sample showed
  zero false-positive merges. Users can tune via
  `merge_similarity_threshold` in config.

### Added
- `merge_into_existing_topics` (bool, default true) config key.
- `merge_similarity_threshold` (float, default 0.65).
- `merge_embed_snippet_len` (int, default 500) controls how much body
  text goes into the matching embedding.
- `append_section_heading_format` (string, default `"## Update {date}"`).
- Topic index cache at `state_dir/cache/topic_index.{npz,meta.json}`.
  Keyed by path+mtime, so only changed or new topic notes get
  re-embedded on each run.

### Phase 4 interaction
Synonym clustering now sees fewer "two-per-day fragments of the same
thing" pairs and can do its real job: grouping genuinely-different
wordings that mean the same concept. Expect tighter clusters and less
redundancy in the `## Same Concept` sections.

## [0.1.0] 2026-04-20

Initial public release.

### Added
- **Phase 1 — Daily Splitter**: Qwen3-4B-Instruct (or any GGUF instruct
  model) via llama-cpp-python splits MM-DD-YYYY / YYYY-MM-DD daily
  notes into titled topic notes with YAML frontmatter and backlinks.
- **Phase 2 — Semantic Backlinks**: Potion-32M (256-dim) cosine
  similarity plus tag overlap bonus, writes top-5 Related Notes per
  note, plus a master NOTE_INDEX.md.
- **Phase 3 — Keyword Linker**: inline `[[wikilinks]]` injection from
  note stems, titles, and folder names. Specificity filter blocks
  generic single-word English. Per-note convergence loop.
- **Phase 4 — Synonym Linker**: GTE-large (1024-dim) plus cuML HDBSCAN
  clusters concept notes into synonym groups. Mega-clusters collapse
  to hub-and-spoke with a centroid-closest representative.
- **Custom model support**: `model_path`, `model_name`, `chat_format`,
  `n_threads` config keys. Any GGUF instruct model (Qwen, Llama 3,
  Mistral, Gemma, Phi-3) works.
- **Plato's Cave demo vault**: 22 daily notes + 24 topic notes seeded
  with real OpenAlex references. Full before/after comparison under
  `examples/`.
- **Config**: YAML file with env-var overrides, editable install via
  `pip install -e .`.
- **Cron-ready**: `deploy.sh all` for idempotent scheduled runs.

[Unreleased]: https://github.com/jimnoneill/obsidian-umbra/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/jimnoneill/obsidian-umbra/releases/tag/v0.2.0
[0.1.0]: https://github.com/jimnoneill/obsidian-umbra/releases/tag/v0.1.0
