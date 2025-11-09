"""
Testing Slurm jobs monitoring
- Needs to create a temporary python script (like with time.sleep())
- Needs to create a temporary shell script
"""

from slurmonitor.core import DiscordNotifier, JobMonitor

from threading import Lock, Thread
from pathlib import Path
from rich.console import Console

console = Console()


def test_slurm_monitor():
    """Testing the job monitoring on a dummy Slurm job"""
    webhook_path: Path = Path("assets/my_webhook_url.txt")
    if not webhook_path.is_file():
        console.print(f"[red]Error:[/red] Discord webhook file '{webhook_path}' not found.")
        return
    with open(webhook_path, 'r', encoding='utf-8') as f:
        discord_webhook = f.read().strip()
    console.print(f"Retrieved webhook URL [bold purple]{discord_webhook}[/bold purple]")

    notifier = DiscordNotifier(discord_webhook)
    monitor = JobMonitor(notifier)

    # TODO: create a dummy slurm job

    def monitor_job():
        return None

    # Start monitoring thread
    thread = Thread(
        target=monitor_job,
        args=(None,)
    )
    thread.daemon = True
    thread.start()
    self.threads[job_id] = thread

    console.print(f"Started monitoring job {job_id}")
    self.notifier.send(f"Started monitoring job **{job_id}**", "info")

