"""Core module for the Slurm job monitoring system"""

from .utils import EMOJI_MAP, COLOR_MAP, STATUS_EMOJI

import time
import subprocess  # executing slurm commands
from datetime import datetime
from pathlib import Path  # better handling of paths
from typing import Dict, List, Optional
from threading import Thread, Lock  # ???
import logging
import requests  # how to get to discord


class DiscordNotifier:
    """Send notifications to Discord via webhook"""

    def __init__(self, webhook_url: str):
        self.webhook_url = webhook_url
        self.lock = Lock()

    def send(self, message: str, level: str = "info"):
        """Send a message to Discord"""
        # Create embed for better formatting
        embed = {
            "description": f"{EMOJI_MAP.get(level, '🔔')} {message}",
            "color": COLOR_MAP.get(level, 3447003),
            "timestamp": datetime.utcnow().isoformat(),
            "footer": {
                "text": "Slurm Monitor"
            }
        }

        payload = {"embeds": [embed]}

        # Send message
        try:
            with self.lock:
                response = requests.post(self.webhook_url, json=payload, timeout=10)
                if response.status_code == 429:  # Rate limited
                    retry_after = response.json().get('retry_after', 1)
                    time.sleep(retry_after / 1000.0)
                    requests.post(self.webhook_url, json=payload, timeout=10)
        except Exception as e:
            console.print(f"Failed to send Discord notification: {e}")

    def send_summary(self, jobs_status: Dict[str, Dict]):
        """Send a summary of all monitored jobs"""        
        lines = ["**📊 Jobs Summary**\n"]
        for job_id, info in jobs_status.items():
            status = info.get('status', 'UNKNOWN')
            emoji = STATUS_EMOJI.get(status, "❓")
            runtime = info.get('runtime', 'N/A')
            lines.append(f"{emoji} **Job {job_id}**: {status} ({runtime})")
        
        message = "\n".join(lines)
        
        embed = {
            "title": "Multi-Job Status Summary",
            "description": message,
            "color": 9807270,
            "timestamp": datetime.utcnow().isoformat()
        }
        
        try:
            with self.lock:
                requests.post(self.webhook_url, json={"embeds": [embed]}, timeout=10)
        except Exception as e:
            print(f"Failed to send summary: {e}")


class JobMonitor:
    """
    Monitor a single Slurm by sending notifications to Discord
    - 
    """

    def __init__(self, job_id, notifier: DiscordNotifier, log_file: Optional[str] = None):
        self.job_id = job_id
        self.notifier = notifier
        self.log_file = log_file

        self.last_status = None  # needs to be updated
        self.running = True  # launch job monitor

    def get_job_info(self) -> Optional[Dict]:
        """Query Slurm for detailed job information"""
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
            print(f"[Job {self.job_id}] Error querying job info: {e}")
            return None

    def get_job_status(self) -> Optional[str]:
        """Get current job status"""
        try:
            # Check if job is in queue
            cmd = ['squeue', '-j', self.job_id, '-h', '-o', '%T']
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)

            if result.returncode != 0 or not result.stdout.strip():
                return "UNKNOWN"

            return result.stdout.strip()
            
        except Exception as e:
            print(f"[Job {self.job_id}] Error getting status: {e}")
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
                'runtime': info.get('RunTime', 'N/A')
            }
        return {'status': self.last_status or 'UNKNOWN', 'runtime': 'N/A'}

    def is_terminal_state(self, status: str) -> bool:
        """Check if job has reached a terminal state"""
        terminal_states = [
            "COMPLETED", "FAILED", "TIMEOUT", "CANCELLED",
            "NODE_FAIL", "PREEMPTED", "OUT_OF_MEMORY"
        ]
        return status in terminal_states

    def stop(self):
        """Stop monitoring this job"""
        self.running = False


