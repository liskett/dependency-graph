from collections import deque

from src.cargo import DependencyError


def dependency_load_order(
    graph: dict[str, list[str]], root: str
) -> list[str]:
    """List reachable dependencies in BFS order, excluding the root."""
    if root not in graph:
        raise DependencyError(f"Root package '{root}' is missing in graph.")
    queue = deque([root])
    seen = {root}
    order: list[str] = []
    while queue:
        current = queue.popleft()
        for target in sorted(graph[current]):
            if target not in graph:
                raise DependencyError(
                    f"Graph references missing dependency '{target}'."
                )
            if target in seen:
                continue
            seen.add(target)
            order.append(target)
            queue.append(target)
    return order
