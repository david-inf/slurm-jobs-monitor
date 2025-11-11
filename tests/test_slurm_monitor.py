"""
Testing Slurm jobs monitoring
- Creates a temporary Python script that runs for a short duration
- Submits it as a Slurm job
- Monitors the job status changes through completion
- Cleans up the job and temporary files afterward
"""

from slurmonitor.core import MultiJobMonitor

from pathlib import Path
import subprocess
import time
import os
from rich.console import Console

console = Console()

DUMMY_PY = """
import time
import sys

# Force unbuffered output so prints appear immediately in Slurm output files
print("Dummy job started", flush=True)
print(f"Running on node: {sys.platform}", flush=True)

# Simulate some work
for i in range(6):
    print(f"Progress: {i*20}%", flush=True)
    time.sleep(10)

print("Dummy job completed successfully", flush=True)
"""

DUMMY_BATCH = """#!/bin/bash
#SBATCH --job-name=monitor_test
#SBATCH --output=slurm_test_%j.out
#SBATCH --error=slurm_test_%j.err
#SBATCH --time=00:10:00
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=1

# Run Python with unbuffered output (-u flag)
# This ensures prints appear immediately in the output file
python3 -u {script_path}
"""


def test_slurm_monitor():
    """Testing the job monitoring on a dummy Slurm job"""

    # Step 1: Load Discord webhook URL
    webhook_path: Path = Path("assets/my_webhook_url.txt")
    if not webhook_path.is_file():
        console.print(f"[red]Error:[/red] Discord webhook file '{webhook_path}' not found.")
        return

    with open(webhook_path, 'r', encoding='utf-8') as f:
        discord_webhook = f.read().strip()
    console.print("✓ Retrieved webhook URL")

    # Step 2: Create a temporary Python script that will be our dummy job
    # This script just sleeps to simulate work
    # IMPORTANT: Create in current directory (not /tmp) so Slurm compute nodes can access it
    cwd = Path.cwd()

    # Create the script file
    script_path = cwd / f"slurm_test_job_{int(time.time())}.py"
    with open(script_path, 'w') as tmp_script:
        tmp_script.write(DUMMY_PY)
    # Make the script executable
    os.chmod(script_path, 0o755)
    console.print(f"✓ Created temporary script: {script_path}")

    # Step 3: Create a Slurm batch script
    # Use absolute path to ensure Slurm can find it
    batch_path = cwd / f"slurm_test_batch_{int(time.time())}.sh"
    with open(batch_path, 'w') as tmp_batch:
        tmp_batch.write(DUMMY_BATCH.format(script_path=script_path.absolute()))
    # Make the batch script executable
    os.chmod(batch_path, 0o755)
    console.print(f"✓ Created Slurm batch script: {batch_path}")

    # Step 4: Submit the job to Slurm
    try:
        result = subprocess.run(
            ['sbatch', batch_path], capture_output=True, text=True, timeout=10)

        if result.returncode != 0:
            console.print(f"[red]Error:[/red] Failed to submit job: {result.stderr}")
            # Clean up temp files
            Path(script_path).unlink(missing_ok=True)
            Path(batch_path).unlink(missing_ok=True)
            return

        # Extract job ID from sbatch output (format: "Submitted batch job 12345")
        output = result.stdout.strip()
        job_id = output.split()[-1]
        console.print(f"✓ Submitted job with ID: [bold green]{job_id}[/bold green]")

    except FileNotFoundError:
        console.print("[red]Error:[/red] 'sbatch' command not found. Is Slurm installed?")
        Path(script_path).unlink(missing_ok=True)
        Path(batch_path).unlink(missing_ok=True)
        return
    except Exception as e:
        console.print(f"[red]Error:[/red] Failed to submit job: {e}")
        Path(script_path).unlink(missing_ok=True)
        Path(batch_path).unlink(missing_ok=True)
        return

    # Step 5: Set up monitoring using MultiJobMonitor
    # Use a short check interval for testing
    console.print("\n🔍 Starting job monitor...")
    monitor = MultiJobMonitor(
        discord_webhook=discord_webhook,
        check_interval=5,
        periodic_updates=True,
        update_interval=30
    )

    # Add the job to monitor
    monitor.add_job(job_id)

    # Step 6: Wait for the job to complete (with timeout)
    # NOTE: We don't call monitor.start() here because:
    # 1. The monitoring thread is already running (started by add_job())
    # 2. monitor.start() blocks forever in an infinite loop
    # 3. For testing, we just need to wait for the job to finish
    console.print("⏳ Monitoring job progress...")

    # NOTE: normally we would wait indefinitely, but for testing we set a max wait time
    max_wait_time = 7*60
    start_time = time.time()

    console.print(f"(Will timeout after {max_wait_time} seconds for testing purposes)")
    while time.time() - start_time < max_wait_time:
        # Check if job is still being monitored
        with monitor.lock:
            is_still_monitored = job_id in monitor.monitors

        if not is_still_monitored:
            console.print("✓ Job monitoring completed (job reached terminal state)")
            break

        # console.print(f"  ... Job {job_id} still running (checked at {int(time.time() - start_time)}s)")
        time.sleep(5)
    else:
        console.print("[yellow]Warning:[/yellow] Test timeout reached, stopping monitor")

    # Step 7: Stop monitoring and clean up
    monitor.stop()
    console.print("✓ Monitor stopped")

    # Clean up temporary files
    Path(script_path).unlink(missing_ok=True)
    Path(batch_path).unlink(missing_ok=True)
    console.print("✓ Cleaned up temporary files")

    # Try to clean up Slurm output files (they use the job ID in the name)
    for out_file in Path('.').glob(f'slurm_test_{job_id}.*'):
        out_file.unlink(missing_ok=True)

    console.print("\n[bold green]✓ Test completed successfully![/bold green]")


if __name__ == "__main__":
    test_slurm_monitor()
