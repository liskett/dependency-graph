"""Command-line entry point for the dependency graph visualizer."""

import sys

from src.cargo import (
    Dependency,
    DependencyError,
    fetch_dependencies,
    load_test_dependencies,
    resolve_dependency_version,
)
from src.config import parse_config
from src.graph import build_dependency_graph


def print_graph(graph: dict[str, list[str]]) -> None:
    """Print the graph as a readable adjacency list."""
    print("Dependency graph:")
    for package in sorted(graph):
        dependencies = graph[package]
        rendered = ", ".join(dependencies) if dependencies else "(none)"
        print(f"{package} -> {rendered}")


def print_configuration(config) -> None:
    """Print every user-provided setting as key-value pairs."""
    print("Application configuration:")
    for key, value in config.as_dict().items():
        print(f"{key} = {value}")


def load_package(config, package: str, version: str | None) -> list[Dependency]:
    """Load a package's dependencies from the selected data source."""
    if config.test_mode:
        return load_test_dependencies(config.repository, package)
    if version is None:
        raise DependencyError(
            f"No resolved version is available for '{package}'."
        )
    return fetch_dependencies(config.repository, package, version)


def resolve_version(config, dependency: Dependency) -> str | None:
    """Resolve an exact version for one transitive dependency."""
    if config.test_mode:
        return None
    requirement = dependency.requirement or "*"
    return resolve_dependency_version(
        config.repository, dependency.name, requirement
    )


def main() -> int:
    """Validate settings, build the graph, and print it."""
    config = parse_config()
    print_configuration(config)
    try:
        graph = build_dependency_graph(
            config.package,
            config.version,
            config.max_depth,
            lambda name, version: load_package(config, name, version),
            lambda dependency: resolve_version(config, dependency),
        )
    except DependencyError as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1
    print()
    print_graph(graph)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
