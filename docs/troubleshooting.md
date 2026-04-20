# Troubleshooting

## `llama-cpp-python` won't find CUDA

You need to build llama-cpp-python with CUDA support. `pip install
llama-cpp-python` alone gives you CPU-only inference.

```bash
pip uninstall -y llama-cpp-python
CMAKE_ARGS="-DGGML_CUDA=on -DCMAKE_CUDA_ARCHITECTURES=89" \
pip install llama-cpp-python --force-reinstall --no-cache-dir
```

Set `CMAKE_CUDA_ARCHITECTURES` to your GPU's compute capability
(e.g. 89 for RTX 4090, 120 for Blackwell).

After reinstall, verify:

```bash
python -c "from llama_cpp import Llama; print('ok')"
ls -lh $(python -c 'import llama_cpp, os; print(os.path.join(os.path.dirname(llama_cpp.__file__), "lib", "libggml-cuda.so"))')
```

The `libggml-cuda.so` file should be ~100MB+.

---

## `cuml` / `cupy` import errors

RAPIDS (cuml, cupy) is finicky. Prefer conda:

```bash
conda create -n umbra python=3.10
conda activate umbra
conda install -c rapidsai -c conda-forge -c nvidia rapids=24.04 cuda-version=12.0
pip install -e .
```

If you must use pip: install `cupy-cuda12x` matching your CUDA and then
try `cuml` wheels from https://pypi.nvidia.com.

---

## `llama-cpp-python` reinstall broke `cupy`

llama-cpp-python's setup can bump numpy past 2.3, which breaks cupy.
Pin numpy and reinstall cupy:

```bash
pip install numpy==2.2.6 --force-reinstall
pip install cupy-cuda12x --force-reinstall
```

---

## Every run re-embeds everything

The backlink generator and synonym linker cache embeddings by
`(path, mtime)`. Writes from Phase 3 / Phase 4 change mtimes, so the
next Phase 2 run would see all notes as "modified" unless we refresh the
cache after writes.

Umbra does this automatically — `build_embeddings_incremental` saves a
pre-write cache, the linker writes, then we re-scan mtimes and save a
post-write cache. If you're hand-editing notes between phases,
re-running will correctly re-embed only what actually changed.

If you suspect cache corruption:

```bash
umbra semantic --rebuild     # re-embed from scratch
umbra synonyms --rebuild
```

---

## Phase 3 keeps linking generic English words

The specificity filter in `keyword_linker.is_specific_keyword` rejects
single lowercase English words. It should already keep your index clean.
If you're still seeing junk links, check:

1. Notes with stems like `Code`, `Images`, `Money`, `Data` — these fail
   the filter and are NOT indexed. If they show up as link targets,
   your vault has a duplicate with different casing.
2. The `STOP_WORDS` set in `src/umbra/keyword_linker.py`. Add your own
   project-specific stopwords there and reinstall.

To inspect what's actually indexed:

```bash
umbra keywords --stats | less
```

---

## Phase 4 clusters are dominated by one mega-cluster

Tune `hdbscan_epsilon` downward (tighter clusters):

```yaml
hdbscan_epsilon: 0.25       # was 0.35
```

Or raise `max_cluster_full_crosslink` so more clusters get full
cross-linking instead of collapsing to hub/spoke.

Inspect cluster assignments:

```bash
umbra synonyms --stats
python -c "import pickle; print(pickle.load(open('~/.obsidian-umbra/cache/synonym_clusters.pickle','rb')))"
```

---

## Pipeline trashed my daily note formatting

Shouldn't happen — Umbra only writes between `<!-- umbra: ... -->`
markers. If you hand-edited inside a marker block, the next run will
overwrite it.

If you see legit damage, open an issue with:
- The original note text (pre-Umbra)
- The damaged note text (post-Umbra)
- Which phase ran (check `state_dir/logs/*.log`)

---

## "No new or modified daily notes"

Phase 1 tracks `state.json`. If you want to reprocess everything:

```bash
rm ~/.obsidian-umbra/daily_splitter_state.json
umbra split
```

Or for a one-off:

```bash
umbra split --all
```

---

## GPU OOM

- 24GB VRAM is comfortable for Qwen3-4B + GTE-large + Potion-32M.
- 12GB is tight. If OOM, point `cuda_visible_devices` at a specific GPU
  and run phases sequentially rather than parallel.
- Reduce `n_ctx` to 8192 if loading Qwen3 itself OOMs.
