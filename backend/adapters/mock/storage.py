import os
from pathlib import Path
from typing import BinaryIO
from urllib.parse import quote

from ..storage import StorageAdapter


class MockStorageAdapter(StorageAdapter):
    def __init__(self, root: str | Path | None = None):
        self.root = Path(root or os.getenv("MOCK_STORAGE_PATH", ".localdev/uploads"))
        self.root.mkdir(parents=True, exist_ok=True)
        from cryptography.fernet import Fernet
        key_path = self.root / ".storage-key"
        if not key_path.exists():
            try:
                with key_path.open("xb") as handle:
                    handle.write(Fernet.generate_key())
            except FileExistsError:
                pass
        self.cipher = Fernet(key_path.read_bytes())

    def _path(self, key: str) -> Path:
        safe_key = Path(key)
        if safe_key.is_absolute() or ".." in safe_key.parts:
            raise ValueError("Invalid storage key")
        path = self.root / safe_key
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    def upload(self, key: str, content: bytes | BinaryIO, content_type: str = "application/octet-stream") -> str:
        data = content if isinstance(content, bytes) else content.read()
        self._path(key).write_bytes(b"CASESEVA_ENCRYPTED_V1\n" + self.cipher.encrypt(data))
        return f"local://uploads/{quote(key)}"

    def download(self, key: str) -> bytes:
        path = self._path(key)
        data = path.read_bytes()
        prefix = b"CASESEVA_ENCRYPTED_V1\n"
        if data.startswith(prefix):
            return self.cipher.decrypt(data[len(prefix):])
        # Preserve old development uploads and encrypt them on first authenticated access.
        path.write_bytes(prefix + self.cipher.encrypt(data))
        return data

    def delete(self, key: str) -> None:
        path = self._path(key)
        if path.exists():
            path.unlink()

    def list(self, prefix: str = "") -> list[str]:
        return [
            path.relative_to(self.root).as_posix()
            for path in self.root.rglob("*")
            if path.is_file() and path.name != ".storage-key" and path.relative_to(self.root).as_posix().startswith(prefix)
        ]
