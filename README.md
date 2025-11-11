# Slurm Discord Monitor

Multi-job Slurm monitoring with real-time Discord notifications.

## Installation

```bash
# Clone the repo
git clone slurm-jobs-monitor
cd slurm-jobs-monitor

# Install with uv
uv run hello-monitor
```


## Quick Start

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
