"""Graph algorithms: loop detection, topological order, downstream search."""

from __future__ import annotations

from collections import deque


def find_loops(node_ids: list[str], successors: dict[str, set[str]]) -> list[list[str]]:
    """Strongly connected components that form a cycle (Tarjan's algorithm).

    A component is a loop when it has more than one node or a node that feeds
    itself. Nodes that merely sit *downstream* of a loop are not part of it.
    Iterative, so a long chain cannot hit Python's recursion limit.
    """
    index: dict[str, int] = {}
    low: dict[str, int] = {}
    on_stack: set[str] = set()
    stack: list[str] = []
    loops: list[list[str]] = []
    counter = 0

    for root in node_ids:
        if root in index:
            continue
        work = [(root, iter(sorted(successors.get(root, ()))))]
        index[root] = low[root] = counter
        counter += 1
        stack.append(root)
        on_stack.add(root)
        while work:
            node, children = work[-1]
            advanced = False
            for child in children:
                if child not in index:
                    index[child] = low[child] = counter
                    counter += 1
                    stack.append(child)
                    on_stack.add(child)
                    work.append((child, iter(sorted(successors.get(child, ())))))
                    advanced = True
                    break
                if child in on_stack:
                    low[node] = min(low[node], index[child])
            if advanced:
                continue
            work.pop()
            if work:
                parent = work[-1][0]
                low[parent] = min(low[parent], low[node])
            if low[node] == index[node]:
                component = []
                while True:
                    member = stack.pop()
                    on_stack.discard(member)
                    component.append(member)
                    if member == node:
                        break
                if len(component) > 1 or node in successors.get(node, ()):
                    loops.append(sorted(component))
    return loops


def topological_order(node_ids: list[str], successors: dict[str, set[str]]) -> list[str]:
    """Kahn's algorithm over ``node_ids`` (edges leaving the set are ignored).

    Nodes that cannot be ordered (they sit on a cycle) are left out.
    """
    members = set(node_ids)
    indegree = {n: 0 for n in node_ids}
    for n in node_ids:
        for m in successors.get(n, ()):
            if m in members:
                indegree[m] += 1
    queue = deque(n for n in node_ids if indegree[n] == 0)
    order: list[str] = []
    while queue:
        n = queue.popleft()
        order.append(n)
        for m in sorted(successors.get(n, ())):
            if m in members:
                indegree[m] -= 1
                if indegree[m] == 0:
                    queue.append(m)
    return order


def downstream(start: str, successors: dict[str, set[str]]) -> list[str]:
    """Every node reachable from ``start`` (excluding ``start`` itself)."""
    seen: set[str] = {start}
    out: list[str] = []
    queue = deque([start])
    while queue:
        n = queue.popleft()
        for m in sorted(successors.get(n, ())):
            if m not in seen:
                seen.add(m)
                out.append(m)
                queue.append(m)
    return out
