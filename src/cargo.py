"""Read direct Cargo dependencies from a registry or a local test graph."""

import json
from dataclasses import dataclass
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from src.config import AppConfig


REQUEST_TIMEOUT = 15
USER_AGENT = "dependency-graph-visualizer/0.1 (educational project)"
HTTP_STATUS_ERROR = 404

class DependencyError(Exception):
    """Represent a dependency lookup or response-format error."""


@dataclass(frozen=True)
class Dependency:
    """Store the dependency fields needed for console output."""

    name: str
    requirement: str | None = None
    kind: str | None = None
    optional: bool = False

def _parse_dependency_record(record: object) -> Dependency:
    """Validate and decode one dependency record."""
    if not isinstance(record, dict):
        raise DependencyError("Registry returned an invalid dependency.")

    name = record.get("crate_id")
    requirement = record.get("req")
    kind = record.get("kind")
    optional = record.get("optional", False)

    if not isinstance(name, str) or not isinstance(requirement, str):
        raise DependencyError("Registry returned an invalid dependency.")

    if kind is not None and not isinstance(kind, str):
        raise DependencyError("Registry returned an invalid dependency.")

    if not isinstance(optional, bool):
        raise DependencyError("Registry returned an invalid dependency.")

    return Dependency(name, requirement, kind or "normal", optional)


def _dependency_sort_key(
    item: Dependency,
) -> tuple[str, str, str]:
    """Return the fields used to sort dependency records."""
    return (
        item.name,
        item.kind or "",
        item.requirement or "",
    )

def build_dependencies_url(
    repository: str, package: str, version: str
) -> str:
    """Build the crates.io-compatible endpoint for one exact version."""
    base = repository.rstrip("/")
    if not base.endswith("/api/v1"):
        base += "/api/v1"
    package_path = quote(package, safe="")
    version_path = quote(version, safe="")
    return f"{base}/crates/{package_path}/{version_path}/dependencies"


def parse_dependencies(payload: object) -> list[Dependency]:
    """Validate and decode the dependencies array in a registry response."""
    if not isinstance(payload, dict):
        raise DependencyError(
            "Registry returned an unexpected JSON object."
        )

    records = payload.get("dependencies")

    if not isinstance(records, list):
        raise DependencyError(
            "Registry response does not contain a dependencies list."
        )

    dependencies: list[Dependency] = []

    for record in records:
        dependencies.append(_parse_dependency_record(record))

    return sorted(dependencies, key=_dependency_sort_key)

def fetch_dependencies(
    repository: str, package: str, version: str
) -> list[Dependency]:
    """Fetch direct dependency records without invoking Cargo or other tools."""
    url = build_dependencies_url(repository, package, version)
    request = Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urlopen(request, timeout=REQUEST_TIMEOUT) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as error:
        if error.code == HTTP_STATUS_ERROR:
            message = f"Package '{package}' version '{version}' was not found."
        else:
            message = f"Registry request failed with HTTP {error.code}."
        raise DependencyError(message) from error
    except (URLError, TimeoutError) as error:
        message = f"Could not reach the registry: {error}."
        raise DependencyError(message) from error
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise DependencyError("Registry returned invalid JSON data.") from error
    return parse_dependencies(payload)


def load_test_dependencies(path: str, package: str) -> list[Dependency]:
    """Read direct edges from the simple JSON graph used in test mode."""
    try:
        graph = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise DependencyError(f"Could not read test graph: {error}.") from error
    if not isinstance(graph, dict):
        message = "Test graph must be a JSON object of package names."
        raise DependencyError(message)
    if package not in graph:
        message = f"Package '{package}' is missing from the test graph."
        raise DependencyError(message)
    names = graph[package]
    if not isinstance(names, list) or any(
        not isinstance(name, str) for name in names
    ):
        raise DependencyError(
            f"Dependencies for package '{package}' must be a list of names."
        )
    return [Dependency(name) for name in sorted(set(names))]


def get_direct_dependencies(config: AppConfig) -> list[Dependency]:
    """Choose the registry or local test source from application settings."""
    if config.test_mode:
        return load_test_dependencies(config.repository, config.package)
    return fetch_dependencies(config.repository, config.package, config.version)
