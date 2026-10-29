"""Read direct Cargo dependencies from a registry or a local test graph."""

import json
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from src.config import AppConfig


REQUEST_TIMEOUT = 15
USER_AGENT = "dependency-graph-visualizer/0.1 (educational project)"
HTTP_STATUS_ERROR = 404
EMPTY = 0
SINGLE_PART = 1
TWO_PARTS = 2


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

def fetch_json(url: str, not_found_message: str) -> object:
    """Fetch and decode a JSON endpoint, translating network errors."""
    request = Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urlopen(request, timeout=REQUEST_TIMEOUT) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as error:
        message = not_found_message if error.code == HTTP_STATUS_ERROR else (
            f"Registry request failed with HTTP {error.code}."
        )
        raise DependencyError(message) from error
    except (URLError, TimeoutError) as error:
        message = f"Could not reach the registry: {error}."
        raise DependencyError(message) from error
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise DependencyError("Registry returned invalid JSON data.") from error


def fetch_dependencies(
    repository: str, package: str, version: str
) -> list[Dependency]:
    """Fetch direct dependency records without invoking Cargo or other tools."""
    url = build_dependencies_url(repository, package, version)
    missing_message = f"Package '{package}' version '{version}' was not found."
    return parse_dependencies(fetch_json(url, missing_message))


def _read_test_graph(path: str) -> object:
    """Read and decode the local test graph JSON file."""
    try:
        contents = Path(path).read_text(encoding="utf-8")
        return json.loads(contents)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise DependencyError(f"Could not read test graph: {error}.") from error


def _validate_test_graph_package_name(package: object) -> None:
    """Reject graph package names outside the required uppercase format."""
    if not isinstance(package, str) or not re.fullmatch(r"[A-Z]+", package):
        raise DependencyError(
            "Test graph package names must use uppercase Latin letters."
        )


def _validate_test_graph_dependencies(
    package: str,
    names: object,
) -> None:
    """Reject dependency lists with invalid names or container types."""
    if not isinstance(names, list):
        _raise_invalid_test_dependencies(package)

    for name in names:
        if not isinstance(name, str) or not re.fullmatch(r"[A-Z]+", name):
            _raise_invalid_test_dependencies(package)


def _raise_invalid_test_dependencies(package: str) -> None:
    """Raise the standard error for malformed dependency lists."""
    raise DependencyError(
        f"Dependencies for package '{package}' must be "
        "a list of uppercase Latin package names."
    )


def _validate_test_graph(graph: object) -> dict[str, list[str]]:
    """Validate all package names and dependency lists in a test graph."""
    if not isinstance(graph, dict):
        raise DependencyError(
            "Test graph must be a JSON object of package names."
        )

    for package, names in graph.items():
        _validate_test_graph_package_name(package)
        _validate_test_graph_dependencies(package, names)

    return graph


def load_test_dependencies(path: str, package: str) -> list[Dependency]:
    """Read uppercase package-name edges from a local test graph."""
    graph = _validate_test_graph(_read_test_graph(path))

    if package not in graph:
        raise DependencyError(
            f"Package '{package}' is missing from the test graph."
        )

    return [Dependency(name) for name in sorted(set(graph[package]))]


def get_direct_dependencies(config: AppConfig) -> list[Dependency]:
    """Choose the registry or local test source from application settings."""
    if config.test_mode:
        return load_test_dependencies(config.repository, config.package)
    return fetch_dependencies(config.repository, config.package, config.version)


def build_versions_url(repository: str, package: str) -> str:
    """Build the registry endpoint listing versions of one Cargo package."""
    base = repository.rstrip("/")
    if not base.endswith("/api/v1"):
        base += "/api/v1"
    package_path = quote(package, safe="")
    return f"{base}/crates/{package_path}/versions"


def _numeric_version(value: str) -> tuple[int, int, int] | None:
    """Parse a stable MAJOR.MINOR.PATCH version into numeric components."""
    match = re.fullmatch(
        r"(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
        r"(?:\+[0-9A-Za-z.-]+)?",
        value,
    )
    if match is None:
        return None
    return tuple(int(part) for part in match.groups())


def _compare_explicit_operator(
    candidate: tuple[int, int, int],
    operator: str,
    boundary: tuple[int, ...],
) -> bool | None:
    """Compare versions using an explicit comparison operator."""
    if operator == ">=":
        return candidate >= boundary
    if operator == "<=":
        return candidate <= boundary
    if operator == ">":
        return candidate > boundary
    if operator == "<":
        return candidate < boundary
    if operator == "=":
        return candidate == boundary
    return None


