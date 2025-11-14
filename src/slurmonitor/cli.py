"""Main program for launching the Slurm job monitoring system.

This module now uses a YAML configuration file (default: `./assets/config.yaml`).

Config precedence and assumptions
- Default config path: cwd()/assets/config.yaml
"""

from .core import MultiJobMonitor
from .utils import logger, console

import argparse
from pathlib import Path
from typing import Any, Dict
import yaml


def load_config(config_file: Path) -> Dict[str, Any]:
    """Load YAML configuration from `config_file`.

    Raises SystemExit with a helpful message when configuration cannot be loaded.
    """
    if not config_file.is_file():
        logger.error(f"Config file not found: {config_file}")
        raise SystemExit(1)

    try:
        with open(config_file, 'r', encoding='utf-8') as f:
            cfg = yaml.safe_load(f) or {}
            if not isinstance(cfg, dict):
                logger.error(f"Invalid config structure in {config_file}: top-level mapping expected")
                raise SystemExit(1)
            # Validate essential fields
            if cfg['discord']['webhook'] is None:
                logger.error(f"Discord webhook not set in config file {config_file}")
                raise SystemExit(1)
            if cfg['discord']['webhook'] and isinstance(cfg['discord']['webhook'], str):
                cfg['discord']['webhook'] = cfg['discord']['webhook'].strip()
            return cfg

    except Exception as e:
        logger.error(f"Failed to read config file {config_file}: {e}")
        raise SystemExit(1)


def main():
    """Main entry point: read config, initialize monitor, add jobs, and start."""
    parser = argparse.ArgumentParser(description="Slurm Job Monitor")
    parser.add_argument('--config-file', '-c', type=str, default="./assets/config.yaml",
                        help="Path to configuration YAML file (default: ./assets/config.yaml)")
    args = parser.parse_args()

    # Load configuration
    logger.info("Slurm Job Monitor - Starting")
    cfg_path = Path(args.config_file)
    logger.info(f"Loading configuration from: {cfg_path}")
    cfg = load_config(cfg_path)

    # Read simple options with sensible defaults
    jobs_dict = cfg.get('jobs', {})
    if not isinstance(jobs_dict, dict) or not jobs_dict:
        logger.error("No jobs configured. Please add a 'jobs' list to the config with Slurm job IDs to monitor.")
        raise SystemExit(1)

    # Create the monitor
    try:
        monitor = MultiJobMonitor(
            discord_opts=cfg.get('discord', {}),
            jobs_dict=jobs_dict,
            job_status_opts=cfg.get('job_status', {}),
            periodic_updates_opts=cfg.get('periodic_updates', {}),
        )
        logger.info("✓ Monitor initialized successfully")
    except Exception as e:
        logger.error(f"Failed to create monitor: {e}")
        raise SystemExit(1)
    console.print(monitor)

    # Start monitoring
    logger.info(f"Monitoring {len(monitor.monitors)} job(s). Press Ctrl+C to stop.")
    try:
        exit_when_done = bool(cfg['job_status'].get('exit_when_done', True))
        monitor.start(exit_when_done=exit_when_done)
        logger.info("Monitor stopped")
    except KeyboardInterrupt:
        logger.info("Received interrupt signal (Ctrl+C)")
        monitor.stop()
    except Exception as e:
        logger.error(f"Unexpected error during monitoring: {e}", exc_info=True)
        monitor.stop()
        raise SystemExit(1)


def hello_monitor():
    """Small helper used by tests or quick checks."""
    print("Hello from slurmonitor!")


if __name__ == "__main__":
    main()
