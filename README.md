# Slurm Discord Monitor

You are running jobs on a Slurm-managed cluster and you'd like to know their status when you are outside :smile:

## Installation

Requirements: [uv](https://docs.astral.sh/uv).

```bash
# Clone the repo then move inside
cd slurm-jobs-monitor

# Install with uv and just test the hello world monitor
uv run hello-monitor
```


## Quick Start

This program needs to run on an entry node of the Slurm-managed cluster.

```bash
# Create a config file as described below
# Then run the monitor for the specified job IDs
uv run slurmonitor --config-file ./assets/config.yaml
```

<table>
    <tr>
        <td><img src="assets/monitor_init.png"></td>
        <td><img src="assets/monitor_summary1.png"></td>
        <td><img src="assets/monitor_summary2.png"></td>
        <td><img src="assets/monitor_stop.png"></td>
    </tr>
</table>


## Setup instructions

### Create a Discord webhook

1. Create a private Discord server
2. Server Settings -> Integrations -> Webhooks and click "New Webhook"
3. Create a config file as follows (which includes the webhook) will be ignored by git

```yaml
discord:
  webhook_file: https://discord.com/api/webhooks/...

jobs:
  "12345":
    log_files: [StdOut]
  "12346":
    log_files: [StdOut]

job_status:
  check_interval: 10
  exit_when_done: true

periodic_updates:
  enabled: true
  update_interval: 30
```

Check the full list of options in `assets/config.yaml`.

### Run in a persistent session

Once you have launched the jobs, you can use `tmux` to run the monitor in a persistent session:
```bash
tmux new -s slurmonitor
uv run slurmonitor --config-file ./assets/config.yaml
# Detach with Ctrl+b d (then you can exit the shell safely)

# Check the session
tmux list-sessions  #  you should see slurmonitor running

# To re-attach later:
tmux attach -t slurmonitor

# Close the session when done:
tmux kill-session -t slurmonitor
```

### Run a test

#### Simple tests

Create and fill a custom config file in `tests/test_config.yaml` with your Discord webhook URL and sets other params as needed. Like the following
```yaml
discord:
  webhook: ""  # put here your url

jobs: {}  # this will be updated by the test script

job_status:
  check_interval: 5
  exit_when_done: true

periodic_updates:
  enabled: true
  update_interval: 30
  update_type: detailed
  use_agent: false
```

Check if Discord notifications are working properly by running the test script:
```bash
uv run tests/test_discord.py
```

Run a simple test (you should see Discord notifications and the job running in the cluster):
```bash
# Run the test
uv run tests/test_slurm_monitor.py
# While it is running you can see the dummy job
squeue -u $USER
```

#### Custom test with two dummy jobs

You will find dummy Python andh Bash scripts in the `tests` folder.

```bash
# Activate dummy script
chmod +x tests/dummy.sh

# Launch two jobs
sbatch --job-name=test_job1 tests/dummy.sh
sbatch --job-name=test_job2 tests/dummy.sh
```

Now that you have the job IDs, proceed to update the `tests/test_config.yaml` file with the job IDs under the `jobs` section, like so:

```yaml
jobs:
  "JOB_ID1":
    log_files: [StdOut]
  "JOB_ID2":
    log_files: [StdOut]
```

Now you can run the monitor for these jobs:
```bash
# Monitor the jobs
uv run slurmonitor -c tests/test_config.yaml
```


## Features

- Multi-threaded real-time monitoring of multiple Slurm jobs (launched via `sbatch`)
- Discord notifications for job status changes
- Log file summarization using AI
- Periodic updates on job progress
- Easy setup with Discord webhooks


<!-- ## Enhancements

- [ ] Use rich tables for better CLI readability
- [ ] From webhook on .txt to a .yaml config file with other options (e.g., default check interval)
- [ ] Extract other infos from the job (job-name, user, etc.) and include them in the notifications
- [ ] Basic log (StdOut) summarization/detection of anomalies
- [ ] Integrate LogSummarizerAgent for better log summarization -->
