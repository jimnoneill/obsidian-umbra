"""Config loader for Obsidian Umbra.

Precedence: CLI args > env vars > config.yaml > defaults.
Paths are expanded with ~ and resolved to absolute.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml


@dataclass
class Config:
    vault: Path                          # Obsidian vault root
    model_path: Path                     # Qwen3-4B-Instruct-2507 GGUF
    output_subdir: str = "umbra"         # where topic notes land (vault/umbra/)
    state_dir: Path = Path("~/.obsidian-umbra").expanduser()
    cuda_visible_devices: str = "0"

    # Phase 1 (daily splitter) ----------------------------------------------
    model_name: str = "Qwen3-4B-Instruct-2507"   # human-readable label in logs
    chat_format: str | None = "chatml"           # llama-cpp chat template name
    n_ctx: int = 16384
    n_gpu_layers: int = -1                        # -1 = all on GPU; 0 = CPU only
    n_threads: int | None = None                  # CPU threads (None = auto)
    temperature: float = 0.2
    max_tokens_per_call: int = 3584
    min_daily_note_chars: int = 80

    # When a new daily-note topic is extracted, check whether an existing
    # topic note covers the same concept and append instead of creating
    # a new file. Match via Potion-32M cosine similarity.
    merge_into_existing_topics: bool = True
    merge_similarity_threshold: float = 0.65
    merge_embed_snippet_len: int = 500
    append_section_heading_format: str = "## Update {date}"

    # Phase 2 (semantic backlinks) ------------------------------------------
    top_k_related: int = 5
    min_similarity: float = 0.30
    tag_bonus: float = 0.05
    tag_bonus_cap: float = 0.15
    embed_snippet_len: int = 800

    # Phase 3 (keyword linker) ----------------------------------------------
    min_keyword_len: int = 3
    max_keyword_passes: int = 10

    # Phase 4 (synonym linker) ----------------------------------------------
    hdbscan_min_cluster_size: int = 2
    hdbscan_min_samples: int = 1
    hdbscan_epsilon: float = 0.35
    hdbscan_method: str = "leaf"
    max_cluster_full_crosslink: int = 20  # bigger → hub/spoke collapse

    # Shared ----------------------------------------------------------------
    skip_dirs: list[str] = field(default_factory=lambda: [
        ".obsidian", ".trash", "Templates",
    ])
    skip_files: list[str] = field(default_factory=lambda: [
        "NOTE_INDEX.md",
    ])

    # Derived
    cache_dir: Path = field(init=False)
    log_dir: Path = field(init=False)

    def __post_init__(self):
        self.vault = Path(self.vault).expanduser().resolve()
        self.model_path = Path(self.model_path).expanduser().resolve()
        self.state_dir = Path(self.state_dir).expanduser().resolve()
        self.cache_dir = self.state_dir / "cache"
        self.log_dir = self.state_dir / "logs"
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.log_dir.mkdir(parents=True, exist_ok=True)


def _merge(target: dict, src: dict) -> dict:
    for k, v in src.items():
        if v is not None:
            target[k] = v
    return target


def load_config(path: str | Path | None = None) -> Config:
    """Load config from YAML + env overrides.

    Default search: ./config.yaml → $UMBRA_CONFIG → ~/.obsidian-umbra/config.yaml
    """
    candidates = []
    if path:
        candidates.append(Path(path))
    if os.environ.get("UMBRA_CONFIG"):
        candidates.append(Path(os.environ["UMBRA_CONFIG"]))
    candidates += [
        Path.cwd() / "config.yaml",
        Path("~/.obsidian-umbra/config.yaml").expanduser(),
    ]

    data: dict = {}
    for p in candidates:
        if p.exists():
            data = yaml.safe_load(p.read_text()) or {}
            data["_loaded_from"] = str(p)
            break

    # Env overrides (UMBRA_VAULT, UMBRA_MODEL_PATH, etc.)
    env_map = {
        "UMBRA_VAULT": "vault",
        "UMBRA_MODEL_PATH": "model_path",
        "UMBRA_OUTPUT_SUBDIR": "output_subdir",
        "UMBRA_STATE_DIR": "state_dir",
        "UMBRA_CUDA_VISIBLE_DEVICES": "cuda_visible_devices",
    }
    for env_key, cfg_key in env_map.items():
        if os.environ.get(env_key):
            data[cfg_key] = os.environ[env_key]

    loaded_from = data.pop("_loaded_from", None)

    if "vault" not in data:
        raise RuntimeError(
            "Config missing 'vault'. Set UMBRA_VAULT env var or create config.yaml "
            "(see config.yaml.example)."
        )
    if "model_path" not in data:
        raise RuntimeError(
            "Config missing 'model_path'. Set UMBRA_MODEL_PATH env var or config.yaml."
        )

    # Filter to known Config fields
    from dataclasses import fields as _fields
    known = {f.name for f in _fields(Config) if f.init}
    clean = {k: v for k, v in data.items() if k in known}
    cfg = Config(**clean)
    cfg._loaded_from = loaded_from  # type: ignore[attr-defined]
    return cfg
