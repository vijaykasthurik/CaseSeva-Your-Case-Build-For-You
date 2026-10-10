import os
from decimal import Decimal
from typing import Any
import boto3
from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError

from ..database import DatabaseAdapter


def _floats_to_decimals(obj: Any) -> Any:
    if isinstance(obj, float):
        return Decimal(str(obj))
    if isinstance(obj, dict):
        return {k: _floats_to_decimals(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_floats_to_decimals(v) for v in obj]
    return obj


def _decimals_to_floats(obj: Any) -> Any:
    if isinstance(obj, Decimal):
        return int(obj) if obj % 1 == 0 else float(obj)
    if isinstance(obj, dict):
        return {k: _decimals_to_floats(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_decimals_to_floats(v) for v in obj]
    return obj


class RealDatabaseAdapter(DatabaseAdapter):
    def __init__(self, table_name: str | None = None, region: str | None = None):
        self.table_name = table_name or os.getenv("DYNAMODB_TABLE_NAME", "caseseva-data-dev").strip()
        self.region = (region or os.getenv("CASESEVA_AWS_REGION") or os.getenv("AWS_REGION", "ap-southeast-2")).strip()
        self.dynamodb = boto3.resource("dynamodb", region_name=self.region)
        self.table = self.dynamodb.Table(self.table_name)

    def create(self, collection: str, record: dict[str, Any]) -> dict[str, Any]:
        record_id = str(record["id"])
        item = _floats_to_decimals(dict(record))
        item["PK"] = collection
        item["SK"] = record_id
        try:
            self.table.put_item(
                Item=item,
                ConditionExpression="attribute_not_exists(PK) AND attribute_not_exists(SK)",
            )
        except ClientError as e:
            if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
                raise ValueError(f"Record already exists: {record_id}") from e
            raise
        return dict(record)

    def get(self, collection: str, record_id: str) -> dict[str, Any] | None:
        response = self.table.get_item(Key={"PK": collection, "SK": record_id}, ConsistentRead=True)
        item = response.get("Item")
        if not item:
            return None
        item.pop("PK", None)
        item.pop("SK", None)
        return _decimals_to_floats(item)

    def update(self, collection: str, record_id: str, changes: dict[str, Any]) -> dict[str, Any]:
        return self.mutate(collection, record_id, lambda current: changes)

    def mutate(self, collection: str, record_id: str, transform) -> dict[str, Any]:
        for attempt in range(10):
            current = self.get(collection, record_id)
            if current is None:
                raise KeyError(record_id)
            revision = current.get("_revision")
            current.update(transform(dict(current)))
            current["_revision"] = (revision or 0) + 1
            item = _floats_to_decimals(dict(current))
            item.update({"PK": collection, "SK": record_id})
            options = {"ConditionExpression": "attribute_exists(PK) AND " + ("attribute_not_exists(#rev)" if revision is None else "#rev = :previous"), "ExpressionAttributeNames": {"#rev": "_revision"}}
            if revision is not None:
                options["ExpressionAttributeValues"] = {":previous": revision}
            try:
                self.table.put_item(Item=item, **options)
                return current
            except ClientError as exc:
                if exc.response["Error"]["Code"] != "ConditionalCheckFailedException":
                    raise
        raise RuntimeError("Concurrent database updates could not be resolved; retry the operation.")

    def delete(self, collection: str, record_id: str) -> bool:
        try:
            response = self.table.delete_item(
                Key={"PK": collection, "SK": record_id},
                ReturnValues="ALL_OLD",
            )
            return "Attributes" in response
        except ClientError:
            return False

    def list(self, collection: str) -> list[dict[str, Any]]:
        response = self.table.query(
            KeyConditionExpression=Key("PK").eq(collection)
        )
        items = response.get("Items", [])
        while response.get("LastEvaluatedKey"):
            response = self.table.query(KeyConditionExpression=Key("PK").eq(collection), ExclusiveStartKey=response["LastEvaluatedKey"])
            items.extend(response.get("Items", []))
        results = []
        for item in items:
            item.pop("PK", None)
            item.pop("SK", None)
            results.append(_decimals_to_floats(item))
        return results
