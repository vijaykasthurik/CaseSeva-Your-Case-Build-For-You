import os
from io import BytesIO
from typing import BinaryIO
import boto3

from ..storage import StorageAdapter


class RealStorageAdapter(StorageAdapter):
    def __init__(self, bucket_name: str | None = None, region: str | None = None):
        self.bucket_name = bucket_name or os.getenv("S3_BUCKET_NAME", "caseseva-storage-dev").strip()
        self.region = (region or os.getenv("CASESEVA_AWS_REGION") or os.getenv("AWS_REGION", "ap-southeast-2")).strip()
        self.s3_client = boto3.client("s3", region_name=self.region)

    def upload(self, key: str, content: bytes | BinaryIO, content_type: str = "application/octet-stream") -> str:
        data = content if isinstance(content, bytes) else content.read()
        self.s3_client.put_object(
            Bucket=self.bucket_name,
            Key=key,
            Body=data,
            ContentType=content_type,
            ServerSideEncryption="AES256",
        )
        return f"s3://{self.bucket_name}/{key}"

    def download(self, key: str) -> bytes:
        response = self.s3_client.get_object(Bucket=self.bucket_name, Key=key)
        return response["Body"].read()

    def delete(self, key: str) -> None:
        self.s3_client.delete_object(Bucket=self.bucket_name, Key=key)

    def list(self, prefix: str = "") -> list[str]:
        response = self.s3_client.list_objects_v2(Bucket=self.bucket_name, Prefix=prefix)
        return [obj["Key"] for obj in response.get("Contents", [])]
