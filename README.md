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

1. Create a private Discord server
2. In the server add a webhook from the integrations section (that will automatically create a bot)
3. Place the webhook in `assets/my_webhook_url.txt` (will be ignored by git)

```bash
# Monitor a single job
uv run slurmonitor 12345
```

