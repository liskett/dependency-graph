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
)
from src.versioned_repository import VersionedRepository


def print_graph(graph: dict[str, list[str]]) -> None:
    """Print all versioned nodes and their outgoing dependency edges."""
    print("Dependency graph:")
    for package in sorted(graph):
        rendered = ", ".join(graph[package]) or "(none)"
        print(f"{package} -> {rendered}")


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
    except DependencyError as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1
    print_graph(graph)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
