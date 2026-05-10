#!/bin/bash
# Auto-runs the batch queue sequentially. Each batch logs to its own file.
# After all batches finish, regenerates dossiers and writes a summary.

set -e
cd /gpfs/scrubbed/danlovuw/miniAgent

PY=.py311/bin/python3.11
LOG_DIR=/tmp/rl_batches
mkdir -p $LOG_DIR

# The batches in execution order. Skip any batch already running.
BATCHES=(
    "batch3_linkers:backend/knowledge/overnight_batch3_linkers.json"
    "batch4_il6st:backend/knowledge/overnight_batch4_il6st.json"
)

for BATCH in "${BATCHES[@]}"; do
    NAME="${BATCH%%:*}"
    INPUT="${BATCH##*:}"
    LOG="$LOG_DIR/${NAME}.log"
    echo "[$(date +%H:%M:%S)] Starting $NAME (input: $INPUT, log: $LOG)"
    $PY -u backend/scripts/rl_loop.py \
        --mode full \
        --input "$INPUT" \
        --iterations 1 \
        --timeout 900 > "$LOG" 2>&1
    echo "[$(date +%H:%M:%S)] Finished $NAME"

    # Regenerate dossiers after each batch
    $PY backend/scripts/generate_dossiers.py --clean > /dev/null 2>&1
done

# Final summary
$PY backend/scripts/generate_dossiers.py --clean > /dev/null 2>&1
echo "[$(date +%H:%M:%S)] All batches complete."
