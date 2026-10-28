"""Group items whose perceptual hashes are within a Hamming distance (BK-tree)."""

from __future__ import annotations

from typing import Callable, Generic, Hashable, TypeVar

T = TypeVar("T")


def hamming(a: int, b: int) -> int:
    return bin(a ^ b).count("1")


class BKTree(Generic[T]):
    def __init__(self, distance: Callable[[int, int], int] = hamming) -> None:
        self.distance = distance
        self.root = None  # [key, item, {dist: child}]

    def add(self, key: int, item: T) -> None:
        node = [key, item, {}]
        if self.root is None:
            self.root = node
            return
        cur = self.root
        while True:
            d = self.distance(key, cur[0])
            if d in cur[2]:
                cur = cur[2][d]
            else:
                cur[2][d] = node
                return

    def search(self, key: int, radius: int) -> list[T]:
        out, stack = [], [self.root] if self.root else []
        while stack:
            k, item, children = stack.pop()
            d = self.distance(key, k)
            if d <= radius:
                out.append(item)
            for cd, child in children.items():
                if d - radius <= cd <= d + radius:
                    stack.append(child)
        return out


def group_similar(items: list[tuple[int, T]], radius: int,
                  ident: Callable[[T], Hashable] = id) -> list[list[T]]:
    """Cluster ``(hash, item)`` pairs; items linked by distance <= radius join."""
    tree: BKTree[int] = BKTree()
    for i, (h, _) in enumerate(items):
        tree.add(h, i)
    parent = list(range(len(items)))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for i, (h, _) in enumerate(items):
        for j in tree.search(h, radius):
            ri, rj = find(i), find(j)
            if ri != rj:
                parent[rj] = ri
    clusters: dict[int, list[T]] = {}
    for i, (_, item) in enumerate(items):
        clusters.setdefault(find(i), []).append(item)
    return [c for c in clusters.values() if len(c) > 1]
