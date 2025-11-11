"""Core module for the Slurm job monitoring system.

This module contains the small monitoring runtime used to poll Slurm
for job state and to report changes to a Discord webhook.

Design notes:
- The code prefers straightforward blocking subprocess calls and plain
  threads for simplicity and portability. This keeps the module easy to
  understand and maintain for users who will run it from CLI or tmux.
"""

from .utils import EMOJI_MAP, COLOR_MAP, STATUS_EMOJI

import time
import subprocess  # used to execute Slurm CLI commands (scontrol, squeue)
from datetime import datetime, timezone
from typing import Dict, Optional
from threading import Thread, Lock
import logging
import requests  # used for sending Discord webhook HTTP requests

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TERMINAL_STATES = [
    "COMPLETED", "FAILED", "TIMEOUT", "CANCELLED",
    "NODE_FAIL", "PREEMPTED", "OUT_OF_MEMORY"
]

# Removed - logic simplified in _monitor_job method


class DiscordNotifier:
    """Send notifications to Discord via webhook"""

    def __init__(self, webhook_url: str):
        self.webhook_url = webhook_url
        self.lock = Lock()

    def send(self, message: str, level: str = "info") -> None:
        """Send a message to Discord"""
        # Build a Discord embed payload; using embeds gives nicer formatting
        # and supports colors/timestamps which are useful for monitoring.
        embed = {
            "description": f"{EMOJI_MAP.get(level, '🔔')} {message}",
            "color": COLOR_MAP.get(level, 3447003),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "footer": {
                "text": "Slurm Monitor"
            }
        }

        payload = {"embeds": [embed]}

        # Use a lock to avoid concurrent requests from multiple threads
        # colliding or exceeding rate limits. We make a best-effort send
        # and swallow exceptions to avoid crashing the monitor loop.
        try:
            with self.lock:
                response = requests.post(self.webhook_url, json=payload, timeout=10)
                # Basic handling of Discord rate limits: Discord may return
                # 429 with a retry_after value (milliseconds). Respect it and
                # retry once. For a robust production system a backoff/queue
                # would be recommended, but that adds complexity here.
                if response.status_code == 429:
                    retry_after = response.json().get('retry_after', 1)
                    time.sleep(retry_after / 1000.0)
                    requests.post(self.webhook_url, json=payload, timeout=10)
        except Exception as e:
            # Log at info level to avoid noisy noise in common deployments.
            logger.info(f"Failed to send Discord notification: {e}")

    def send_summary(self, jobs_status: Dict[str, Dict]) -> None:
        """Send a summary of all monitored jobs"""        
        lines = []
        for job_id, info in jobs_status.items():
            status = info.get('status', 'UNKNOWN')
            emoji = STATUS_EMOJI.get(status, "❓")
            runtime = info.get('runtime', 'N/A')
            lines.append(f"{emoji} **Job {job_id}**: {status} ({runtime})")

        message = "\n".join(lines)

        embed = {
            "title": "📊 Jobs Summary",
            "description": message,
            "color": 9807270,
            "timestamp": datetime.now().isoformat(),
        }

        # Reuse the same locking and best-effort sending pattern used above.
        try:
            with self.lock:
                requests.post(self.webhook_url, json={"embeds": [embed]}, timeout=10)
        except Exception as e:
            logger.info(f"Failed to send summary: {e}")


