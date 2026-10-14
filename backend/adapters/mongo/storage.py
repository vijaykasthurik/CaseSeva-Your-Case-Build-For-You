"""MongoDB and GridFS storage adapter for CaseSeva."""
import hashlib
import io
import os
from typing import BinaryIO, Any
import pymongo
from gridfs import GridFS, NoFile

from ..storage import StorageAdapter
from ...database.mongo_client import get_mongo_db, get_gridfs
from ...models.case import utc_now


class MongoGridFSStorageAdapter(StorageAdapter):
    def __init__(self, db_name: str | None = None, uri: str | None = None):
        self.db_name = db_name or os.getenv("MONGODB_DATABASE", "caseseva").strip()
        self.uri = uri or os.getenv("MONGODB_URI", "mongodb://127.0.0.1:27017").strip()
        self.db = get_mongo_db(self.db_name, self.uri)
        self.fs = get_gridfs(self.db)

    def upload(self, key: str, content: bytes | BinaryIO, content_type: str = "application/octet-stream") -> str:
        data = content if isinstance(content, bytes) else content.read()
        sha256 = hashlib.sha256(data).hexdigest()
        byte_size = len(data)

        # Remove any existing versions for this exact key to maintain unique key resolution
        self.delete(key)

        grid_file_id = self.fs.put(
            data,
            filename=key,
            contentType=content_type,
            metadata={
                "key": key,
                "sha256": sha256,
                "size": byte_size,
                "uploaded_at": utc_now(),
            }
        )
        return f"gridfs://{self.db_name}/{key}"

    def download(self, key: str) -> bytes:
        try:
            grid_file = self.fs.find_one({"filename": key}, sort=[("uploadDate", pymongo.DESCENDING)])
            if grid_file is None:
                raise FileNotFoundError(f"File not found in GridFS: {key}")
            return grid_file.read()
        except NoFile as exc:
            raise FileNotFoundError(f"File not found in GridFS: {key}") from exc

    def get_file_metadata(self, key: str) -> dict[str, Any] | None:
        grid_file = self.fs.find_one({"filename": key}, sort=[("uploadDate", pymongo.DESCENDING)])
        if grid_file is None:
            return None
        meta = grid_file.metadata or {}
        return {
            "gridfs_file_id": str(grid_file._id),
            "filename": grid_file.filename,
            "contentType": getattr(grid_file, "contentType", "application/octet-stream"),
            "size": grid_file.length,
            "sha256": meta.get("sha256", hashlib.sha256(grid_file.read()).hexdigest()),
            "upload_date": str(grid_file.upload_date),
            **meta
        }

    def delete(self, key: str) -> None:
        for file in self.fs.find({"filename": key}):
            self.fs.delete(file._id)

    def list(self, prefix: str = "") -> list[str]:
        query = {"filename": {"$regex": f"^{prefix}"}} if prefix else {}
        keys = set()
        for file in self.fs.find(query):
            if file.filename:
                keys.add(file.filename)
        return sorted(list(keys))
