"""Explicit registrations, validated dependency graphs and output ownership."""
from dataclasses import dataclass
from typing import Callable
from ..models.orchestration import AgentContract


def overlaps(a, b):
    return a == b or a.startswith(b + ".") or b.startswith(a + ".")


@dataclass(frozen=True)
class Registration:
    contract: AgentContract
    handler: Callable | None = None
    validators: dict | None = None
    enabled: bool = True
    live_validated: bool = False
    available: bool = True
    granular_writes: tuple = ()


class AgentRegistry:
    def __init__(self):
        self._agents = {}

    def register(self, contract, handler=None, validators=None, *, enabled=True, live_validated=False, available=True, granular_writes=()):
        contract = AgentContract.model_validate(contract)
        name = contract.agent_type
        if name in self._agents:
            raise ValueError("Duplicate agent registration: " + name)
        if handler is not None and set(validators or {}) != set(contract.writes):
            raise ValueError("Every implemented output needs a validator")
        if live_validated and handler is None:
            raise ValueError("An unavailable agent cannot be live validated")
        if not set(granular_writes).issubset(contract.writes):
            raise ValueError('Granular writes must be declared owned output paths')
        self._agents[name] = Registration(contract, handler, validators, enabled, live_validated, available, tuple(granular_writes))
        return self

    def get(self, name):
        if name not in self._agents:
            raise ValueError("Unregistered agent: " + name)
        return self._agents[name]

    def describe(self):
        return [{**r.contract.model_dump(mode="json"), "registered": True,
                 "implemented": r.handler is not None, "available": r.enabled and r.available and r.handler is not None,
                 "enabled": r.enabled, "live_validated": r.live_validated}
                for r in self._agents.values()]

    def graph(self, selected):
        """Expand prerequisites from contracts, not a permanent stage list."""
        graph, visiting = {}, set()
        def visit(name):
            if name in visiting:
                raise ValueError("Dependency cycle: " + name)
            if name in graph:
                return
            contract = self.get(name).contract
            visiting.add(name)
            for dep in contract.dependencies:
                visit(dep)
            visiting.remove(name)
            graph[name] = list(contract.dependencies)
        for name in selected:
            visit(name)
        if len(graph) > 64:
            raise ValueError("Execution plan exceeds 64 nodes")
        return graph

    def select_pack(self, pack):
        return [name for name, r in self._agents.items() if r.contract.pack == pack]

    def watched_paths(self, name):
        c = self.get(name).contract
        paths = set(c.watched_paths())
        for dependency in c.dependencies:
            outputs = self.get(dependency).contract.writes
            # Explicit field reads narrow a dependency. Otherwise watch all of
            # its outputs so a metadata-only edge cannot hide stale input.
            if not any(overlaps(p, output) for p in paths for output in outputs):
                paths.update(outputs)
        return tuple(sorted(paths))

    def compatible(self, left, right):
        a, b = self.get(left).contract, self.get(right).contract
        return a.can_run_concurrently and b.can_run_concurrently and not any(
            overlaps(x, y) for x in a.writes for y in b.writes + self.watched_paths(right)) and not any(
            overlaps(x, y) for x in b.writes for y in self.watched_paths(left))


def production_registry(adapters=None):
    from .understanding_agents import core_registry
    return core_registry(adapters)
