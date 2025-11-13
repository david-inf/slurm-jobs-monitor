"""Utilities for the job monitoring system"""

import logging
from rich.logging import RichHandler
from rich.console import Console
from rich.theme import Theme


# Configure logging
monitor_theme = Theme({
    "info": "dim cyan",
    "warning": "magenta",
    "error": "bold red",
})
console = Console(theme=monitor_theme)

logging.basicConfig(
    level=logging.INFO,
    format='%(message)s',
    # datefmt='[%X]',
    handlers=[RichHandler(
        console=console,
        rich_tracebacks=True,
    )],
)
logger = logging.getLogger(__name__)
