"""Single-worker HTTP request queue with retry and backpressure handling.

All HTTP calls go through one worker thread. Callers submit requests via
queue.request() which blocks until the worker processes it. The worker
handles 429/Retry-After and network errors internally — callers get back
a requests.Response or an ApiQueueError.
"""

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


class ApiQueue:

    def __init__(self):
        self._q = queue.Queue()
        self._worker = None
        self._lock = threading.Lock()

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

            if attempt >= _MAX_RETRIES:
                raise ApiQueueError(
                    'Rate limit retries exhausted. '
                    'Please wait a minute and try again.'
                )

            wait = _parse_retry_after(resp, attempt)
            if wait > _MAX_RETRY_WAIT:
                mins = (wait + 59) // 60
                raise ApiQueueError(
                    f'Rate limit too long ({mins} min). '
                    'Please wait and try again later.'
                )
            logger.warning('429 on %s, Retry-After=%s, attempt %d/%d',
                           url, resp.headers.get('Retry-After', '?'),
                           attempt + 1, _MAX_RETRIES)
            if on_status:
                on_status(f'Rate-limited, waiting {wait}s '
                          f'(attempt {attempt + 1}/{_MAX_RETRIES})...')
            time.sleep(wait)


def _parse_retry_after(resp, attempt):
    raw = resp.headers.get('Retry-After')
    if raw is not None:
        try:
            return max(int(raw), 0)
        except (ValueError, TypeError):
            pass
    return int(min(2 ** attempt + random.uniform(0, 2), 60))


spotify_queue = ApiQueue()
