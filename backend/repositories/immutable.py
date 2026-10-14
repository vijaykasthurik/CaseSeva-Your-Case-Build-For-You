"""Insert-only Mongo history with canonical BSON payload retry comparison."""
from copy import deepcopy

from bson import BSON, json_util
from pymongo.errors import DuplicateKeyError


class HistoryConflict(ValueError):
    """An immutable ID already belongs to a different payload."""


def insert_immutable(collection, document):
    doc = BSON(BSON.encode(deepcopy(document))).decode()
    try:
        collection.insert_one(doc)
    except DuplicateKeyError as exc:
        existing = collection.find_one({"_id": doc["_id"]})
        canonical = lambda value: json_util.dumps(
            value, sort_keys=True, json_options=json_util.CANONICAL_JSON_OPTIONS)
        if existing is None or canonical(existing) != canonical(doc):
            raise HistoryConflict("Immutable record already has a different payload") from exc
    return doc
