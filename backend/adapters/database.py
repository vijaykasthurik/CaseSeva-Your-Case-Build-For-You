from abc import ABC, abstractmethod
from typing import Any


class DatabaseAdapter(ABC):
    def mutate(self, collection: str, record_id: str, transform) -> dict[str, Any]:
        current = self.get(collection, record_id)
        if current is None:
            raise KeyError(record_id)
        return self.update(collection, record_id, transform(current))

    def reserve_admin_role_intent(self, intent):
        raise NotImplementedError("Administrator promotion is unsupported by this adapter")

    @abstractmethod
    def create(self, collection: str, record: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def get(self, collection: str, record_id: str) -> dict[str, Any] | None:
        raise NotImplementedError

    @abstractmethod
    def update(self, collection: str, record_id: str, changes: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def delete(self, collection: str, record_id: str) -> bool:
        raise NotImplementedError

    @abstractmethod
    def list(self, collection: str) -> list[dict[str, Any]]:
        raise NotImplementedError
