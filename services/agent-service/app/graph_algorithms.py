"""Bounded graph traversal over already-authorized relation data."""

from collections import deque
from collections.abc import Callable
from dataclasses import dataclass

from app.graph_extraction import GraphRelation

MAX_PATH_DEPTH = 4
MAX_PATHS = 8


@dataclass
class GraphPathStep:
    source: str
    relation: str
    target: str
    forward: bool = True

    def display(self) -> str:
        if self.forward:
            return f"{self.source} —{self.relation}→ {self.target}"
        return f"{self.source} ←{self.relation}— {self.target}"


def find_relation_paths(adjacency: dict, source: str, target: str, max_depth: int = 3) -> list[list[GraphPathStep]]:
    max_depth = max(1, min(max_depth, MAX_PATH_DEPTH))
    if source not in adjacency or target not in adjacency:
        return []

    paths: list[list[GraphPathStep]] = []
    queue: deque[tuple[str, list[GraphPathStep], set[str]]] = deque([(source, [], {source})])
    while queue and len(paths) < MAX_PATHS:
        node, path, visited = queue.popleft()
        if len(path) >= max_depth:
            continue
        for neighbor, relation_type, forward in adjacency.get(node, []):
            if neighbor in visited:
                continue
            step = (
                GraphPathStep(source=node, relation=relation_type, target=neighbor, forward=True)
                if forward
                else GraphPathStep(source=node, relation=relation_type, target=neighbor, forward=False)
            )
            next_path = path + [step]
            if neighbor == target:
                paths.append(next_path)
                continue
            queue.append((neighbor, next_path, visited | {neighbor}))
    return paths


def relation_neighborhood(names: list[str], relations_for: Callable, depth: int = 2, limit: int = 24) -> list[GraphRelation]:
    depth = max(1, min(depth, MAX_PATH_DEPTH))
    frontier = {name for name in names if name}
    if not frontier:
        return []
    seen_relations: dict[tuple[str, str, str], GraphRelation] = {}
    visited: set[str] = set()
    for _ in range(depth):
        if not frontier or len(seen_relations) >= limit:
            break
        batch = [name for name in frontier if name not in visited]
        visited.update(batch)
        next_frontier: set[str] = set()
        for name in batch:
            for relation in relations_for(name):
                key = (relation.source_name, relation.relation_type, relation.target_name)
                if key not in seen_relations:
                    seen_relations[key] = relation
                next_frontier.add(relation.source_name)
                next_frontier.add(relation.target_name)
        frontier = next_frontier - visited
    return list(seen_relations.values())[:limit]