def _tilde_upper_bound(
    major: int,
    minor: int,
    part_count: int,
) -> tuple[int, int, int]:
    """Calculate the exclusive upper bound for a tilde requirement."""
    if part_count == SINGLE_PART:
        return (major + 1, 0, 0)
    return (major, minor + 1, 0)


def _caret_upper_bound(
    major: int,
    minor: int,
    patch: int,
    part_count: int,
) -> tuple[int, int, int]:
    """Calculate the exclusive upper bound for a caret requirement."""
    if major > EMPTY or part_count == SINGLE_PART:
        return (major + 1, 0, 0)
    if minor > EMPTY or part_count == TWO_PARTS:
        return (0, minor + 1, 0)
    return (0, 0, patch + 1)


def _matches_version_range(
    candidate: tuple[int, int, int],
    operator: str,
    parts: tuple[int, ...],
) -> bool:
    """Compare a numeric version with one operator and version boundary."""
    padded = parts + (0,) * (3 - len(parts))

    comparison = _compare_explicit_operator(
        candidate, operator, padded
    )
    if comparison is not None:
        return comparison

    major, minor, patch = padded

    if operator == "~":
        upper = _tilde_upper_bound(major, minor, len(parts))
        return padded <= candidate < upper

    upper = _caret_upper_bound(
        major, minor, patch, len(parts)
    )
    return padded <= candidate < upper


def _requirement_matches_token(
    candidate: tuple[int, int, int], token: str
) -> bool:
    """Match one Cargo-style version requirement token."""
    cleaned = token.strip()
    if cleaned in {"*", "x", "X"}:
        return True
    if re.fullmatch(r"\d+(?:\.\d+)?\.[*xX]", cleaned):
        prefix = cleaned.rsplit(".", 1)[0]
        parts = tuple(int(part) for part in prefix.split("."))
        return candidate[:len(parts)] == parts
    if re.fullmatch(r"\d+\.[*xX]", cleaned):
        return candidate[0] == int(cleaned.split(".", 1)[0])
    if re.fullmatch(r"\d+", cleaned):
        return candidate[0] == int(cleaned)

    match = re.fullmatch(
        r"(\^|~|>=|<=|>|<|=)?\s*(\d+(?:\.\d+){0,2})"
        r"(?:\+[0-9A-Za-z.-]+)?",
        cleaned,
    )
    if match is None:
        return False
    operator = match.group(1) or "^"
    parts = tuple(int(part) for part in match.group(2).split("."))
    return _matches_version_range(candidate, operator, parts)


def version_satisfies(version: str, requirement: str) -> bool:
    """Return whether a stable version satisfies a common Cargo requirement."""
    candidate = _numeric_version(version)
    if candidate is None:
        return False
    alternatives = requirement.split("||")
    for alternative in alternatives:
        tokens = [part.strip() for part in alternative.split(",")]
        if tokens and all(
            _requirement_matches_token(candidate, token) for token in tokens
        ):
            return True
    return False


def _matching_versions(
    payload: object, requirement: str
) -> list[tuple[tuple[int, int, int], str]]:
    """Validate version records and return stable matching candidates."""
    if not isinstance(payload, dict) or not isinstance(
        payload.get("versions"), list
    ):
        raise DependencyError("Registry response has no versions list.")

    candidates = []
    for record in payload["versions"]:
        if not isinstance(record, dict):
            raise DependencyError(
                "Registry returned an invalid version record."
            )
        version = record.get("num")
        yanked = record.get("yanked", False)
        if not isinstance(version, str) or not isinstance(yanked, bool):
            raise DependencyError(
                "Registry returned an invalid version record."
            )
        parsed = _numeric_version(version)
        if (
            not yanked
            and parsed is not None
            and version_satisfies(version, requirement)
        ):
            candidates.append((parsed, version))
    return candidates


def resolve_dependency_version(
    repository: str, package: str, requirement: str
) -> str:
    """Select the newest non-yanked stable version matching a requirement."""
    url = build_versions_url(repository, package)
    missing_message = f"Package '{package}' was not found in the registry."
    payload = fetch_json(url, missing_message)
    candidates = _matching_versions(payload, requirement)
    if not candidates:
        message = (
            f"No stable, non-yanked version of '{package}' matches "
            f"'{requirement}'."
        )
        raise DependencyError(message)
    return max(candidates, key=lambda item: item[0])[1]