"""Command-line entry point for the dependency graph visualizer."""

import sys

from src.cargo import Dependency, DependencyError, get_direct_dependencies
from src.config import parse_config


def print_dependencies(
    package: str, version: str, dependencies: list[Dependency], test_mode: bool
) -> None:
    """Print the direct dependency list in a predictable human-readable form."""
    print(f"Direct dependencies of {package} (version {version}):")
    if not dependencies:
        print("No direct dependencies found.")
        return
    for dependency in dependencies:
        if test_mode:
            print(f"- {dependency.name}")
            continue
        kind = dependency.kind or "normal"
        optional = "yes" if dependency.optional else "no"
        print(
            f"- {dependency.name} (requirement: {dependency.requirement}; "
            f"kind: {kind}; optional: {optional})"
        )


def main() -> int:
    """Validate settings and print the selected package dependencies."""
    config = parse_config()
    print("Application configuration:")
    for key, value in config.as_dict().items():
        print(f"{key} = {value}")
    try:
        dependencies = get_direct_dependencies(config)
    except DependencyError as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1
    print()
    print_dependencies(
        config.package, config.version, dependencies, config.test_mode
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
