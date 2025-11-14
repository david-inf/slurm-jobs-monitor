"""Tests for sending messages to Discord"""

from slurmonitor.core import DiscordNotifier
from slurmonitor.discord_notifier import EMOJI_MAP

from threading import Thread, Lock
from rich.console import Console
import yaml

console = Console()


def test_discord_message():
    """Send a simple message to Discord"""
    console.rule("Testing Discord message sending")
    with open("tests/test_config.yaml", 'r', encoding='utf-8') as f:
        configs = yaml.safe_load(f)
    assert configs is not None
    assert isinstance(configs, dict)
    console.print(configs)

    webhook = configs['discord']['webhook'].strip()
    if not webhook:
        console.print(f"[red]Error:[/red] Discord webhook file '{webhook}' not found.")
        return
    console.print(f"Retrieved webhook URL [bold purple]{webhook}[/bold purple]")

    notifier = DiscordNotifier(webhook)  # who sends the messages
    msg = "Hello World!"  # content
    levels = list(EMOJI_MAP.keys())
    for level in levels:
        # Send a message at each possible level (custom)
        notifier.send(msg, level)
    console.print("Messages sent!")


def test_threads_discord_message():
    """Send multiple Discord messages (simulating multiple jobs)"""
    console.rule("Testing Discord message sending with threads")
    with open("tests/test_config.yaml", 'r', encoding='utf-8') as f:
        configs = yaml.safe_load(f)
    assert configs is not None
    assert isinstance(configs, dict)
    console.print(configs)

    webhook = configs['discord']['webhook'].strip()
    if not webhook:
        console.print(f"[red]Error:[/red] Discord webhook file '{webhook}' not found.")
        return
    console.print(f"Retrieved webhook URL [bold purple]{webhook}[/bold purple]")

    notifier = DiscordNotifier(webhook)
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


if __name__ == "__main__":
    test_discord_message()
    test_threads_discord_message()
