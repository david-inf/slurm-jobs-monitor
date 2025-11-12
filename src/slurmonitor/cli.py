"""Main program for launching the Slurm job monitoring system"""

from .core import MultiJobMonitor

import argparse  # command-line arguments
from pathlib import Path
import logging
import sys

# Configure logging with more detailed format
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

DESC = """
Examples:
  # Monitor a single job
  %(prog)s 12345

  # Monitor multiple jobs with custom check interval
  %(prog)s 12345 12346 12347 --check-interval 30

  # Enable periodic summaries every 10 minutes
  %(prog)s 12345 --periodic-updates --update-interval 600
"""


def main():
    """Main entry point for the Slurm job monitor CLI"""
    logger.info("=" * 70)
    logger.info("Slurm Job Monitor - Starting")
    logger.info("=" * 70)

    # Parse command-line arguments
    parser = argparse.ArgumentParser(
        description='Monitor Slurm jobs and send notifications to Discord',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=DESC
    )

    parser.add_argument('job_ids', nargs='+', 
                       help='Slurm job IDs to monitor')
    parser.add_argument('--check-interval', type=int, default=60,
                       help='Seconds between status checks (default: 60)')
    parser.add_argument('--periodic-updates', action='store_true',
                       help='Send periodic summary updates')
    parser.add_argument('--update-interval', type=int, default=20*60,
                       help='Seconds between periodic summaries (default: 1200)')
    parser.add_argument('--webhook-file', type=str, default='./assets/my_webhook_url.txt',
                       help='Path to file containing Discord webhook URL (so you can specify multiple webhooks)')
    parser.add_argument('--exit-when-done', action='store_true', default=True,
                       help='Exit when all jobs complete (default: True)')
    parser.add_argument('--use-agent', action='store_true',
                        help='Use an AI Agent to summarize log files o/w classical')

    args = parser.parse_args()

    # Load Discord webhook URL from file
    logger.info(f"Loading Discord webhook from: {args.webhook_file}")
    webhook_path = Path(args.webhook_file)

    if not webhook_path.is_file():
        logger.error(f"Discord webhook file '{webhook_path}' not found!")
        logger.error("Please create the file with your Discord webhook URL")
        sys.exit(1)

    try:
        with open(webhook_path, 'r', encoding='utf-8') as f:
            discord_webhook = f.read().strip()

        if not discord_webhook:
            logger.error(f"Webhook file '{webhook_path}' is empty!")
            sys.exit(1)

        if not discord_webhook.startswith('https://discord.com/api/webhooks/'):
            logger.warning("Webhook URL doesn't look like a Discord webhook")
            logger.warning("Expected format: https://discord.com/api/webhooks/...")

        logger.info("✓ Successfully loaded Discord webhook URL")

    except Exception as e:
        logger.error(f"Failed to read webhook file: {e}")
        sys.exit(1)

    # Validate job IDs
    logger.info(f"Validating {len(args.job_ids)} job ID(s)...")
    valid_job_ids = []
    for job_id in args.job_ids:
        if job_id.isdigit():
            valid_job_ids.append(job_id)
            logger.info(f"  ✓ Job ID {job_id} is valid")
        else:
            logger.warning(f"  ✗ Invalid job ID: '{job_id}' (must be numeric)")

    if not valid_job_ids:
        logger.error("No valid job IDs provided!")
        sys.exit(1)

    # Create the monitor
    # TODO: use a table format for better readability
    logger.info("\nInitializing MultiJobMonitor...")
    logger.info(f"  Check interval: {args.check_interval} seconds")
    logger.info(f"  Periodic updates: {args.periodic_updates}")
    if args.periodic_updates:
        logger.info(f"  Update interval: {args.update_interval} seconds")

    try:
        monitor = MultiJobMonitor(
            discord_webhook=discord_webhook,
            check_interval=args.check_interval,
            periodic_updates=args.periodic_updates,
            update_interval=args.update_interval,
            use_agent=args.use_agent,
        )
        logger.info("✓ Monitor initialized successfully")

    except Exception as e:
        logger.error(f"Failed to create monitor: {e}")
        sys.exit(1)

    # Add jobs to monitor
    logger.info(f"\nAdding {len(valid_job_ids)} job(s) to monitor...")
    for i, job_id in enumerate(valid_job_ids, start=1):
        try:
            monitor.add_job(job_id)
            logger.info(f"  [{i}/{len(valid_job_ids)}] ✓ Added job {job_id}")
        except Exception as e:
            logger.error(f"  [{i}/{len(valid_job_ids)}] ✗ Failed to add job {job_id}: {e}")

    # Start monitoring
    logger.info("\n" + "=" * 70)
    logger.info(f"Monitoring {len(monitor.monitors)} job(s)")
    logger.info("Press Ctrl+C to stop monitoring")
    logger.info("=" * 70 + "\n")

    try:
        monitor.start(exit_when_done=args.exit_when_done)
        logger.info("\n" + "=" * 70)
        logger.info("Monitor stopped")
        logger.info("=" * 70)

    except KeyboardInterrupt:
        logger.info("\n\nReceived interrupt signal (Ctrl+C)")
        monitor.stop()
        logger.info("Monitor stopped by user")

    except Exception as e:
        logger.error(f"\nUnexpected error during monitoring: {e}", exc_info=True)
        monitor.stop()
        sys.exit(1)


def hello_monitor():
    """Just to do a test and install all packages"""
    print("Hello from slurmonitor")


if __name__ == "__main__":
    main()
