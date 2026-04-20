# Plato's Cave demo vault

A realistic example vault: a philosophy grad student's notes on Plato's
*Allegory of the Cave*. Seeded with 50 real paper references pulled from
OpenAlex (see `plato_cave_records.tsv`).

## Structure

```
examples/
├── before/                        22 daily notes + 24 topic notes, untouched
├── after/                         Same vault, post-Umbra pipeline
├── plato_cave_records.tsv         Real OpenAlex citations (tab-separated)
├── umbra-demo-config.yaml         Config used to generate `after/`
└── README.md                      You are here
```

## Reproduce

```bash
# From repo root
cp -r examples/before /tmp/plato-vault
cat > /tmp/plato-config.yaml <<EOF
vault: /tmp/plato-vault
model_path: ~/models/Qwen3-4B-Instruct-2507-Q8_0.gguf
output_subdir: umbra
state_dir: /tmp/.umbra-state
cuda_visible_devices: "0"
EOF
UMBRA_CONFIG=/tmp/plato-config.yaml python -m umbra.cli all
```

Should take ~10 minutes on a 4090: ~8 min for Phase 1 (22 daily notes
through Qwen3-4B), <1 min for Phases 2-4 combined.

## What to look for

- `examples/after/umbra/` — **~70 generated topic notes** with YAML
  frontmatter, H1 titles, source backlinks
- `examples/after/01-15-2024.md` — **original daily note** now has
  inline `[[Form of the Good]]` and `[[Divided Line]]` links, plus
  `## Topics` and `## Related Notes` sections
- `examples/after/Concepts/Allegory of the Cave.md` — **topic note**
  with `## Related Notes` (semantic neighbors) and `## Same Concept`
  (synonym cluster)
- `examples/after/umbra/NOTE_INDEX.md` — **master catalog** of all
  108+ notes organized by folder

## Sample diff

```bash
diff examples/before/01-15-2024.md examples/after/01-15-2024.md
```

