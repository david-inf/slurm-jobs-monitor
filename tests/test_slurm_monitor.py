"""
Testing Slurm jobs monitoring
- Needs to create a temporary python script (like with time.sleep())
- Needs to create a temporary shell script
"""

from slurmonitor.core import DiscordNotifier, JobMonitor

from threading import Lock, Thread

YOUR_WEBHOOK_URL = ""


def test_slurm_monitor():
    """Testing the job monitoring on a dummy Slurm job"""
    notifier = DiscordNotifier(YOUR_WEBHOOK_URL)
    monitor = JobMonitor(notifier)

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

