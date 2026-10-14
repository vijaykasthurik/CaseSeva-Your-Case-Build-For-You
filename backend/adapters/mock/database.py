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

    def create_additional_review_admin(self, user: dict[str, Any], *, session_token: str) -> None:
        """Recheck authorization and duplicates atomically; leave bootstrap history untouched."""
        with self._lock:
            data = self._read()
            session = data.get('sessions', {}).get(session_token)
            users = data.get('users', {})
            authorizer = users.get(session.get('user_id')) if session else None
            if not authorizer or authorizer.get('role') != 'admin':
                raise ValueError('An authenticated existing administrator is required')
            if not data.get('review_admin_bootstrap'):
                raise ValueError('Existing review bootstrap history is required; onboarding cannot bootstrap')
            if user['id'] in users or any(u.get('email', '').strip().lower() == user['email'] for u in users.values()):
                raise ValueError('Account already exists; onboarding never promotes existing users')
            audit = user.get('provisioning', {})
            if (user.get('role') != 'admin' or audit.get('scope') != 'PHASE4_REVIEW_ONLY'
                    or audit.get('authorized_by') != authorizer['id']):
                raise ValueError('Invalid local reviewer onboarding request')
            data.setdefault('users', {})[user['id']] = dict(user)
            data.setdefault('review_admin_provisioning', {})[user['id']] = {
                'id': user['id'], 'user_id': user['id'], **audit}
            self._write(data)

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

    def reset_local_review_admin_password(
        self, email: str, new_password_hash: str, *, operator: str
    ) -> dict[str, Any]:
        """Atomically rotates the password of an existing review admin.

        Fails closed if:
        - account not found
        - account is not admin
        - database is not an isolated review identity database
        """
        from ...models.case import utc_now
        from uuid import uuid4

        with self._lock:
            target_str = str(self.path.resolve()).replace("\\", "/")
            if not ("identity" in target_str or "phase4" in target_str or "test" in target_str):
                raise ValueError("Password rotation is only permitted on the isolated review identity database")

            data = self._read()
            users = data.get("users", {})
            normalized = email.strip().lower()
            user_entry = next((u for u in users.values() if u.get("email", "").strip().lower() == normalized), None)
            if not user_entry:
                raise ValueError(f"Review administrator account '{email}' not found")
            if user_entry.get("role") != "admin":
                raise ValueError(f"Account '{email}' is not an administrator; role promotion/rotation refused")

            user_id = user_entry["id"]
            user_entry["password_hash"] = new_password_hash
            user_entry["password_rotated_at"] = utc_now()

            # Invalidate all active sessions for this admin user
            sessions = data.get("sessions", {})
            invalidated = [sid for sid, s in list(sessions.items()) if s.get("user_id") == user_id]
            for sid in invalidated:
                del sessions[sid]

            # Record immutable audit event (NEVER store password or password_hash)
            now = utc_now()
            rotations = data.setdefault("review_admin_password_rotations", {})
            rotation_id = uuid4().hex
            rotations[rotation_id] = {
                "id": rotation_id,
                "user_id": user_id,
                "email": user_entry["email"],
                "local_operator": operator,
                "timestamp": now,
                "operation_type": "LOCAL_REVIEW_ADMIN_PASSWORD_ROTATION",
                "sessions_invalidated": len(invalidated),
            }

            self._write(data)
            return dict(user_entry)
