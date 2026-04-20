# Manual Setup

If `deploy.sh` isn't your style, or you want cron-level control.

---

## 1. Clone & Install

```bash
git clone https://github.com/jimnoneill/obsidian-umbra
cd obsidian-umbra
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

## 2. Install CUDA-aware deps

(See [troubleshooting](troubleshooting.md) for CUDA-specific build flags.)

```bash
# Build llama-cpp-python with CUDA
CMAKE_ARGS="-DGGML_CUDA=on -DCMAKE_CUDA_ARCHITECTURES=89" \
pip install llama-cpp-python --force-reinstall --no-cache-dir

# cupy + cuml — prefer conda
conda install -c rapidsai -c conda-forge -c nvidia rapids=24.04 cuda-version=12.0
```

## 3. Download the LLM

```bash
mkdir -p ~/models
huggingface-cli download Qwen/Qwen3-4B-Instruct-2507-GGUF \
  Qwen3-4B-Instruct-2507-Q8_0.gguf \
  --local-dir ~/models
```

## 4. Write config

```bash
cat > config.yaml <<EOF
vault: ~/Documents/MyVault
model_path: ~/models/Qwen3-4B-Instruct-2507-Q8_0.gguf
output_subdir: umbra
state_dir: ~/.obsidian-umbra
cuda_visible_devices: "0"
EOF
```

## 5. Run phases individually

```bash
python -m umbra.cli split
python -m umbra.cli semantic
python -m umbra.cli keywords
python -m umbra.cli synonyms
```

Or:

```bash
python -m umbra.cli all
```

## 6. Cron

```bash
crontab -e
```

Add:

```
0 4 * * *   UMBRA_CONFIG=/path/to/config.yaml /path/to/.venv/bin/python -m umbra.cli all >> /path/to/umbra.log 2>&1
```

---

## Running against a different vault temporarily

```bash
UMBRA_VAULT=/tmp/test-vault UMBRA_STATE_DIR=/tmp/test-state \
  python -m umbra.cli all
```
