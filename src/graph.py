"""Build dependency graphs using recursive breadth-first traversal."""

from collections.abc import Callable

from src.cargo import Dependency, DependencyError


DependencyLoader = Callable[[str, str | None], list[Dependency]]
VersionResolver = Callable[[Dependency], str | None]
EMPTY = 0
DEPTH_STEP = 1


class _GraphBuilder:
    """Keep recursive BFS state outside the public entry point."""

    def __init__(
        self,
        package: str,
        version: str,
        max_depth: int,
        dependency_loader: DependencyLoader,
        version_resolver: VersionResolver | None,
    ) -> None:
        self.package = package
        self.version = version
        self.max_depth = max_depth
        self.dependency_loader = dependency_loader
        self.version_resolver = version_resolver
        self.graph: dict[str, list[str]] = {package: []}
        self.discovered = {package}

    def build(self) -> dict[str, list[str]]:
        """Run the recursive breadth-first traversal and return its graph."""
        if self.max_depth < EMPTY:
            raise DependencyError("Maximum depth cannot be negative.")
        if self.max_depth > EMPTY:
            self._expand_level([(self.package, self.version)], 0)
        return self.graph

    def _expand_level(
        self, frontier: list[tuple[str, str | None]], depth: int
    ) -> None:
        """Expand one BFS level, then recursively process the next level."""
        if depth >= self.max_depth or not frontier:
            return
        next_frontier: list[tuple[str, str | None]] = []
        for current_package, current_version in frontier:
            dependencies = self.dependency_loader(
                current_package, current_version
            )
            adjacent = set(self.graph.setdefault(current_package, []))
            self._add_edges(
                dependencies, depth, adjacent, next_frontier
            )
            self.graph[current_package] = sorted(adjacent)
        self._expand_level(next_frontier, depth + DEPTH_STEP)

    def _add_edges(
        self,
        dependencies: list[Dependency],
        depth: int,
        adjacent: set[str],
        next_frontier: list[tuple[str, str | None]],
    ) -> None:
        """Record edges and queue each newly discovered package once."""
        for dependency in dependencies:
            adjacent.add(dependency.name)
            self.graph.setdefault(dependency.name, [])
            if dependency.name in self.discovered:
                continue
            self.discovered.add(dependency.name)
            if depth + DEPTH_STEP >= self.max_depth:
                continue
            version = None
            if self.version_resolver is not None:
                version = self.version_resolver(dependency)
            next_frontier.append((dependency.name, version))


def build_dependency_graph(
    package: str,
    version: str,
    max_depth: int,
    dependency_loader: DependencyLoader,
    version_resolver: VersionResolver | None = None,
) -> dict[str, list[str]]:
    """Build a dependency graph using a recursive breadth-first traversal.

    Depth is measured in edges from the root. Zero includes only the root;
    one includes its direct dependency edges.
    """
    builder = _GraphBuilder(
        package, version, max_depth, dependency_loader, version_resolver
    )
    return builder.build()
