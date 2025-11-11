# Slurm Discord Monitor

Multi-job Slurm monitoring with real-time Discord notifications.

## Installation

Requirements: [uv](https://uv.run) (version >= 1.4.0)

```bash
# Clone the repo
git clone slurm-jobs-monitor
cd slurm-jobs-monitor

# Install with uv and just test the hello world monitor
uv run hello-monitor
```


## Quick Start

This program just needs to be in an entry node of the Slurm-manged cluster.

```bash
# Monitor a single job that checks every 30 seconds
uv run slurmonitor 12345 --check-interval 30

# Add periodic updates every 1800 seconds
uv run slurmonitor 12345 \
    --periodic-updates --update-interval 1800

# Monitor multiple jobs
uv run slurmonitor 12345 12346 12347
```


## Setup instructions

### Create a Discord webhook

1. Create a private Discord server
2. Server Settings -> Integrations -> Webhooks and click "New Webhook"
3. Place the webhook in `assets/my_webhook_url.txt` (will be ignored by git)

### Run in a persistent session

Use `tmux` to run the monitor in a persistent session:
```bash
tmux new -s slurmonitor
uv run slurmonitor 12345
# Detach with Ctrl+b d

# To re-attach later:
tmux attach -t slurmonitor

# Close the session when done:
tmux kill-session -t slurmonitor
```

### Run a test

Run a simple test (you should see Discord notifications and the job running in the cluster):
```bash
# Run the test
uv run tests/test_slurm_monitor.py
```

Run one more test:
```bash
# Launch a job
chmod +x tests/dummy.sh
sbatch tests/dummy.sh

# Monitor the job (replace JOB_ID with the actual job ID)
uv run slurmonitor JOB_ID --check-interval 15 --periodic-updates --update-interval 60
```


## Enhancements

- [ ] Use rich tables for better CLI readability
- [ ] Extract other infos from the job (job-name, user, etc.) and include them in the notifications
- [ ] Add screenshots here in the docs that show the monitor in action
