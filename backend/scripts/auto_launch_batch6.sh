#!/bin/bash
# Wait for batch 5 to finish, then launch batch 6.

cd /gpfs/scrubbed/danlovuw/miniAgent
PY=.py311/bin/python3.11

echo "[$(date +%H:%M:%S)] Waiting for batch 5 to finish..."
while pgrep -f "rl_loop.py.*overnight_batch5" > /dev/null; do
    sleep 30
done
echo "[$(date +%H:%M:%S)] Batch 5 finished. Regenerating dossiers..."
$PY backend/scripts/generate_dossiers.py --clean > /tmp/dossier_after_batch5.log 2>&1

echo "[$(date +%H:%M:%S)] Launching batch 6 (re-tests + new combos)..."
$PY -u backend/scripts/rl_loop.py \
    --mode full \
    --input backend/knowledge/overnight_batch6_retests.json \
    --iterations 1 \
    --timeout 900 > /tmp/rl_batch6.log 2>&1

echo "[$(date +%H:%M:%S)] Batch 6 finished. Final dossiers..."
$PY backend/scripts/generate_dossiers.py --clean > /tmp/dossier_final2.log 2>&1
touch /tmp/rl_batch6_complete.flag
echo "[$(date +%H:%M:%S)] Done."
