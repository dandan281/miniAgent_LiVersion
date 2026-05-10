#!/bin/bash
# Wait for batch 2 to finish (rl_loop.py process exits), then launch batch 3 + batch 4.
# Each batch logs to its own file. Regenerates dossiers between batches.

cd /gpfs/scrubbed/danlovuw/miniAgent
PY=.py311/bin/python3.11

echo "[$(date +%H:%M:%S)] Waiting for batch 2 to finish..."
while pgrep -f "rl_loop.py.*overnight_batch2" > /dev/null; do
    sleep 30
done
echo "[$(date +%H:%M:%S)] Batch 2 finished. Regenerating dossiers..."
$PY backend/scripts/generate_dossiers.py --clean > /tmp/dossier_after_batch2.log 2>&1

echo "[$(date +%H:%M:%S)] Launching batch 3 (linker variants)..."
$PY -u backend/scripts/rl_loop.py \
    --mode full \
    --input backend/knowledge/overnight_batch3_linkers.json \
    --iterations 1 \
    --timeout 900 > /tmp/rl_batch3.log 2>&1

echo "[$(date +%H:%M:%S)] Batch 3 finished. Regenerating dossiers..."
$PY backend/scripts/generate_dossiers.py --clean > /tmp/dossier_after_batch3.log 2>&1

echo "[$(date +%H:%M:%S)] Launching batch 4 (IL6ST-focused)..."
$PY -u backend/scripts/rl_loop.py \
    --mode full \
    --input backend/knowledge/overnight_batch4_il6st.json \
    --iterations 1 \
    --timeout 900 > /tmp/rl_batch4.log 2>&1

echo "[$(date +%H:%M:%S)] Batch 4 finished. Regenerating final dossiers..."
$PY backend/scripts/generate_dossiers.py --clean > /tmp/dossier_final.log 2>&1

echo "[$(date +%H:%M:%S)] All batches complete."
touch /tmp/rl_overnight_complete.flag
