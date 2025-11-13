"""Core module for the Slurm job monitoring system.

This module contains the small monitoring runtime used to poll Slurm
for job state and to report changes to a Discord webhook.

Design notes:
- The code prefers straightforward blocking subprocess calls and plain
  threads for simplicity and portability. This keeps the module easy to
  understand and maintain for users who will run it from CLI or tmux.
"""

from .discord_notifier import DiscordNotifier
from .agent import LogSummarizerAgent, SimpleLogSummarizer
from .utils import logger

import time
import subprocess  # used to execute Slurm CLI commands (scontrol, squeue)
from typing import Dict, Optional, Union
from threading import Thread, Lock
import logging
from pathlib import Path

TERMINAL_STATES = [
    "COMPLETED", "FAILED", "TIMEOUT", "CANCELLED",
    "NODE_FAIL", "PREEMPTED", "OUT_OF_MEMORY"
]


class JobMonitor:
    """Monitor a single Slurm job by sending notifications to Discord"""

    def __init__(self, job_id, notifier: DiscordNotifier):
        self.job_id = job_id
        self.notifier = notifier

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
            f"**Job {self.job_id}** ({info.get('JobName', 'N/A')})",
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
            return info
        return {'status': self.last_status or 'UNKNOWN', 'runtime': 'N/A'}

    # TODO: review and do docs on this method
    def summarize_std_out(self, summary_opts: Optional[Dict], pipeline: Union[LogSummarizerAgent, SimpleLogSummarizer]) -> str:
        """Use a text summarization pipeline on given log files (*.out)"""
        # Retrieve job info
        info_dict: Dict = self.get_job_info()

        files_to_summarize = []
        if summary_opts.get('log_files') is not None:
            stdout_path: Path = Path(info_dict.get('StdOut', ''))
            if 'StdOut' in summary_opts['log_files']:
                files_to_summarize.append(stdout_path)
            # Assume other log files are in the same parent as StdOut
            files_to_summarize.extend([stdout_path.parent / log for log in summary_opts['log_files'] if log != 'StdOut'])
        else:
            # Default to StdOut only
            stdout_path: Path = Path(info_dict.get('StdOut', ''))
            files_to_summarize.append(stdout_path)

        # Extract the StdOut key if exists
        summary = []
        log_file: Path
        for log_file in files_to_summarize:
            if log_file.exists():
                summary.append(f"**{log_file.name}:**")
                try:
                    summary.append(pipeline.summarize(log_file, verbose=False))
                except Exception as e:
                    logger.info(f"[Job {self.job_id}] Error reading log file {log_file}: {e}, skipping...")
                    continue

            else:
                summary.append(f"Log file {log_file} **not found**.")

        return "\n".join(summary)

    def stop(self) -> None:
        """Stop monitoring this job"""
        self.running = False

        # The monitoring loop checks `self.running` and will exit quickly.
        # We don't attempt to forcibly join threads here because the
        # MultiJobMonitor controls thread lifecycle.


