"""Discord notification handler"""

import time
from typing import Dict
from datetime import datetime, timezone
import requests  # used for sending Discord webhook HTTP requests
from threading import Lock
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# Emoji mappings using Unicode escape sequences for better compatibility
# This avoids display issues in terminals and editors that don't support emoji
EMOJI_MAP = {
    "info": "\U00002139\U0000FE0F",     # ℹ️ Information
    "warning": "\U000026A0\U0000FE0F",  # ⚠️ Warning sign
    "error": "\U0000274C",              # ❌ Cross mark
    "success": "\U00002705",            # ✅ Check mark
    "running": "\U0001F680",            # 🚀 Rocket
    "pending": "\U000023F3",            # ⏳ Hourglass
    "completed": "\U0001F389",          # 🎉 Party popper
    "log": "\U0001F4DD",                # 📝 Memo
    "stats": "\U0001F4CA"               # 📊 Bar chart
}

# Color codes for Discord embeds (decimal format)
COLOR_MAP = {
    "info": 3447003,      # Blue (#3498DB)
    "warning": 16776960,  # Yellow (#FFFF00)
    "error": 15158332,    # Red (#E74C3C)
    "success": 3066993,   # Green (#2ECC71)
    "running": 3447003,   # Blue (#3498DB)
    "pending": 10181046,  # Purple (#9B59B6)
    "completed": 3066993, # Green (#2ECC71)
    "log": 9807270,       # Gray (#95A5A6)
    "stats": 9936031      # Teal (#97C4FF)
}

# Status-specific emoji for job states
STATUS_EMOJI = {
    "RUNNING": "\U0001F3C3",            # 🏃 Runner (person running)
    "PENDING": "\U0001F7E1",            # 🟡 Yellow circle
    "COMPLETED": "\U00002705",          # ✅ Check mark
    "FAILED": "\U0000274C",             # ❌ Cross mark
    "TIMEOUT": "\U000023F1\U0000FE0F",  # ⏱️ Stopwatch
    "CANCELLED": "\U0001F6AB",          # 🚫 Prohibited sign
    "NODE_FAIL": "\U0001F4A5",          # 💥 Collision
    "OUT_OF_MEMORY": "\U0001F4BE",      # 💾 Floppy disk (memory symbol)
    "UNKNOWN": "\U00002753"             # ❓ Question mark
}


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


