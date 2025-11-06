"""Tests for sending messages to Discord"""

from slurmonitor.core import DiscordNotifier
from slurmonitor.utils import EMOJI_MAP

from threading import Thread, Lock
from rich.console import Console

YOUR_WEBHOOK_URL = ""
console = Console()


def test_discord_message():
    """Send a simple message to Discord"""
    notifier = DiscordNotifier(YOUR_WEBHOOK_URL)  # who sends the messages
    msg = "Hello World!"  # content
    levels = list(EMOJI_MAP.keys())
    for level in levels:
        # Send a message at each possible level (custom)
        notifier.send(msg, level)


def test_threads_discord_message():
    """Send multiple Discord messages (simulating multiple jobs)"""
    notifier = DiscordNotifier(YOUR_WEBHOOK_URL)
    n_jobs = 3  # jobs under monitoring
    # messages for each job
    msgs = ["Hello World 1!", "Hello World 2!", "Hello World 3!"]

    def send_msg(job_id):
        try:
            notifier.send(msgs[job_id], "running")
        except Exception as e:
            console.print(f"Error in monitoring: {e}")

        with lock:
            if job_id in threads:
                del threads[job_id]

    threads = {}
    lock = Lock()
    for job_id in range(n_jobs):
        with lock:
            thread = Thread(
                target=send_msg,
                args=(job_id,)
            )
            thread.daemon = True
            thread.start()
            threads[job_id] = thread

            console.print(f"Started monitoring job {job_id}")
            notifier.send(f"Started monitoring job **{job_id}**", "info")
