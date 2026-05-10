#!/usr/bin/env bash
# Submit the miniAgent backend as a SLURM GPU job.
# Usage: bash start-backend-slurm.sh
# The job prints the compute-node hostname so you can SSH-tunnel to port 8002.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

sbatch <<EOF
#!/usr/bin/env bash
#SBATCH --job-name=miniAgent-backend
#SBATCH --partition=gpu-h200
#SBATCH --gres=gpu:1
#SBATCH --cpus-per-task=4
#SBATCH --mem=16G
#SBATCH --time=08:00:00
#SBATCH --output=${SCRIPT_DIR}/logs/backend-slurm-%j.log
#SBATCH --error=${SCRIPT_DIR}/logs/backend-slurm-%j.log

echo "=== miniAgent backend starting on \$(hostname) at \$(date) ==="
echo "Job ID: \$SLURM_JOB_ID"
echo ""
echo "To forward port 8002 to your local machine, run:"
echo "  ssh -N -L 8002:\$(hostname):8002 \$USER@\$(hostname -f | sed 's/[^.]*\.//')"
echo ""

source /gpfs/software/miniforge3/25.3.1-3/etc/profile.d/conda.sh
conda activate miniAgent

cd "${SCRIPT_DIR}/backend"
exec uvicorn app:app --port 8002 --host 0.0.0.0 --reload
EOF
