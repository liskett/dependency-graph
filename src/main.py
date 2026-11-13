"""Command-line entry point for version-aware dependency analysis."""

import sys

from src.cargo import (
    Dependency,
    DependencyError,
    fetch_dependencies,
    resolve_dependency_version,
)
from src.config import AppConfig, parse_config
from src.graph import (
    DependencyLoader,
    VersionResolver,
    build_dependency_graph,
    node_id,
)
from src.load_order import dependency_load_order
from src.versioned_repository import VersionedRepository
from src.visualization import save_visualization


def print_graph(graph: dict[str, list[str]]) -> None:
    """Print all versioned nodes and their outgoing dependency edges."""
    print("Dependency graph:")
    for package in sorted(graph):
        rendered = ", ".join(graph[package]) or "(none)"
        print(f"{package} -> {rendered}")


def print_load_order(order: list[str]) -> None:
    """Print a deterministic BFS order for dependency discovery."""
    print("Dependency load order (BFS discovery, root excluded):")
    for position, package in enumerate(order, start=1):
        print(f"{position}. {package}")
    if not order:
        print("(none)")


def test_version(dependency: Dependency) -> str:
    """Return the exact version stored in a test dependency."""
    if dependency.requirement is None:
        raise DependencyError("Test dependency has no exact version.")
    return dependency.requirement


def make_loaders(
    config: AppConfig,
) -> tuple[DependencyLoader, VersionResolver]:
    """Choose dependency and version loaders for the selected repository."""
    if config.test_mode:
        repository = VersionedRepository(config.repository)
        return repository.dependencies, test_version

    def registry_loader(package: str, version: str) -> list[Dependency]:
        """Fetch the direct dependencies of one exact crate version."""
        return fetch_dependencies(config.repository, package, version)

    def registry_version(dependency: Dependency) -> str:
        """Resolve one Cargo requirement to an exact crate version."""
        return resolve_dependency_version(
            config.repository,
            dependency.name,
            dependency.requirement or "*",
        )

    return registry_loader, registry_version


def main() -> int:
    """Build and print the dependency graph from CLI settings."""
    config = parse_config()
    try:
        loader, resolver = make_loaders(config)
        graph = build_dependency_graph(
            config.package,
            config.version,
            config.max_depth,
            loader,
            resolver,
        )
        if config.show_load_order:
            root = node_id(config.package, config.version)
            order = dependency_load_order(graph, root)
        elif config.visualize:
            root = node_id(config.package, config.version)
            mermaid = save_visualization(graph, root, config.output)
    except DependencyError as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1
    if config.show_load_order:
        print_load_order(order)
    elif config.visualize:
        print("Mermaid diagram:")
        print(mermaid)
        print(f"Saved SVG: {config.output}")
    else:
        print_graph(graph)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
