#! /bin/bash

#SBATCH --job-name=monitor_test
#SBATCH --time=00:10:00
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=1

#SBATCH --output=logs/slurm_test_%j.out
#SBATCH --error=logs/slurm_test_%j.err

# Python env
uv sync
source .venv/bin/activate

# Sanity check
which python
python --version

# Start the job
echo "Starting dummy job with SLURM_JOB_ID: $SLURM_JOB_ID"
echo "Job started on: $(date)"

uv run "tests/dummy.py"