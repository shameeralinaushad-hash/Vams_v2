import time
import math
from threading import Lock

# In-memory on purpose: this is a speed bump against casual brute-forcing,
# not a hardened defense. Resets on app restart, which is fine -- an app
# restart is already a natural pause, and this never touches real user data
# or the database, so there's nothing to migrate or persist here.

MAX_ATTEMPTS = 5
LOCKOUT_SECONDS = 15 * 60  # 15 minutes

_failed_attempts = {}  # email -> list of failure timestamps within the window
_lock = Lock()


def _prune(email, now):
    attempts = _failed_attempts.get(email, [])
    attempts = [t for t in attempts if now - t < LOCKOUT_SECONDS]
    if attempts:
        _failed_attempts[email] = attempts
    else:
        _failed_attempts.pop(email, None)
    return attempts


def is_locked_out(email):
    if not email:
        return False
    with _lock:
        attempts = _prune(email, time.time())
        return len(attempts) >= MAX_ATTEMPTS


def record_failure(email):
    if not email:
        return
    with _lock:
        now = time.time()
        attempts = _prune(email, now)
        attempts.append(now)
        _failed_attempts[email] = attempts


def clear_failures(email):
    if not email:
        return
    with _lock:
        _failed_attempts.pop(email, None)


def seconds_until_unlock(email):
    with _lock:
        attempts = _prune(email, time.time())
        if not attempts:
            return 0
        oldest = min(attempts)
        return max(0, int(LOCKOUT_SECONDS - (time.time() - oldest)))


def minutes_until_unlock(email):
    return max(1, math.ceil(seconds_until_unlock(email) / 60))