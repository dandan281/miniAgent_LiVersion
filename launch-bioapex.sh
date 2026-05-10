#!/usr/bin/env bash
# Launch BioAPEX (backend + frontend) as a SLURM GPU job.
# Usage: bash launch-bioapex.sh

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONDA_ENV="/gpfs/home/danlovuw/.conda/envs/miniAgent"
API_PORT=8022
WEB_PORT=3022

mkdir -p "${SCRIPT_DIR}/logs"

sbatch <<EOF
#!/usr/bin/env bash
#SBATCH --job-name=bioapex
#SBATCH --partition=gpu-h200
#SBATCH --gres=gpu:1
#SBATCH --cpus-per-task=4
#SBATCH --mem=16G
#SBATCH --time=08:00:00
#SBATCH --output=${SCRIPT_DIR}/logs/bioapex-%j.log
#SBATCH --error=${SCRIPT_DIR}/logs/bioapex-%j.log

NODE=\$(hostname -s)
echo "================================================"
echo " BioAPEX starting on \$NODE at \$(date)"
echo " Job: \$SLURM_JOB_ID"
echo "================================================"
echo "Run this on your LOCAL machine:"
echo "  ssh -N -L ${WEB_PORT}:\$NODE:${WEB_PORT} danlovuw@tillicum.hyak.uw.edu"
echo "Then open: http://localhost:${WEB_PORT}"
echo "================================================"

source /gpfs/software/miniforge3/25.3.1-3/etc/profile.d/conda.sh
conda activate miniAgent

# Start backend in background
cd "${SCRIPT_DIR}/backend"
uvicorn app:app --host 0.0.0.0 --port ${API_PORT} >"${SCRIPT_DIR}/logs/backend-\$SLURM_JOB_ID.log" 2>&1 &
BACKEND_PID=\$!
echo "Backend PID: \$BACKEND_PID"

# Start frontend in background
cd "${SCRIPT_DIR}/frontend"
NEXT_PUBLIC_API_PORT=${API_PORT} NEXT_DIST_DIR=.next-slurm node node_modules/next/dist/bin/next dev --hostname 0.0.0.0 --port ${WEB_PORT} >"${SCRIPT_DIR}/logs/frontend-\$SLURM_JOB_ID.log" 2>&1 &
FRONTEND_PID=\$!
echo "Frontend PID: \$FRONTEND_PID"

echo "Waiting for services..."
wait \$BACKEND_PID \$FRONTEND_PID
EOF
