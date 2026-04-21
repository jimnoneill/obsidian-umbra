# Models

Umbra's Phase 1 (daily splitter) is the only phase that needs a generative
LLM. Any GGUF instruct model that llama-cpp-python can load will work —
the pipeline asks it for JSON output, so instruction-following quality
matters more than size.

## Recommended models

| Model | Size (Q4_K_M) | Size (Q8_0) | VRAM (Q4_K_M) | VRAM (Q8_0) | chat_format |
|-------|---------------|-------------|---------------|-------------|-------------|
| **Qwen3-4B-Instruct-2507** (default) | 2.5 GB | 4.3 GB | ~4 GB | ~6 GB | `chatml` |
| Qwen2.5-7B-Instruct | 4.5 GB | 7.6 GB | ~6 GB | ~10 GB | `chatml` |
| Llama-3.1-8B-Instruct | 4.9 GB | 8.5 GB | ~6 GB | ~10 GB | `llama-3` |
| Mistral-7B-Instruct-v0.3 | 4.4 GB | 7.7 GB | ~6 GB | ~9 GB | `mistral-instruct` |
| Gemma-2-9B-Instruct | 5.8 GB | 9.8 GB | ~8 GB | ~12 GB | `gemma` |
| Phi-3.5-mini-Instruct | 2.4 GB | 4.1 GB | ~3 GB | ~5 GB | `phi-3` |

VRAM figures assume `n_ctx: 16384` and include KV cache. Halve VRAM and
context window on a 12GB card.

## Quantization: Q4_K_M vs Q8_0

| Quant | File size | Quality | When to use |
|-------|-----------|---------|-------------|
| **Q4_K_M** | Smallest | ~95% of full | 12GB VRAM, laptops, CPU-only |
| Q5_K_M | Medium | ~97% of full | Nice middle ground |
| **Q8_0** | Large | ~99% of full | 24GB+ VRAM, quality-critical |
| FP16 | Full | 100% | Development only — you don't need this |

Umbra's JSON-mode prompting is forgiving — **Q4_K_M works fine** for
almost all vaults. Only bump to Q8 if you see topic-extraction quality
regressions.

## Download

Hugging Face hosts GGUF builds of every model listed above. For Qwen's
official Q8 (the default):

```bash
mkdir -p ~/models
huggingface-cli download Qwen/Qwen3-4B-Instruct-2507-GGUF \
  Qwen3-4B-Instruct-2507-Q8_0.gguf \
  --local-dir ~/models
```

For Q4_K_M (half the size):

```bash
huggingface-cli download Qwen/Qwen3-4B-Instruct-2507-GGUF \
  Qwen3-4B-Instruct-2507-Q4_K_M.gguf \
  --local-dir ~/models
```

Or direct `wget` from the HF resolve URL — any source works, Umbra only
cares that the path exists.

## Switching models

Point `model_path` at your new GGUF in `config.yaml`, and update
`chat_format` to match the model family:

```yaml
model_path: ~/models/Meta-Llama-3.1-8B-Instruct-Q4_K_M.gguf
model_name: Llama-3.1-8B-Instruct
chat_format: llama-3
```

The full list of chat formats llama-cpp-python recognizes:
https://github.com/abetlen/llama-cpp-python/blob/main/llama_cpp/llama_chat_format.py

If `chat_format: null` is set, llama-cpp will fall back to whatever
template is embedded in the GGUF's metadata — usually correct for
official releases.

## CPU-only mode

Set `n_gpu_layers: 0` and (optionally) `n_threads` to your physical
core count. Expect ~10-30× slower Phase 1 runs but everything else
(Phase 2 embeddings, Phase 3 keyword matching, Phase 4 clustering)
is either CPU-fast or can be re-pointed to CPU if you install CPU
builds of cuml / cupy.

Phases 2 & 3 work on CPU out of the box. Phase 4 needs cuML HDBSCAN,
which requires GPU — or swap in `sklearn.cluster.HDBSCAN` if you
don't have one. Contributions welcome.