class JobMonitor:
    """Monitor a single Slurm job by sending notifications to Discord"""

    def __init__(self, job_id, notifier: DiscordNotifier, log_file: Optional[str] = None):
        self.job_id = job_id
        self.notifier = notifier
        self.log_file = log_file

        self.last_status = None  # needs to be updated
        self.running = True  # if this job monitor is running

    def get_job_info(self) -> Optional[Dict]:
        """Query Slurm for detailed job information running 'scontrol show job'"""
        try:
            cmd = ['scontrol', 'show', 'job', self.job_id, '--oneliner']
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)

            if result.returncode != 0:
                # Program failed
                return None

            info = {}
            for item in result.stdout.split():
                if '=' in item:
                    key, value = item.split('=', 1)
                    info[key] = value

            return info

        except Exception as e:
            logger.info(f"[Job {self.job_id}] Error querying job info: {e}")
            return None

    def get_job_status(self) -> Optional[str]:
        """Get current job status running 'squeue'"""
        try:
            # Check if job is in queue
            cmd = ['squeue', '-j', self.job_id, '-h', '-o', '%T']
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)

            if result.returncode != 0 or not result.stdout.strip():
                # Return UNKNOWN if squeue fails or the job is not found.
                return "UNKNOWN"

            return result.stdout.strip()

        except Exception as e:
            logger.info(f"[Job {self.job_id}] Error getting status: {e}")
            return None

    def format_job_info(self, info: Dict) -> str:
        """Format job info for Discord message"""
        lines = [
            f"**Job {self.job_id}**",
            f"Status: `{info.get('JobState', 'UNKNOWN')}`",
            f"Runtime: `{info.get('RunTime', 'N/A')}`",
            f"Node(s): `{info.get('NodeList', 'N/A')}`",
        ]

        if 'Reason' in info and info['Reason'] != 'None':
            lines.append(f"Reason: `{info['Reason']}`")

        return '\n'.join(lines)
    
    def get_status_dict(self) -> Dict:
        """Get current status as dictionary"""
        info = self.get_job_info()
        if info:
            return {
                'status': info.get('JobState', 'UNKNOWN'),
                'runtime': info.get('RunTime', 'N/A'),
                # TODO: maybe add something more?
            }
        return {'status': self.last_status or 'UNKNOWN', 'runtime': 'N/A'}

    def stop(self) -> None:
        """Stop monitoring this job"""
        self.running = False

        # The monitoring loop checks `self.running` and will exit quickly.
        # We don't attempt to forcibly join threads here because the
        # MultiJobMonitor controls thread lifecycle.


