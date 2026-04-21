<p align="center">
  <img src="docs/assets/logo.png" alt="Obsidian Umbra" width="320">
</p>

<p align="center">
  <strong>A local pipeline that turns years of daily Obsidian notes into a Zettelkasten graph. Nothing leaves your machine.</strong>
</p>

<p align="center">
  <a href="#quick-start">Quick start</a> ·
  <a href="#how-it-works">How it works</a> ·
  <a href="#before-and-after">Before and after</a> ·
  <a href="docs/phases.md">Phases</a> ·
  <a href="docs/models.md">Models</a> ·
  <a href="docs/troubleshooting.md">Troubleshooting</a>
</p>

<p align="center">
  <a href="https://pypi.org/project/obsidian-umbra/"><img src="https://img.shields.io/pypi/v/obsidian-umbra.svg?style=flat-square&color=7c3aed" alt="PyPI version"></a>
  <img src="https://img.shields.io/pypi/pyversions/obsidian-umbra.svg?style=flat-square" alt="Python versions">
  <img src="https://img.shields.io/badge/Obsidian-0.16+-7c3aed?style=flat-square&logo=obsidian" alt="Obsidian">
  <img src="https://img.shields.io/badge/Models-Qwen%20%7C%20Llama%203%20%7C%20Mistral%20%7C%20Gemma-ff6b35?style=flat-square" alt="Supported models">
  <img src="https://img.shields.io/badge/NVIDIA-CUDA%2012+-76b900?style=flat-square&logo=nvidia" alt="NVIDIA CUDA">
  <img src="https://img.shields.io/badge/License-MIT-blue?style=flat-square" alt="License">
  <a href="https://paypal.me/jimnoneill"><img src="https://img.shields.io/badge/Donate-PayPal-00457C?style=flat-square&logo=paypal" alt="Donate via PayPal"></a>
</p>

---

## Why

Obsidian's graph view is only as rich as the `[[wikilinks]]` you remembered
to write at the time. After a few hundred daily notes the graph is mostly
islands. There are plenty of "second brain" tools that fix that by sending
every note to a cloud API, which is a hard no if you journal about anything
personal. Umbra does the same work on your own machine.

It reads your daily notes, asks a local LLM to pull out distinct topics,
creates one titled note per topic, and then weaves four kinds of links
across the whole vault so the graph actually connects.

```
  OBSIDIAN VAULT                        LOCAL GPU

  daily notes                           Qwen3-4B-Instruct (topic split)
  project notes      <--  file I/O -->  Potion-32M (semantic neighbors)
  folder tree                           GTE-large + HDBSCAN (synonyms)

  graph of [[wikilinks]]                nothing leaves your machine
```

## Quick start

You need Linux with an NVIDIA GPU (12GB VRAM is enough for the Q4 model,
24GB gives you Q8 quality), CUDA 12 or newer, Python 3.10 or newer, and a
recent Obsidian build.

Install from PyPI:

```bash
pip install obsidian-umbra
```

Or from `main` if you want the latest:

```bash
git clone https://github.com/jimnoneill/obsidian-umbra
cd obsidian-umbra
pip install -e .
```

Download the model. The default is Qwen3-4B-Instruct Q8 (4.3 GB, best
quality on a 24GB+ card):

```bash
mkdir -p ~/models
huggingface-cli download Qwen/Qwen3-4B-Instruct-2507-GGUF \
  Qwen3-4B-Instruct-2507-Q8_0.gguf --local-dir ~/models
```

If you only have 12GB VRAM, swap in Q4_K_M (2.5 GB) which is indistinguishable
in practice for this workload. Any GGUF instruct model works. Llama 3,
Mistral, Gemma, and Phi-3 are all fine. [docs/models.md](docs/models.md)
has the compatibility matrix.

Copy the example config and edit it to point at your vault and model:

```bash
cp config.yaml.example config.yaml
```

```yaml
vault: ~/Documents/MyVault
model_path: ~/models/Qwen3-4B-Instruct-2507-Q8_0.gguf
model_name: Qwen3-4B-Instruct-2507
chat_format: chatml
output_subdir: umbra
state_dir: ~/.obsidian-umbra
cuda_visible_devices: "0"
```

Then run the whole pipeline:

```bash
./deploy.sh all
```

On a large vault the first run takes roughly two minutes per fifty daily
notes for the LLM pass, plus about a minute for the other three phases
combined. Every subsequent run is idempotent and finishes in seconds.

If you want it to keep up with new journal entries automatically:

```bash
(crontab -l 2>/dev/null; echo "0 4 * * *  $PWD/deploy.sh all") | crontab -
```

## How it works

Four phases run in sequence. Each one is idempotent and can be run on its
own. The important thing is that none of them overwrite your prose. Every
section Umbra writes is bracketed by an `<!-- umbra: ... -->` marker pair,
and re-runs only touch the content inside those brackets.

The **daily splitter** reads each daily note, filenames in the form
`MM-DD-YYYY.md` or `YYYY-MM-DD.md`. It calls the local LLM in JSON mode,
asks for the distinct topics, and writes one titled topic note per result
with YAML frontmatter and a backlink to the source daily.

The **semantic backlinks** phase embeds every note in your vault with
Potion-32M, a 256-dimensional static embedding that runs on CPU in under
a second for a thousand notes. It computes pairwise cosine similarity,
adds a small tag-overlap bonus, and writes a `## Related Notes` section
with the top five hits and their similarity percentages.

