"""Size-capped append-only log file, a drop-in for `open(path, "a", buffering=1)`.

Every server in this backend writes a plain, human-readable per-connection log
(plus session_manager's machine-readable wire.jsonl) with an ordinary appending
file handle. Those files never rotated and had no size ceiling, so an
unauthenticated peer that simply keeps talking - or a long uptime with real
traffic - grows them until the disk fills, which takes the whole backend down
(run_all.py stops every server when one dies).

RotatingLog keeps the same tiny surface the servers already use (`write`,
`flush`, context manager) so nothing else has to change, and renames the file
aside once it passes MAX_BYTES. Rotation is by rename, not truncation, so the
most recent history survives: `<path>` -> `<path>.1` -> ... -> `<path>.<n>`,
oldest dropped. Total disk per log file is therefore bounded at
MAX_BYTES * (BACKUPS + 1).

stdlib `logging.handlers.RotatingFileHandler` does the same job, but these
servers write pre-formatted multi-line blocks straight to a file handle rather
than going through the `logging` module; wrapping that surface is far less
invasive than restructuring five servers' logging around records and formatters.
"""
import os
import threading

# 64 MiB per file, 3 older generations kept -> at most 256 MiB per log file.
# Generous for this project's debug-logging usefulness while still bounded.
MAX_BYTES = int(os.environ.get("TLOU_LOG_MAX_BYTES", str(64 * 1024 * 1024)))
BACKUPS = int(os.environ.get("TLOU_LOG_BACKUPS", "3"))


class RotatingLog:
    def __init__(self, path, max_bytes=None, backups=None):
        self.path = path
        self.max_bytes = MAX_BYTES if max_bytes is None else max_bytes
        self.backups = BACKUPS if backups is None else backups
        self._lock = threading.Lock()
        self._fp = open(path, "a", buffering=1)
        try:
            self._size = self._fp.tell()
        except OSError:
            self._size = 0

    def _rotate(self):
        """Caller holds the lock. Rename the current file aside and reopen."""
        self._fp.close()
        oldest = f"{self.path}.{self.backups}"
        if os.path.exists(oldest):
            os.remove(oldest)
        for i in range(self.backups - 1, 0, -1):
            src, dst = f"{self.path}.{i}", f"{self.path}.{i + 1}"
            if os.path.exists(src):
                os.replace(src, dst)
        if self.backups > 0:
            os.replace(self.path, f"{self.path}.1")
        else:
            os.remove(self.path)
        self._fp = open(self.path, "a", buffering=1)
        self._size = 0

    def write(self, text):
        data = text if isinstance(text, str) else str(text)
        with self._lock:
            if self.max_bytes > 0 and self._size >= self.max_bytes:
                self._rotate()
            self._fp.write(data)
            self._size += len(data.encode("utf-8", "replace"))

    def flush(self):
        with self._lock:
            self._fp.flush()

    def close(self):
        with self._lock:
            if not self._fp.closed:
                self._fp.close()

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        self.close()
        return False


def capped_appender(entry, limit, label="bytes"):
    """Helper for the servers that build one log block per connection in memory.

    Returns (append, finish): `append(text)` adds to the block until `limit`
    characters have been accumulated and then only counts what it drops;
    `finish()` returns the block with a truncation marker appended if anything
    was dropped. Without a ceiling, a peer that streams data forever (no
    handshake or auth required on these ports) grows the in-memory block until
    the process is OOM-killed.
    """
    box = {"text": entry, "dropped": 0}

    def append(text):
        if box["dropped"] or len(box["text"]) >= limit:
            box["dropped"] += len(text)
            return
        room = limit - len(box["text"])
        if len(text) <= room:
            box["text"] += text
        else:
            box["text"] += text[:room]
            box["dropped"] += len(text) - room

    def finish():
        if box["dropped"]:
            return (box["text"] +
                    f"\n  ... log truncated at {limit} {label}; "
                    f"{box['dropped']} more not logged\n")
        return box["text"]

    return append, finish
