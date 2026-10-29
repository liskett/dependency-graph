import json
import tempfile
import unittest
from pathlib import Path

from src.cargo import Dependency, DependencyError, load_test_dependencies
from src.graph import build_dependency_graph
from src.versioned_repository import VersionedRepository


PROJECT_ROOT = Path(__file__).resolve().parents[1]
LEGACY_GRAPH = PROJECT_ROOT / "tests" / "data" / "test_graph.json"
VERSIONED_GRAPH = PROJECT_ROOT / "tests" / "data" / "versioned_graph.json"


class BuildDependencyGraphTests(unittest.TestCase):
    """Verify that BFS treats package versions as different nodes."""

    def setUp(self) -> None:
        self.repository = VersionedRepository(str(VERSIONED_GRAPH))
        self.loaded: list[tuple[str, str]] = []

    def loader(self, package: str, version: str) -> list[Dependency]:
        """Record BFS visits while loading exact package versions."""
        self.loaded.append((package, version))
        return self.repository.dependencies(package, version)

    @staticmethod
    def resolver(dependency: Dependency) -> str:
        """Return the exact version given in the test JSON."""
        if dependency.requirement is None:
            raise DependencyError("Missing test dependency version.")
        return dependency.requirement

    def build(self, version: str, depth: int) -> dict[str, list[str]]:
        """Build a graph rooted at the selected version of A."""
        return build_dependency_graph(
            "A", version, depth, self.loader, self.resolver
        )

    def test_bfs_with_shared_nodes_and_cycle(self) -> None:
        graph = self.build("1.0.0", 5)
        self.assertEqual(
            graph,
            {
                "A@1.0.0": ["B@1.0.0", "C@1.0.0"],
                "B@1.0.0": ["D@1.0.0"],
                "C@1.0.0": ["B@1.0.0", "D@1.0.0", "E@1.0.0"],
                "D@1.0.0": [],
                "E@1.0.0": ["A@1.0.0"],
            },
        )
        self.assertEqual(
            self.loaded,
            [
                ("A", "1.0.0"),
                ("B", "1.0.0"),
                ("C", "1.0.0"),
                ("D", "1.0.0"),
                ("E", "1.0.0"),
            ],
        )

    def test_different_versions_are_distinct_nodes(self) -> None:
        graph = self.build("2.0.0", 5)
        self.assertIn("A@1.0.0", graph)
        self.assertIn("A@2.0.0", graph)
        self.assertIn("B@1.0.0", graph)
        self.assertIn("B@2.0.0", graph)
        self.assertEqual(graph["B@1.0.0"], ["D@1.0.0"])
        self.assertEqual(graph["B@2.0.0"], ["D@2.0.0"])
        self.assertEqual(graph["E@1.0.0"], ["A@1.0.0"])

    def test_depth_one_records_only_direct_edges(self) -> None:
        graph = self.build("1.0.0", 1)
        self.assertEqual(
            graph,
            {
                "A@1.0.0": ["B@1.0.0", "C@1.0.0"],
                "B@1.0.0": [],
                "C@1.0.0": [],
            },
        )
        self.assertEqual(self.loaded, [("A", "1.0.0")])

    def test_zero_depth_includes_only_the_root(self) -> None:
        self.assertEqual(self.build("1.0.0", 0), {"A@1.0.0": []})
        self.assertEqual(self.loaded, [("A", "1.0.0")])

    def test_zero_depth_rejects_nonexistent_version(self) -> None:
        with self.assertRaisesRegex(DependencyError, "missing"):
            self.build("9.9.9", 0)

    def test_deep_graph_reports_clear_error(self) -> None:
        def linear_loader(package: str, version: str) -> list[Dependency]:
            return [Dependency(str(int(package) + 1), version)]

        with self.assertRaisesRegex(DependencyError, "too deep"):
            build_dependency_graph(
                "0", "1.0.0", 1200,
                linear_loader, self.resolver,
            )

    def test_each_exact_version_is_expanded_once(self) -> None:
        self.build("2.0.0", 5)
        self.assertEqual(len(self.loaded), len(set(self.loaded)))

    def test_negative_depth_is_rejected(self) -> None:
        with self.assertRaisesRegex(DependencyError, "cannot be negative"):
            self.build("1.0.0", -1)


class VersionedRepositoryTests(unittest.TestCase):
    """Check input validation and exact-version dependency selection."""

    def load_from_dict(self, data: object) -> VersionedRepository:
        """Write a temporary JSON fixture and load its repository."""
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "graph.json"
            path.write_text(json.dumps(data), encoding="utf-8")
            return VersionedRepository(str(path))

    def test_loads_exact_version_dependencies(self) -> None:
        repository = VersionedRepository(str(VERSIONED_GRAPH))
        self.assertEqual(
            repository.dependencies("A", "2.0.0"),
            [Dependency("B", "2.0.0"), Dependency("C", "1.0.0")],
        )

    def test_rejects_nonexistent_package_version(self) -> None:
        repository = VersionedRepository(str(VERSIONED_GRAPH))
        with self.assertRaisesRegex(DependencyError, "missing"):
            repository.dependencies("A", "9.0.0")

    def test_rejects_lowercase_names(self) -> None:
        data = {"A": {"1.0.0": [{"name": "bad", "version": "1.0.0"}]}}
        with self.assertRaisesRegex(DependencyError, "uppercase Latin"):
            self.load_from_dict(data)

    def test_rejects_invalid_version(self) -> None:
        with self.assertRaisesRegex(DependencyError, "exact package versions"):
            self.load_from_dict({"A": {"1.0": []}})

    def test_rejects_dependency_without_version(self) -> None:
        with self.assertRaisesRegex(DependencyError, "name.*version"):
            self.load_from_dict({"A": {"1.0.0": [{"name": "B"}]}})

    def test_rejects_missing_dependency_target(self) -> None:
        data = {
            "A": {
                "1.0.0": [{"name": "B", "version": "2.0.0"}]
            },
            "B": {"1.0.0": []},
        }
        with self.assertRaisesRegex(DependencyError, "missing version"):
            self.load_from_dict(data)

    def test_rejects_invalid_json_shape(self) -> None:
        with self.assertRaisesRegex(DependencyError, "JSON object"):
            self.load_from_dict([])

    def test_legacy_test_data_for_stage_two_is_unchanged(self) -> None:
        self.assertEqual(
            load_test_dependencies(str(LEGACY_GRAPH), "A"),
            [Dependency("B"), Dependency("C")],
        )


if __name__ == "__main__":
    unittest.main()
