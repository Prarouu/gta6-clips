import logging, random, time

log = logging.getLogger("retry")


def retry(fn, attempts=3, base_delay=2.0, exceptions=(Exception,), label="op", no_retry=()):
    """Run fn() with exponential backoff + jitter. Exceptions in no_retry are raised immediately."""
    last = None
    for i in range(1, attempts + 1):
        try:
            return fn()
        except no_retry:
            raise
        except exceptions as e:
            last = e
            if i == attempts:
                break
            delay = base_delay * (2 ** (i - 1)) + random.uniform(0, 0.5)
            log.warning("op=%s retry=%d/%d wait=%.1fs error=%s", label, i, attempts, delay, e)
            time.sleep(delay)
    raise last
