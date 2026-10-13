import json
import os
import time
from pathlib import Path
from .file_lock import DatabaseFileLock
from typing import Any

from ..database import DatabaseAdapter


class MockDatabaseAdapter(DatabaseAdapter):
    def __init__(self, path: str | Path | None = None):
        self.path = Path(path or os.getenv("MOCK_DATABASE_PATH", ".localdev/database.json"))
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = DatabaseFileLock(self.path)
        with self._lock:
            if not self.path.exists():
                self._write({})

    def _read(self) -> dict[str, dict[str, Any]]:
        last_err = None
        for attempt in range(50):
            try:
                if self.path.exists():
                    text = self.path.read_text(encoding="utf-8")
                    if text.strip():
                        return json.loads(text)
                    else:
                        last_err = ValueError("Database file is empty")
                else:
                    if attempt > 3:
                        self.path.parent.mkdir(parents=True, exist_ok=True)
                        self.path.write_text("{}", encoding="utf-8")
                        return {}
                    last_err = FileNotFoundError("Database file does not exist")
            except Exception as err:
                last_err = err
            time.sleep(0.01)
        if last_err:
            print(f"[ERROR MOCK DB READ]: failed to read {self.path}: {last_err}", flush=True)
            raise RuntimeError(f"Failed to read database: {last_err}")
        return {}

    def _write(self, data: dict[str, dict[str, Any]]) -> None:
        content = json.dumps(data, indent=2)
        for attempt in range(50):
            try:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                temporary = self.path.with_suffix(self.path.suffix + ".pending")
                temporary.write_text(content, encoding="utf-8")
                os.replace(temporary, self.path)
                return
            except Exception:
                time.sleep(0.02)
        raise RuntimeError("Local database write failed.")

    def mutate(self, collection: str, record_id: str, transform) -> dict[str, Any]:
        with self._lock:
            data = self._read()
            record = data.get(collection, {}).get(record_id)
            if record is None:
                raise KeyError(record_id)
            record.update(transform(dict(record)))
            self._write(data)
            return dict(record)

    def create(self, collection: str, record: dict[str, Any]) -> dict[str, Any]:
        record_id = str(record["id"])
        with self._lock:
            data = self._read()
            bucket = data.setdefault(collection, {})
            if record_id in bucket:
                raise ValueError(f"Record already exists: {record_id}")
            bucket[record_id] = dict(record)
            self._write(data)
        return dict(record)

    def create_local_review_admin(self, user: dict[str, Any]) -> None:
        """Atomically claim the one-time bootstrap and insert a new dedicated user."""
        with self._lock:
            data = self._read()
            users = data.get('users', {})
            if any(u.get('email', '').strip().lower() == user['email'] for u in users.values()):
                raise ValueError('Account already exists; bootstrap never promotes existing users')
            if data.get('review_admin_bootstrap') or any(u.get('role') == 'admin' for u in users.values()):
                raise ValueError('Local review administrator bootstrap has already been used or an admin exists')
            if user.get('role') != 'admin' or user.get('provisioning', {}).get('scope') != 'PHASE4_REVIEW_ONLY':
                raise ValueError('Invalid local review provisioning request')
            data.setdefault('users', {})[user['id']] = dict(user)
            data['review_admin_bootstrap'] = {'one-time': {'id': 'one-time', 'user_id': user['id'],
                **user['provisioning']}}
            self._write(data)

    def get(self, collection: str, record_id: str) -> dict[str, Any] | None:
        with self._lock:
            data = self._read()
            record = data.get(collection, {}).get(record_id)
            return dict(record) if record else None

    def update(self, collection: str, record_id: str, changes: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            data = self._read()
            bucket = data.get(collection, {})
            record = bucket.get(record_id)
            if record is None:
                raise KeyError(record_id)
            record.update(changes)
            self._write(data)
            return dict(record)

    def delete(self, collection: str, record_id: str) -> bool:
        with self._lock:
            data = self._read()
            bucket = data.get(collection, {})
            deleted = record_id in bucket
            if deleted:
                del bucket[record_id]
                self._write(data)
            return deleted

    def list(self, collection: str) -> list[dict[str, Any]]:
        with self._lock:
            data = self._read()
            return [dict(record) for record in data.get(collection, {}).values()]
