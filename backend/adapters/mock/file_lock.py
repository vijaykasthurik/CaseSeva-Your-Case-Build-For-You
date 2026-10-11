"""Serialize local JSON adapter instances and processes; never used by cloud adapters."""
import os
import time
from pathlib import Path
from threading import Lock

_guard = Lock()
_locks = {}


class DatabaseFileLock:
    def __init__(self, path):
        self.path = str(Path(path).resolve()) + ".lock"
        with _guard:
            self.thread_lock = _locks.setdefault(self.path, Lock())

    def __enter__(self):
        self.thread_lock.acquire()
        try:
            self.file = open(self.path, "a+b")
            self.file.seek(0, 2)
            if not self.file.tell():
                self.file.write(b"0")
                self.file.flush()
            deadline = time.monotonic() + 30
            while True:
                try:
                    self.file.seek(0)
                    if os.name == "nt":
                        import msvcrt
                        msvcrt.locking(self.file.fileno(), msvcrt.LK_NBLCK, 1)
                    else:
                        import fcntl
                        fcntl.flock(self.file, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    return self
                except OSError:
                    if time.monotonic() >= deadline:
                        raise TimeoutError("Local database is busy")
                    time.sleep(0.01)
        except BaseException:
            if hasattr(self, "file"):
                self.file.close()
            self.thread_lock.release()
            raise

    def __exit__(self, *args):
        try:
            self.file.seek(0)
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(self.file.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.file, fcntl.LOCK_UN)
        finally:
            self.file.close()
            self.thread_lock.release()
