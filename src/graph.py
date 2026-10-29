"""Build version-aware dependency graphs using recursive BFS."""

from collections.abc import Callable

from src.cargo import Dependency, DependencyError


DependencyLoader = Callable[[str, str], list[Dependency]]
VersionResolver = Callable[[Dependency], str]
EMPTY = 0
DEPTH_STEP = 1


def node_id(package: str, version: str) -> str:
    """Identify one exact package version in the dependency graph."""
    return f"{package}@{version}"


class GraphBuilder:
    """Store graph state during a recursive breadth-first traversal."""

    def __init__(
        self,
        package: str,
        version: str,
        max_depth: int,
        dependency_loader: DependencyLoader,
        version_resolver: VersionResolver,
    ) -> None:
        self.package = package
        self.version = version
        self.max_depth = max_depth
        self.dependency_loader = dependency_loader
        self.version_resolver = version_resolver
        self.graph: dict[str, list[str]] = {node_id(package, version): []}
        self.discovered = set(self.graph)

    def build(self) -> dict[str, list[str]]:
        """Return the graph after expanding up to the chosen depth."""
        if self.max_depth < EMPTY:
            raise DependencyError("Maximum depth cannot be negative.")
        if self.max_depth == EMPTY:
            self.dependency_loader(self.package, self.version)
            return self.graph
        try:
            self._expand_level([(self.package, self.version)], EMPTY)
        except RecursionError as error:
            raise DependencyError(
                "Dependency graph is too deep for recursive BFS."
            ) from error
        return self.graph

    def _expand_level(
        self, frontier: list[tuple[str, str]], depth: int
    ) -> None:
        """Expand one BFS level and recursively visit the next level."""
        if depth >= self.max_depth or not frontier:
            return
        next_frontier: list[tuple[str, str]] = []
        for package, version in frontier:
            current = node_id(package, version)
            adjacent: set[str] = set(self.graph[current])
            dependencies = self.dependency_loader(package, version)
            self._add_edges(
                dependencies, depth, adjacent, next_frontier
            )
            self.graph[current] = sorted(adjacent)
        self._expand_level(next_frontier, depth + DEPTH_STEP)

    def _add_edges(
        self,
        dependencies: list[Dependency],
        depth: int,
        adjacent: set[str],
        next_frontier: list[tuple[str, str]],
    ) -> None:
        """Record versioned edges and queue newly discovered nodes."""
        for dependency in dependencies:
            version = self.version_resolver(dependency)
            if not version:
                raise DependencyError(
                    f"No version resolved for '{dependency.name}'."
                )
            target = node_id(dependency.name, version)
            adjacent.add(target)
            self.graph.setdefault(target, [])
            if target in self.discovered:
                continue
            self.discovered.add(target)
            if depth + DEPTH_STEP < self.max_depth:
                next_frontier.append((dependency.name, version))


def build_dependency_graph(
    package: str,
    version: str,
    max_depth: int,
    dependency_loader: DependencyLoader,
    version_resolver: VersionResolver,
) -> dict[str, list[str]]:
    """Build a version-aware graph by recursively expanding BFS levels."""
    builder = GraphBuilder(
        package, version, max_depth, dependency_loader, version_resolver
    )
    return builder.build()