class MultiJobMonitor:
    """
    Monitor multiple Slurm jobs simultaneously

    How to keep this guy running with tmux:
    """

    def __init__(self, discord_webhook: str, check_interval: int = 60,
                 periodic_updates: bool = False, update_interval: int = 3600):
        self.check_interval = check_interval  # seconds between checks
        self.periodic_updates = periodic_updates  # whether to send periodic summaries
        self.update_interval = update_interval  # seconds between periodic updates

        self.monitors: Dict[str, JobMonitor] = {}
        self.threads: Dict[int, Thread] = {}

        self.lock = Lock()
        self.notifier = DiscordNotifier(discord_webhook)
        self.running = True  # launch multi-job monitor

        # Note: `threads` maps job_id -> Thread. Using simple threads keeps
        # the implementation easy to understand; for many concurrent jobs
        # consider switching to an event-driven model (asyncio) to reduce
        # resource usage.

    def add_job(self, job_id: str, log_file: Optional[str] = None) -> None:
        """
        Add a job to monitor.
        Intentionally avoids complex lifecycle management so the
        user can easily add/remove jobs at runtime.
        """
        with self.lock:
            if job_id not in self.monitors:
                # Create JobMonitor object
                monitor = JobMonitor(job_id, self.notifier, log_file)
                # Add the monitor to the monitors dict
                self.monitors[job_id] = monitor

                # Start monitoring thread
                thread = Thread(
                    target=self._monitor_job,
                    args=(monitor,)
                )
                thread.daemon = True
                thread.start()
                self.threads[job_id] = thread

                logging.info(f"Started monitoring job {job_id}")
                self.notifier.send(f"Started monitoring job **{job_id}**", "info")

    def _monitor_job(self, monitor: JobMonitor) -> None:
        """Monitor a single job in its own thread"""
        job_id = monitor.job_id  # get this job id

        # While the current job monitor and the overall multi-monitor are running
        while monitor.running and self.running:
            try:
                # Get detailed job info from scontrol (more reliable than squeue)
                info = monitor.get_job_info()

                if info is None:
                    # Job info not available - job might have finished and been purged
                    # or there's a Slurm issue. If we had a last_status, treat as completed
                    if monitor.last_status is not None:
                        logger.info(f"[Job {job_id}] Job no longer in Slurm queue, treating as completed")
                        message = f"**Job {job_id}**\nStatus: Job completed or removed from queue"
                        self.notifier.send(message, "completed")
                        monitor.stop()
                        break
                    else:
                        # Job never started or invalid job_id
                        logger.info(f"[Job {job_id}] Unable to get job info")
                        time.sleep(self.check_interval)
                        continue

                # Get current status from the job info
                status = info.get('JobState', 'UNKNOWN')

                # Check for status changes and send notifications
                if status != monitor.last_status:
                    message = f"{monitor.format_job_info(info)}"

                    # Determine notification level and whether to stop monitoring
                    if status == "RUNNING" and monitor.last_status in [None, "PENDING"]:
                        # Job just started running
                        self.notifier.send(message, "running")

                    elif status == "COMPLETED":
                        # Job completed successfully
                        self.notifier.send(message, "completed")
                        monitor.stop()  # Stop monitoring completed jobs

                    elif status in TERMINAL_STATES:
                        # Job failed, cancelled, timed out, etc.
                        self.notifier.send(message, "error")
                        monitor.stop()  # Stop monitoring failed jobs

                    elif status == "PENDING":
                        # Job is waiting in queue
                        self.notifier.send(message, "pending")

                    # Update the last known status
                    monitor.last_status = status
                    logger.info(f"[Job {job_id}] Status changed to {status}")

                # Wait before next check
                time.sleep(self.check_interval)

            except Exception as e:
                # Catch-all: individual monitor failures should not crash the
                # whole program. Log and continue after a pause.
                logger.error(f"[Job {job_id}] Error in monitoring: {e}")
                time.sleep(self.check_interval)

        # Clean up when done
        with self.lock:
            if job_id in self.monitors:
                # Delete JobMonitor object
                del self.monitors[job_id]
                logger.info(f"[Job {job_id}] Removed from active monitors")
                logger.info(f"Jobs currently monitored: {list(self.monitors.keys())}")
            if job_id in self.threads:
                # Delete Thread object
                del self.threads[job_id]
                logger.info(f"[Job {job_id}] Removed monitoring thread")
                logger.info(f"Jobs currently monitored: {list(self.threads.keys())}")

    def _send_periodic_summary(self) -> None:
        """Send periodic summary of all monitored jobs"""
        while self.running:
            # Wait for next update
            time.sleep(self.update_interval)

            # If there are job monitor activated
            if self.monitors:
                with self.lock:
                    jobs_status = {
                        job_id: monitor.get_status_dict() 
                        for job_id, monitor in self.monitors.items()
                    }

                if jobs_status:
                    self.notifier.send_summary(jobs_status)

    def start(self) -> None:
        """Start the monitoring system"""
        if self.periodic_updates:
            # Automatically sets the periodic summary thread
            summary_thread = Thread(target=self._send_periodic_summary)
            summary_thread.daemon = True
            summary_thread.start()

        # This starts an infinite loop to keep the main thread alive
        try:
            # Wait while monitor is running. Use `self.running` as the canonical
            # flag controlling the runtime; previously code used
            # `self.running` which is not defined at init. Using
            # `self.running` avoids accidental attribute errors.
            while self.running:
                time.sleep(1)
        except KeyboardInterrupt:
            self.stop()

    def stop(self) -> None:
        """Stop all monitoring"""
        logging.info("\nStopping all monitors...")
        # Flip the canonical running flag so threads exit their loops.
        self.running = False

        with self.lock:
            for monitor in self.monitors.values():
                monitor.stop()

        self.notifier.send("Monitoring stopped for all jobs", "warning")