class MultiJobMonitor:
    """
    Monitor multiple Slurm jobs simultaneously

    USAGE PATTERNS:

    1. Batch monitoring (exit when all jobs complete):
       ```python
       monitor = MultiJobMonitor(webhook_url)
       monitor.add_job("12345")
       monitor.add_job("12346")
       monitor.start(exit_when_done=True)  # Exits when both jobs finish
       ```

    2. Long-running service (continuous monitoring):
       ```python
       monitor = MultiJobMonitor(webhook_url)
       monitor.add_job("12345")
       monitor.start(exit_when_done=False)  # Keeps running forever
       ```

    CURRENT LIMITATION:
    - Jobs can only be added before calling start()
    - Once start() is called with exit_when_done=True, it exits when all jobs finish
    """

    def __init__(self, discord_opts: Dict, jobs_dict: Dict, job_status_opts: Dict, periodic_updates_opts: Dict):
        # Preserve original configuration dicts
        self.discord_opts = discord_opts
        self.jobs_dict = jobs_dict
        self.job_status_opts = job_status_opts
        self.summary_opts = periodic_updates_opts

        # Get job status updates settings
        self.check_interval = int(self.job_status_opts.get('check_interval', 15))
        # Get jobs summary updates
        self.periodic_updates = bool(self.summary_opts.get('enabled', False))
        self.update_interval = int(self.summary_opts.get('update_interval', 20 * 60))
        self.update_type = self.summary_opts.get('update_type', 'brief')

        # Keep the pipeline (especially the agent) centralized so
        # it won't be created by each JobMonitor
        if bool(self.summary_opts.get('use_agent', False)):
            self.summary_pipe = LogSummarizerAgent()
        else:
            self.summary_pipe = SimpleLogSummarizer()

        self.monitors: Dict[str, JobMonitor] = {}
        self.threads: Dict[int, Thread] = {}

        self.lock = Lock()
        self.notifier = DiscordNotifier(discord_opts.get('webhook', ''))
        self.running = True  # launch multi-job monitor

        # Note: `threads` maps job_id -> Thread. Using simple threads keeps
        # the implementation easy to understand; for many concurrent jobs
        # consider switching to an event-driven model (asyncio) to reduce
        # resource usage.

        self._add_jobs()

    def _add_jobs(self) -> None:
        """Add multiple jobs from the jobs_dict"""
        logger.info(f"Adding {len(self.jobs_dict)} job(s) to monitor...")
        for i, job_id in enumerate(self.jobs_dict.keys(), start=1):
            try:
                self.add_job(str(job_id))
                logger.info(f"  [{i}/{len(self.jobs_dict)}] ✓ Added job {job_id}")
            except Exception as e:
                logger.error(f"  [{i}/{len(self.jobs_dict)}] ✗ Failed to add job {job_id}: {e}")

    def add_job(self, job_id: str) -> None:
        """
        Add a job to monitor.
        Intentionally avoids complex lifecycle management so the
        user can easily add/remove jobs at runtime.
        """
        with self.lock:
            if job_id not in self.monitors:
                # Create JobMonitor object
                monitor = JobMonitor(job_id, self.notifier)
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

            logger.debug(f"Jobs currently monitored: {list(self.monitors.keys())}")
            logger.debug(f"Threads currently running: {list(self.threads.keys())}")

    def remove_job(self, job_id: str) -> bool:
        """
        Remove a job from monitoring (for runtime job management)

        Args:
            job_id: The Slurm job ID to stop monitoring

        Returns:
            True if job was removed, False if job wasn't being monitored

        Note: This gracefully stops the monitoring thread. The thread will
              exit on its next iteration when it checks monitor.running.
        """
        with self.lock:
            if job_id in self.monitors:
                logger.info(f"[Job {job_id}] Requesting removal from monitoring")
                self.monitors[job_id].stop()  # Signal thread to exit
                return True
            else:
                logger.warning(f"[Job {job_id}] Not currently being monitored")
                return False

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
                    message = monitor.format_job_info(info)

                    # Map status to notification level and whether to stop monitoring
                    if status == "COMPLETED":
                        level, stop = "completed", True
                    elif status in TERMINAL_STATES:
                        level, stop = "error", True
                    elif status == "RUNNING":
                        level, stop = "running", False
                    elif status == "PENDING":
                        level, stop = "pending", False
                    else:
                        level, stop = "info", False

                    self.notifier.send(message, level)

                    if stop:
                        monitor.stop()

                    last_status = monitor.last_status
                    monitor.last_status = status
                    logger.info(f"[Job {job_id}] Status changed to {status} from {last_status}")

                    # Update the last known status
                    last_status = monitor.last_status
                    monitor.last_status = status
                    logger.info(f"[Job {job_id}] Status changed to {status} from {last_status}")

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
                logger.info(f"Threads currently running: {list(self.threads.keys())}")

    def _send_periodic_summary(self) -> None:
        """Send periodic summary of all monitored jobs"""
        while self.running:
            # If there are job monitor activated
            if self.monitors:
                with self.lock:
                    # Get info using scontrol command
                    # this is just a check, will be redundant but it's ok
                    # in the simplest version it is just to check runtime
                    jobs_status = {
                        job_id: monitor.get_status_dict()
                        for job_id, monitor in self.monitors.items()
                    }
                    # Text summarization pipeline
                    if self.update_type in ['detailed']:
                        jobs_summary = {
                            job_id: monitor.summarize_std_out(
                                summary_opts=self.jobs_dict[job_id],
                                pipeline=self.summary_pipe
                            ) for job_id, monitor in self.monitors.items()
                        }

                if jobs_status:
                    self.notifier.send_summary(jobs_status)
                    logger.info("Sent job status summary")
                if self.update_type in ['detailed'] and jobs_summary:
                    for job_id, summary in jobs_summary.items():
                        self.notifier.send(f"**Job {job_id} StdOut Summary:**\n{summary}", "info")
                        logger.info(f"Sent detailed summary for job {job_id}")

            # Wait for next update
            time.sleep(self.update_interval)

    def start(self, exit_when_done: bool = True) -> None:
        """Start the monitoring system
        
        Args:
            exit_when_done: If True, automatically exit when all jobs complete.
                          If False, keep running indefinitely (useful for runtime job management).
        """
        if self.periodic_updates:
            # Automatically sets the periodic summary thread
            summary_thread = Thread(target=self._send_periodic_summary)
            summary_thread.daemon = True
            summary_thread.start()

        # This starts an infinite loop to keep the main thread alive
        try:
            # Wait while monitor is running
            while self.running:
                time.sleep(5)  # Check every 5 seconds (in case of self.stop() call)

                # Check if there are any active monitors
                # Needs this context manager everytime one interacts with monitors (threadsafety)
                with self.lock:
                    active_count = len(self.monitors)

                if active_count == 0:
                    if exit_when_done:
                        # TEMPORARY SOLUTION: Exit when no jobs are being monitored
                        logging.info("No active job monitors remaining. Exiting...")
                        self.running = False
                        # Just break, no need to call self.stop()
                        self.notifier.send("All monitored jobs have completed. Monitor is exiting.", "info")
                        break
                    else:
                        # Keep running, waiting for jobs to be added at runtime
                        # (requires implementing add_job_runtime() method)
                        logger.debug("No active monitors, but continuing to run (exit_when_done=False)")
                        
        except KeyboardInterrupt:
            # Exits the while loop and stops monitoring if any
            logging.info("\nReceived keyboard interrupt (Ctrl+C)")
            self.stop()

    def stop(self) -> None:
        """Stop all monitoring and clean up resources"""
        logging.info("\n" + "=" * 60)
        logging.info("Stopping all monitors...")
        logging.info("=" * 60)

        # Flip the canonical running flag so threads exit their loops.
        self.running = False

        with self.lock:
            active_jobs = list(self.monitors.keys())
            for monitor in self.monitors.values():
                monitor.stop()

        if active_jobs:
            logging.info(f"Stopped monitoring {len(active_jobs)} job(s): {active_jobs}")
            self.notifier.send(
                f"Monitoring stopped for {len(active_jobs)} job(s): {', '.join(active_jobs)}", 
                "warning"
            )
        else:
            logging.info("No active jobs to stop")

        logging.info("Monitor shutdown complete")
        logging.info("=" * 60)
        self.notifier.send("Slurm Monitor has been stopped.", "info")

    def __str__(self) -> str:
        """Human-friendly multi-line configuration summary for printing."""
        webhook = getattr(self.notifier, 'webhook_url', '')[:30] + '...'
        lines = [
            "MultiJobMonitor configuration:",
            f"  - webhook: {webhook}",
            f"  - job_status_opts: {self.job_status_opts}",
            f"  - periodic_updates: {self.summary_opts}",
            f"  - jobs_opts: {self.jobs_dict}"
        ]
        return "\n".join(lines)    
