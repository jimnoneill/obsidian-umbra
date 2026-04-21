# Changelog

All notable changes to obsidian-umbra are documented here. Format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and versions
follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.0] — 2026-04-20

Initial public release.

### Added
- **Phase 1 — Daily Splitter**: Qwen3-4B-Instruct (or any GGUF instruct
  model) via llama-cpp-python splits MM-DD-YYYY / YYYY-MM-DD daily
  notes into titled topic notes with YAML frontmatter and backlinks.
- **Phase 2 — Semantic Backlinks**: Potion-32M (256-dim) cosine
  similarity + tag overlap bonus → top-5 Related Notes section per
  note. Master NOTE_INDEX.md catalog.
- **Phase 3 — Keyword Linker**: inline `[[wikilinks]]` injection from
  note stems, titles, and folder names. Specificity filter blocks
  generic single-word English. Per-note convergence loop.
- **Phase 4 — Synonym Linker**: GTE-large (1024-dim) + cuML HDBSCAN
  clusters concept notes into synonym groups. Mega-clusters collapse
  to hub/spoke with centroid-closest representative.
- **Custom model support**: `model_path`, `model_name`, `chat_format`,
  `n_threads` config keys — any GGUF instruct model (Qwen, Llama 3,
  Mistral, Gemma, Phi-3) works.
- **Plato's Cave demo vault**: 22 daily notes + 24 topic notes seeded
  with real OpenAlex references. Full before/after comparison in
  `examples/`.
- **Config**: YAML file with env-var overrides, editable install via
  `pip install -e .`.
- **Cron-ready**: `deploy.sh all` for idempotent scheduled runs.

[Unreleased]: https://github.com/jimnoneill/obsidian-umbra/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/jimnoneill/obsidian-umbra/releases/tag/v0.1.0
