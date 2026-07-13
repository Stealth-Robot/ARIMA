"""RSS watchdog — gracefully recycles the gunicorn worker before the 1GB container OOM."""
import logging
import os
import signal
import threading
import time

logger = logging.getLogger(__name__)

# 450MB enforces the 500MB Railway cost target with headroom for one in-flight stats build.
RSS_LIMIT_MB = int(os.environ.get('MEMWATCH_RSS_LIMIT_MB', '450'))
CHECK_INTERVAL = 30


def read_rss_mb():
    """Current process RSS in MB, or None where /proc is unavailable (e.g. macOS dev)."""
    try:
        with open('/proc/self/status') as f:
            for line in f:
                if line.startswith('VmRSS:'):
                    return int(line.split()[1]) // 1024
    except (OSError, ValueError, IndexError):
        return None
    return None


def _watch_loop():
    while True:
        time.sleep(CHECK_INTERVAL)
        rss = read_rss_mb()
        if rss is not None and rss > RSS_LIMIT_MB:
            logger.warning('memwatch: RSS %dMB exceeds %dMB limit, recycling worker', rss, RSS_LIMIT_MB)
            # SIGTERM to ourselves = graceful gunicorn worker exit; the master respawns a fresh one.
            os.kill(os.getpid(), signal.SIGTERM)
            return


def start_memory_watchdog():
    """Start the RSS monitor thread; no-ops on platforms without /proc."""
    if read_rss_mb() is None:
        return
    logger.info('Starting memory watchdog (limit %dMB, check every %ds)', RSS_LIMIT_MB, CHECK_INTERVAL)
    t = threading.Thread(target=_watch_loop, daemon=True, name='memwatch')
    t.start()
