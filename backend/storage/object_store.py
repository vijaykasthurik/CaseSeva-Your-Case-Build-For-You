"""Generic ObjectStore abstraction for CaseSeva binary assets.

Supports MongoDB GridFS (default for local development) and AWS S3 (optional).
AWS credentials are never required unless S3 is explicitly selected.
"""
from abc import ABC, abstractmethod
import hashlib
import os
from typing import Any, BinaryIO
from ..models.case import utc_now


class ObjectStore(ABC):
    @abstractmethod
    def put_object(self, key: str, data: bytes | BinaryIO, content_type: str = "application/octet-stream", metadata: dict[str, Any] | None = None) -> str:
        """Stores object bytes and returns an immutable URI (gridfs://... or s3://...)."""
        raise NotImplementedError

    @abstractmethod
    def get_object(self, key: str) -> bytes:
        """Retrieves raw object bytes."""
        raise NotImplementedError

    @abstractmethod
    def get_object_metadata(self, key: str) -> dict[str, Any] | None:
        """Retrieves verified object metadata (SHA-256, size, MIME type, timestamps)."""
        raise NotImplementedError

    @abstractmethod
    def delete_object(self, key: str) -> None:
        """Deletes object by key."""
        raise NotImplementedError

    @abstractmethod
    def list_objects(self, prefix: str = "") -> list[str]:
        """Lists object keys with matching prefix."""
        raise NotImplementedError

    def object_exists(self, key: str) -> bool:
        """Checks if object exists."""
        return self.get_object_metadata(key) is not None


class MongoGridFSObjectStore(ObjectStore):
    """Local default binary object store using MongoDB GridFS."""

    def __init__(self, db_name: str | None = None, uri: str | None = None):
        from ..adapters.mongo.storage import MongoGridFSStorageAdapter
        self.adapter = MongoGridFSStorageAdapter(db_name=db_name, uri=uri)

    def put_object(self, key: str, data: bytes | BinaryIO, content_type: str = "application/octet-stream", metadata: dict[str, Any] | None = None) -> str:
        return self.adapter.upload(key, data, content_type=content_type)

    def get_object(self, key: str) -> bytes:
        return self.adapter.download(key)

    def get_object_metadata(self, key: str) -> dict[str, Any] | None:
        return self.adapter.get_file_metadata(key)

    def delete_object(self, key: str) -> None:
        self.adapter.delete(key)

    def list_objects(self, prefix: str = "") -> list[str]:
        return self.adapter.list(prefix=prefix)


class S3ObjectStore(ObjectStore):
    """Optional S3 binary object store for cloud deployments."""

    def __init__(self, bucket_name: str | None = None, region: str | None = None):
        self.bucket_name = bucket_name or os.getenv("S3_BUCKET_NAME", "caseseva-storage-dev").strip()
        self.region = (region or os.getenv("CASESEVA_AWS_REGION") or os.getenv("AWS_REGION", "ap-southeast-2")).strip()
        import boto3
        self.s3_client = boto3.client("s3", region_name=self.region)

    def put_object(self, key: str, data: bytes | BinaryIO, content_type: str = "application/octet-stream", metadata: dict[str, Any] | None = None) -> str:
        body = data if isinstance(data, bytes) else data.read()
        sha256 = hashlib.sha256(body).hexdigest()
        meta = {**(metadata or {}), "sha256": sha256, "size": str(len(body))}
        self.s3_client.put_object(
            Bucket=self.bucket_name,
            Key=key,
            Body=body,
            ContentType=content_type,
            Metadata=meta,
            ServerSideEncryption="AES256",
        )
        return f"s3://{self.bucket_name}/{key}"

    def get_object(self, key: str) -> bytes:
        resp = self.s3_client.get_object(Bucket=self.bucket_name, Key=key)
        return resp["Body"].read()

    def get_object_metadata(self, key: str) -> dict[str, Any] | None:
        try:
            head = self.s3_client.head_object(Bucket=self.bucket_name, Key=key)
            return {
                "filename": key,
                "size": head.get("ContentLength"),
                "contentType": head.get("ContentType"),
                "sha256": head.get("Metadata", {}).get("sha256"),
                **head.get("Metadata", {}),
            }
        except Exception:
            return None

    def delete_object(self, key: str) -> None:
        self.s3_client.delete_object(Bucket=self.bucket_name, Key=key)

    def list_objects(self, prefix: str = "") -> list[str]:
        resp = self.s3_client.list_objects_v2(Bucket=self.bucket_name, Prefix=prefix)
        return [item["Key"] for item in resp.get("Contents", [])]


def get_object_store(provider: str | None = None, **kwargs: Any) -> ObjectStore:
    target_provider = (provider if provider is not None else os.getenv("OBJECT_STORE_PROVIDER", "mongodb")).strip().lower()
    if target_provider in {"mongodb", "gridfs", "local"}:
        return MongoGridFSObjectStore(**kwargs)
    elif target_provider in {"s3", "aws"}:
        return S3ObjectStore(**kwargs)
    else:
        raise ValueError(f"Unknown object store provider: {target_provider}. Must be 'mongodb' or 's3'.")