The **keyword linker** is the one that actually lights up the graph. It
builds an index of note stems, titles, and folder names, then scans every
note for body-text mentions of those names and wraps them in `[[wikilinks]]`.
It skips YAML, code fences, existing links, headings, URLs, and HTML
comments. Single-word keywords have to pass a specificity test (CamelCase,
acronym, or digit-bearing) so common English words like "money" and "code"
don't get linked to random notes.

The **synonym linker** handles the case where you wrote about the same
concept on three different days with three different words. It embeds
concept-note titles with GTE-large (1024-dim), clusters them with cuML
HDBSCAN, and writes a `## Same Concept` section between cluster siblings.
Mega-clusters larger than twenty members collapse to a hub-and-spoke
pattern: every member links to the centroid-closest representative, and
the representative gets links to its top five nearest neighbors, so
recurring project themes don't get buried in a 29-item list.

## Before and after

The repo ships a demo vault based on a made-up grad student's notes on
Plato's Allegory of the Cave. 22 daily entries, 24 topic notes, seeded
with real OpenAlex paper references. To see what Umbra actually does,
diff one daily note:

```bash
diff examples/before/01-15-2024.md examples/after/01-15-2024.md
```

The same entry before and after. Start with the original:

```markdown
Distracted day. Reading around the edges.

Thought experiment: what if the cave is literally about sensory
perception vs. mathematical knowledge? The shadows are sense-data.
The puppets are physical objects. The sun is the Form of the Good.

Then the ascent tracks: aisthesis → doxa → dianoia → noesis. The
divided line literally fits inside the cave.
```

After the pipeline:

```markdown
Distracted day. Reading around the edges.

Thought experiment: what if the cave is literally about sensory
perception vs. mathematical knowledge? The shadows are sense-data.
The puppets are physical objects. The sun is the [[Form of the Good|Form of the Good]].

Then the ascent tracks: aisthesis → doxa → dianoia → noesis. The
[[Divided Line|divided line]] literally fits inside the cave.

<!-- umbra: generated topic links -->
## Topics
- [[cave-sensory-perception-mathematical-knowledge-2024-01-15|Cave as Narrative of Sensory vs Mathematical Knowledge]] #plato #allegory #perception
- [[plato-revee-intro-comparison-2024-01-15|Reeve's Intro Offers Similar Framework]] #reeve #plato

<!-- umbra: related notes -->
## Related Notes
- [[cave-sensory-perception-mathematical-knowledge-2024-01-15|Cave as Narrative of Sensory vs Mathematical Knowledge]] (93%)
- [[01-08-2024|01-08-2024]] (81%)
- [[01-28-2024|01-28-2024]] (80%)
- [[plato-cave-epistemic-contexts-2024-01-28|The Cave as Epistemic Context Shift]] (77%)
```

The original prose is untouched. Two inline wikilinks, a generated
topic-links section, and a related-notes section got appended. Browse
`examples/after/` for the rest: generated topic notes, hub-spoke
synonym clusters, and the auto-built `NOTE_INDEX.md`.

## Commands

```bash
./deploy.sh install     # pip install -e .
./deploy.sh all         # run phases 1 through 4
./deploy.sh split       # phase 1, daily note splitter
./deploy.sh semantic    # phase 2, semantic backlinks
./deploy.sh keywords    # phase 3, keyword linker
./deploy.sh synonyms    # phase 4, synonym clustering
./deploy.sh status      # tail each phase's log
./deploy.sh logs        # live-tail all logs
./deploy.sh help        # show all commands
```

Each phase also takes its own flags (`--dry-run`, `--rebuild`, `--one PATH`,
`--stats`). Pass them after the phase name:

```bash
./deploy.sh split --dry-run --since 2024-06-01
./deploy.sh synonyms --stats
```

## Documentation

The detailed per-phase walkthrough is in [docs/phases.md](docs/phases.md).
The model compatibility matrix and the Q4 vs Q8 recommendation is in
[docs/models.md](docs/models.md). Every config key is documented in
[docs/configuration.md](docs/configuration.md). Common failure modes are
in [docs/troubleshooting.md](docs/troubleshooting.md), and if you'd rather
run the phases by hand [docs/manual-setup.md](docs/manual-setup.md) shows
that path. Maintainer SemVer release process lives in
[docs/releasing.md](docs/releasing.md) with the version history in
[CHANGELOG.md](CHANGELOG.md).

## When something goes wrong

| Symptom | Likely cause |
|---|---|
| `llama-cpp-python` won't build with CUDA | Needs `CMAKE_ARGS="-DGGML_CUDA=on"` |
| `cuml` import fails | pip wheels are unreliable; install from RAPIDS conda |
| Every run re-embeds everything | Mtime cache went stale, try `--rebuild` |
| Phase 3 linked "money" or "code" | Specificity filter isn't catching a duplicate note |
| Phase 4 produced one giant cluster | Tune `max_cluster_full_crosslink` down |

Full fixes in [docs/troubleshooting.md](docs/troubleshooting.md).

## Requirements

Obsidian 0.16 or newer. Python 3.10+. NVIDIA driver 525+ for CUDA 12.
`llama-cpp-python` 0.3.0+, built with `GGML_CUDA=on` for real speed.
`sentence-transformers` 3.0+ (pulls GTE-large on first run, about 500MB).
`model2vec` 0.3.0+ (Potion-32M, 40MB). `cuml` matching your CUDA, for
HDBSCAN on GPU.

## Support

If Umbra saved you from hand-wikilinking a decade of journal entries,
contributions toward continued work are welcome.

<p>
  <a href="https://paypal.me/jimnoneill"><img src="https://img.shields.io/badge/Donate-PayPal-00457C?style=for-the-badge&logo=paypal" alt="Donate via PayPal"></a>
</p>

## License

MIT, 2026.
