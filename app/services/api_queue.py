"""Single-worker HTTP request queue with retry and backpressure handling.

All HTTP calls go through one worker thread. Callers submit requests via
queue.request() which blocks until the worker processes it. The worker
handles 429/Retry-After and network errors internally — callers get back
a requests.Response or an ApiQueueError.
"""

import os
import time
import queue
import random
import logging
import threading

import requests as http_lib

logger = logging.getLogger(__name__)

_MAX_RETRY_WAIT = 120
_MAX_RETRIES = 5


class ApiQueueError(Exception):
    pass


class RateLimitedError(ApiQueueError):
    """Raised when the remembered cooldown is too long to wait out.

    `retry_after` is the seconds remaining on the cooldown.
    """

    def __init__(self, message, retry_after):
        super().__init__(message)
        self.retry_after = retry_after


class ApiQueue:

    def __init__(self, min_interval=0.0):
        self._q = queue.Queue()
        self._worker = None
        self._lock = threading.Lock()
        # Wall-clock time until which the remote has asked us not to call it
        # (set from Retry-After on a 429). Only touched by the worker thread.
        self._cooldown_until = 0.0
        # Proactive pacing: minimum seconds between successive requests, to
        # stay under the remote's rolling-window limit and avoid earning a
        # long ban in the first place. Only touched by the worker thread.
        self._min_interval = min_interval
        self._last_request = 0.0

    def _ensure_worker(self):
        with self._lock:
            if self._worker is None or not self._worker.is_alive():
                self._worker = threading.Thread(target=self._run, daemon=True)
                self._worker.start()

    def request(self, method, url, headers=None, data=None, timeout=15,
                on_status=None):
        self._ensure_worker()
        result_q = queue.Queue(maxsize=1)
        self._q.put((method, url, headers, data, timeout, on_status, result_q))
        result = result_q.get()
        if isinstance(result, Exception):
            raise result
        return result

    def _run(self):
        while True:
            item = self._q.get()
            method, url, headers, data, timeout, on_status, result_q = item
            try:
                resp = self._execute(method, url, headers, data, timeout,
                                     on_status)
                result_q.put(resp)
            except Exception as exc:
                result_q.put(exc)

    def _execute(self, method, url, headers, data, timeout, on_status):
        for attempt in range(_MAX_RETRIES + 1):
            # Honor any cooldown the remote previously imposed before we call
            # it again — short waits are slept out, long ones fail fast so we
            # don't sit on the worker (and don't re-trip the limit).
            self._honor_cooldown(on_status)
            self._pace()
            try:
                resp = http_lib.request(method, url, headers=headers,
                                        data=data, timeout=timeout)
            except http_lib.RequestException as exc:
                if attempt < _MAX_RETRIES:
                    wait = min(2 ** attempt + random.uniform(0, 1), 60)
                    logger.warning('Network error on %s (attempt %d): %s',
                                   url, attempt + 1, exc)
                    if on_status:
                        on_status(f'Network error, retrying in {wait:.0f}s...')
                    time.sleep(wait)
                    continue
                raise ApiQueueError(
                    f'Request failed after {_MAX_RETRIES + 1} attempts: {exc}'
                )

            if resp.status_code != 429:
                return resp

            # Remember the backoff window so this and every later request
            # waits it out instead of hammering the remote.
            wait = _parse_retry_after(resp, attempt)
            self._cooldown_until = max(self._cooldown_until, time.time() + wait)
            logger.warning('429 on %s, Retry-After=%s, cooldown %ds '
                           '(attempt %d/%d)', url,
                           resp.headers.get('Retry-After', '?'), wait,
                           attempt + 1, _MAX_RETRIES)

        # Retries exhausted on 429 — surface the remembered cooldown (raises if
        # it's still long, otherwise falls through to the generic message).
        self._honor_cooldown(on_status)
        raise ApiQueueError(
            'Rate limit retries exhausted. Please wait a minute and try again.'
        )

    def cooldown_remaining(self):
        """Seconds left on the remembered cooldown (0 if not rate-limited)."""
        return max(0.0, self._cooldown_until - time.time())

    def _pace(self):
        """Sleep so successive requests are at least _min_interval apart."""
        if self._min_interval <= 0:
            return
        gap = self._min_interval - (time.time() - self._last_request)
        if gap > 0:
            time.sleep(gap)
        self._last_request = time.time()

    def _honor_cooldown(self, on_status):
        """Block (or fail fast) until the remembered cooldown has elapsed."""
        remaining = self._cooldown_until - time.time()
        if remaining <= 0:
            return
        if remaining > _MAX_RETRY_WAIT:
            raise RateLimitedError(_cooldown_message(remaining), remaining)
        if on_status:
            on_status(f'Rate-limited, waiting {int(remaining) + 1}s...')
        time.sleep(remaining)


def _cooldown_message(remaining):
    # Emit the expiry as a UTC ISO timestamp; the client localizes it to the
    # user's timezone (and it stays readable as UTC if that doesn't run).
    import datetime
    mins = int((remaining + 59) // 60)
    until = (datetime.datetime.now(datetime.timezone.utc)
             + datetime.timedelta(seconds=remaining))
    return (f'Rate-limited for ~{mins} min (until {until:%Y-%m-%dT%H:%MZ}). '
            'Please try again later.')


def _parse_retry_after(resp, attempt):
    raw = resp.headers.get('Retry-After')
    if raw is not None:
        try:
            return max(int(raw), 0)
        except (ValueError, TypeError):
            pass
    return int(min(2 ** attempt + random.uniform(0, 2), 60))


# Pace Spotify calls to stay under its rolling-window limit and avoid long
# bans. 0.4s == ~2.5 req/s (~75 per 30s window). Tunable via
# SPOTIFY_MIN_REQUEST_INTERVAL (seconds).
try:
    _SPOTIFY_MIN_INTERVAL = max(0.0, float(
        os.environ.get('SPOTIFY_MIN_REQUEST_INTERVAL', '0.4')))
except ValueError:
    _SPOTIFY_MIN_INTERVAL = 0.4

spotify_queue = ApiQueue(min_interval=_SPOTIFY_MIN_INTERVAL)
railway_queue = ApiQueue()
