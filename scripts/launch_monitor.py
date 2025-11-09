"""Main program for launching the Slurm job monitoring system"""

from slurmonitor import SlurmJobMonitor

import argparse  # command-line arguments
from pathlib import Path
from rich.console import Console

console = Console()


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser()
    parser.add_argument('job_ids', nargs='+', help='Slurm job IDs to monitor')
    parser.add_argument('--check-interval', type=int, default=60,
                       help='Seconds between status checks (default: 60)')
    parser.add_argument('--periodic-updates', action='store_true',
                       help='Send periodic summary updates')
    parser.add_argument('--update-interval', type=int, default=3600,
                       help='Seconds between periodic summaries (default: 3600)')
    parser.add_argument('--log-files', nargs='*',
                       help='Log files corresponding to each job (optional)')

    args = parser.parse_args()

    # Take Discord webhook from .txt file
    webhook_path: Path = Path("./my_webhook_url.txt")
    if not webhook_path.is_file():
        console.print(f"[red]Error:[/red] Discord webhook file '{webhook_path}' not found.")
        return
    with open(webhook_path, 'r', encoding='utf-8') as f:
        args.discord_webhook = f.read().strip()

    # Create single job monitor
    monitor = SlurmJobMonitor(
        discord_webhook=args.discord_webhook,
        check_interval=args.check_interval,
        periodic_updates=args.periodic_updates,
        update_interval=args.update_interval
    )

    # Add jobs to monitor
    log_files = args.log_files or []
    for i, job_id in enumerate(args.job_ids):
        log_file = log_files[i] if i < len(log_files) else None
        monitor.add_job(job_id, log_file)

    # Start monitoring
    console.print(f"Monitoring {len(args.job_ids)} job(s). Press Ctrl+C to stop.")
    monitor.start()


if __name__ == "__main__":
    main()
