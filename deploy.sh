#!/usr/bin/env bash
# obsidian-umbra — one-shot runner for cron or manual
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG="${UMBRA_CONFIG:-$HERE/config.yaml}"

usage() {
    cat <<EOF
Usage: ./deploy.sh <command>

Commands:
  install    Install Python deps (pip install -e .)
  all        Run Phase 1 → 2 → 3 → 4 sequentially
  split      Phase 1 — daily note splitter (needs local LLM)
  semantic   Phase 2 — semantic backlinks (Potion-32M)
  keywords   Phase 3 — keyword linker (no model)
  synonyms   Phase 4 — synonym clustering (GTE-large + HDBSCAN)
  status     Show latest log lines for each phase
  logs       Tail the combined cron log
  help       Show this help
EOF
}

CMD="${1:-help}"

case "$CMD" in
    install)
        pip install -e "$HERE"
        ;;
    all)
        UMBRA_CONFIG="$CONFIG" python -m umbra.cli all
        ;;
    split|semantic|keywords|synonyms)
        UMBRA_CONFIG="$CONFIG" python -m umbra.cli "$CMD" "${@:2}"
        ;;
    status)
        STATE_DIR="${UMBRA_STATE_DIR:-$HOME/.obsidian-umbra}"
        for log in daily_splitter semantic_backlinks keyword_linker synonym_linker; do
            echo "=== $log ==="
            tail -n 3 "$STATE_DIR/logs/$log.log" 2>/dev/null || echo "  (no log yet)"
        done
        ;;
    logs)
        STATE_DIR="${UMBRA_STATE_DIR:-$HOME/.obsidian-umbra}"
        tail -f "$STATE_DIR/logs"/*.log
        ;;
    help|--help|-h)
        usage
        ;;
    *)
        echo "Unknown command: $CMD"
        usage
        exit 1
        ;;
esac