class MultiJobMonitor:
    """
    Monitor multiple Slurm jobs simultaneously

    How to keep this guy running with tmux:
    """

    def __init__(self, discord_webhook: str, check_interval: int = 60,
                 periodic_updates: bool = False, update_interval: int = 3600):
        self.check_interval = check_interval
        self.periodic_updates = periodic_updates
        self.update_interval = update_interval

        self.monitors: Dict[str, JobMonitor] = {}
        self.threads: Dict[int, Thread] = {}

        self.lock = Lock()
        self.notifier = DiscordNotifier(discord_webhook)
        self.running = True  # launch multi-job monitor

    def add_job(self, job_id: str, log_file: Optional[str] = None):
        """Add a job to monitor"""
        with self.lock:
            if job_id not in self.monitors:
                monitor = JobMonitor(job_id, self.notifier, log_file)
                self.monitors[job_id] = monitor  # add monitor object

                # Start monitoring thread
                thread = Thread(
                    target=self._monitor_job,
                    args=(monitor,)
                )
                thread.daemon = True
                thread.start()
                self.threads[job_id] = thread

                console.print(f"Started monitoring job {job_id}")
                self.notifier.send(f"Started monitoring job **{job_id}**", "info")

    def _monitor_job(self, monitor: JobMonitor):
        """Monitor a single job in its own thread"""
        job_id = monitor.job_id  # get this job id

        while monitor.running and self.running:
            try:
                # Check job status
                status = monitor.get_job_status()

                # Check for status changes
                if status and status != monitor.last_status:
                    info = monitor.get_job_info()

                    if status == "RUNNING" and monitor.last_status in [None, "PENDING"]:
                        message = f"{monitor.format_job_info(info)}"
                        self.notifier.send(message, "running")

                    elif status == "COMPLETED":
                        message = f"{monitor.format_job_info(info)}"
                        self.notifier.send(message, "completed")
                        monitor.stop()  # stop monitoring if completed

                    elif monitor.is_terminal_state(status):
                        message = f"{monitor.format_job_info(info)}"
                        self.notifier.send(message, "error")
                        monitor.stop()  # stop monitoring if on error

                    elif status == "PENDING":
                        message = f"{monitor.format_job_info(info)}"
                        self.notifier.send(message, "pending")

                    # Update status if changed
                    monitor.last_status = status

                # Check for log updates
                log_update = monitor.check_log_updates()
                if log_update:
                    # Truncate if too long for Discord
                    if len(log_update) > 1800:
                        log_update = log_update[-1800:] + "\n... (truncated)"

                    message = f"**Job {job_id} - Log Update:**\n```\n{log_update}\n```"
                    self.notifier.send(message, "log")

                # Wait for next update
                time.sleep(self.check_interval)

            except Exception as e:
                console.print(f"[Job {job_id}] Error in monitoring: {e}")
                time.sleep(self.check_interval)

        # Clean up when done
        with self.lock:
            if job_id in self.monitors:
                # Delete JobMonitor object
                del self.monitors[job_id]
            if job_id in self.threads:
                # Delete Thread object, so deliting the thread itself
                del self.threads[job_id]

    def send_periodic_summary(self):
        """Send periodic summary of all jobs"""
        while self.running:
            # Wait for next update
            time.sleep(self.update_interval)

            # If this feature is enabled
            # and there are job monitor activated
            if self.periodic_updates and self.monitors:
                with self.lock:
                    jobs_status = {
                        job_id: monitor.get_status_dict() 
                        for job_id, monitor in self.monitors.items()
                    }

                if jobs_status:
                    self.notifier.send_summary(jobs_status)

    def start(self):
        """Start the monitoring system"""
        if self.periodic_updates:
            summary_thread = Thread(target=self.send_periodic_summary)
            summary_thread.daemon = True
            summary_thread.start()
        
        try:
            while self.is_monitor_running:
                time.sleep(1)  # 
        except KeyboardInterrupt:
            self.stop()
    
    def stop(self):
        """Stop all monitoring"""
        console.print("\nStopping all monitors...")
        self.is_monitor_running = False

        with self.lock:
            for monitor in self.monitors.values():
                monitor.stop()

        self.notifier.send("Monitoring stopped for all jobs", "warning")

