import json
import re
from pathlib import Path

from src.cargo import Dependency, DependencyError
from src.config import VERSION_PATTERN


PACKAGE_PATTERN = re.compile(r"[A-Z]+")


class VersionedRepository:
    """Validate and serve exact versions from a local JSON graph."""

    def __init__(self, path: str) -> None:
        self.graph = self._read_graph(path)
        self._validate_references()

    @staticmethod
    def _check_package(value: object) -> str:
        """Require package names composed of uppercase Latin letters."""
        if not isinstance(value, str) or not PACKAGE_PATTERN.fullmatch(value):
            raise DependencyError(
                "Test graph names must use uppercase Latin letters."
            )
        return value

    @staticmethod
    def _check_version(value: object) -> str:
        """Require an exact version accepted by the command-line parser."""
        if (
            not isinstance(value, str)
            or not VERSION_PATTERN.fullmatch(value)
        ):
            raise DependencyError("Test graph requires exact package versions.")
        return value

    @classmethod
    def _parse_dependency(cls, record: object) -> Dependency:
        """Decode a dependency containing its package name and version."""
        if not isinstance(record, dict) or set(record) != {"name", "version"}:
            raise DependencyError(
                "Each test dependency needs 'name' and 'version'."
            )
        name = cls._check_package(record["name"])
        version = cls._check_version(record["version"])
        return Dependency(name, version)

    @classmethod
    def _parse_graph(
        cls, data: object
    ) -> dict[str, dict[str, list[Dependency]]]:
        """Validate the JSON structure and decode every package version."""
        if not isinstance(data, dict):
            raise DependencyError("Test graph must be a JSON object.")
        graph: dict[str, dict[str, list[Dependency]]] = {}
        for package, versions in data.items():
            name = cls._check_package(package)
            if not isinstance(versions, dict) or not versions:
                raise DependencyError(f"'{name}' must have a versions object.")
            graph[name] = {}
            for version, records in versions.items():
                exact = cls._check_version(version)
                if not isinstance(records, list):
                    raise DependencyError(
                        f"Dependencies for '{name}@{exact}' must be a list."
                    )
                graph[name][exact] = [
                    cls._parse_dependency(record) for record in records
                ]
        return graph

    @classmethod
    def _read_graph(
        cls, path: str
    ) -> dict[str, dict[str, list[Dependency]]]:
        """Read a JSON file and report malformed or inaccessible input."""
        try:
            text = Path(path).read_text(encoding="utf-8")
            return cls._parse_graph(json.loads(text))
        except (OSError, UnicodeError, json.JSONDecodeError) as error:
            message = f"Could not read test graph: {error}."
            raise DependencyError(message) from error

    def _validate_references(self) -> None:
        """Reject dependencies pointing to unknown package versions."""
        for versions in self.graph.values():
            for dependencies in versions.values():
                for dependency in dependencies:
                    available = self.graph.get(dependency.name, {})
                    if dependency.requirement not in available:
                        raise DependencyError(
                            "Test dependency references missing version "
                            f"'{dependency.name}@{dependency.requirement}'."
                        )

    def dependencies(self, package: str, version: str) -> list[Dependency]:
        """Return direct dependencies of one exact package version."""
        available = self.graph.get(package, {})
        if version not in available:
            raise DependencyError(
                f"Package version '{package}@{version}' is missing."
            )
        return list(available[version])
