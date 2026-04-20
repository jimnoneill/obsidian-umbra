# Configuration

Umbra reads `config.yaml` from (in order): `--config FLAG` > `$UMBRA_CONFIG` >
`./config.yaml` > `~/.obsidian-umbra/config.yaml`.

Every key has an environment-variable override:
`UMBRA_VAULT`, `UMBRA_MODEL_PATH`, `UMBRA_OUTPUT_SUBDIR`, `UMBRA_STATE_DIR`,
`UMBRA_CUDA_VISIBLE_DEVICES`.

---

## Required

| Key | Description |
|-----|-------------|
| `vault` | Absolute path to your Obsidian vault root |
| `model_path` | Absolute path to a Qwen3-4B-Instruct-2507 Q8_0 GGUF file |

---

## Paths

| Key | Default | Description |
|-----|---------|-------------|
| `output_subdir` | `umbra` | Where topic notes and `NOTE_INDEX.md` land (relative to vault) |
| `state_dir` | `~/.obsidian-umbra` | State, cache, logs (absolute path) |
| `cuda_visible_devices` | `"0"` | GPU to use (passed as env var) |

---

## Phase 1 — Daily Splitter

| Key | Default | Description |
|-----|---------|-------------|
| `n_ctx` | 16384 | llama-cpp context window |
| `n_gpu_layers` | -1 | Layers on GPU (-1 = all) |
| `temperature` | 0.2 | Sampling temperature |
| `max_tokens_per_call` | 3584 | Max tokens the LLM can emit |
| `min_daily_note_chars` | 80 | Skip daily notes shorter than this |

---

## Phase 2 — Semantic Backlinks

| Key | Default | Description |
|-----|---------|-------------|
| `top_k_related` | 5 | Max related notes per section |
| `min_similarity` | 0.30 | Minimum combined cosine + tag-bonus score |
| `tag_bonus` | 0.05 | Bonus per shared tag |
| `tag_bonus_cap` | 0.15 | Maximum tag bonus |
| `embed_snippet_len` | 800 | Chars of body to embed after the title |

---

## Phase 3 — Keyword Linker

| Key | Default | Description |
|-----|---------|-------------|
| `min_keyword_len` | 3 | Shortest indexable keyword |
| `max_keyword_passes` | 10 | Within-note convergence iterations |

---

## Phase 4 — Synonym Linker

| Key | Default | Description |
|-----|---------|-------------|
| `hdbscan_min_cluster_size` | 2 | Smallest cluster to emit |
| `hdbscan_min_samples` | 1 | HDBSCAN density parameter |
| `hdbscan_epsilon` | 0.35 | Cluster selection epsilon |
| `hdbscan_method` | `leaf` | `leaf` (finer) vs `eom` (broader) |
| `max_cluster_full_crosslink` | 20 | Above this → hub/spoke collapse |

---

## Shared

| Key | Default | Description |
|-----|---------|-------------|
| `skip_dirs` | `[.obsidian, .trash, Templates]` | Directory names to skip |
| `skip_files` | `[NOTE_INDEX.md]` | Filenames to skip |
