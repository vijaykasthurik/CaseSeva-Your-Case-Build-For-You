"""MongoDB client and GridFS provider for local CaseSeva persistence.

Defaults to local MongoDB Community Server on mongodb://127.0.0.1:27017 with database 'caseseva'.
"""
import os
from threading import Lock
import pymongo
from gridfs import GridFS


def get_mongo_uri() -> str:
    return os.getenv("MONGODB_URI", "mongodb://127.0.0.1:27017").strip()


def get_mongo_db_name() -> str:
    return os.getenv("MONGODB_DATABASE", "caseseva").strip()


_clients: dict[str, pymongo.MongoClient] = {}
_clients_lock = Lock()


def get_mongo_client(uri: str | None = None) -> pymongo.MongoClient:
    target_uri = (uri or get_mongo_uri()).strip()
    # Never reuse a connection to a different configured deployment.
    with _clients_lock:
        if target_uri not in _clients:
            _clients[target_uri] = pymongo.MongoClient(
                target_uri,
                serverSelectionTimeoutMS=3000,
                connectTimeoutMS=3000,
                socketTimeoutMS=10000,
                maxPoolSize=50,
                minPoolSize=5,
            )
        return _clients[target_uri]


def get_mongo_db(db_name: str | None = None, uri: str | None = None) -> pymongo.database.Database:
    client = get_mongo_client(uri)
    target_db = db_name or get_mongo_db_name()
    return client[target_db]


def get_gridfs(db: pymongo.database.Database | None = None) -> GridFS:
    database = db if db is not None else get_mongo_db()
    return GridFS(database)


def ping_mongodb(uri: str | None = None) -> bool:
    try:
        client = get_mongo_client(uri)
        client.admin.command("ping")
        return True
    except Exception:
        return False
