"""Tests for recursive breadth-first dependency graph traversal."""

import unittest
from pathlib import Path

from src.cargo import Dependency, DependencyError, load_test_dependencies
from src.graph import build_dependency_graph


PROJECT_ROOT = Path(__file__).resolve().parents[1]
TEST_GRAPH = PROJECT_ROOT / "tests" / "data" / "test_graph.json"


class BuildDependencyGraphTests(unittest.TestCase):
    """Check BFS level order, depth limits, and cycle handling."""

    def setUp(self) -> None:
        self.edges = {
            "A": ["B", "C"],
            "B": ["D"],
            "C": ["D", "E"],
            "D": [],
            "E": ["A"],
        }
        self.loaded: list[str] = []

    def loader(self, package: str, version: str | None) -> list[Dependency]:
        """Provide test edges and record the BFS expansion order."""
        self.loaded.append(package)
        return [Dependency(name) for name in self.edges[package]]

    def test_builds_transitive_graph_and_handles_cycle(self) -> None:
        graph = build_dependency_graph("A", "1.0.0", 5, self.loader)
        self.assertEqual(
            graph,
            {
                "A": ["B", "C"],
                "B": ["D"],
                "C": ["D", "E"],
                "D": [],
                "E": ["A"],
            },
        )
        self.assertEqual(self.loaded, ["A", "B", "C", "D", "E"])

    def test_respects_maximum_depth_one(self) -> None:
        graph = build_dependency_graph("A", "1.0.0", 1, self.loader)
        self.assertEqual(graph, {"A": ["B", "C"], "B": [], "C": []})
        self.assertEqual(self.loaded, ["A"])

    def test_zero_depth_includes_only_root(self) -> None:
        graph = build_dependency_graph("A", "1.0.0", 0, self.loader)
        self.assertEqual(graph, {"A": []})
        self.assertEqual(self.loaded, [])

    def test_each_package_is_loaded_once_in_diamond_graph(self) -> None:
        build_dependency_graph("A", "1.0.0", 5, self.loader)
        self.assertEqual(len(self.loaded), len(set(self.loaded)))

    def test_resolves_versions_for_expanded_nodes(self) -> None:
        resolved: list[str] = []

        def resolver(dependency: Dependency) -> str:
            resolved.append(dependency.name)
            return f"{dependency.name}-version"

        build_dependency_graph("A", "1.0.0", 2, self.loader, resolver)
        self.assertEqual(resolved, ["B", "C"])

    def test_rejects_negative_depth(self) -> None:
        with self.assertRaisesRegex(DependencyError, "cannot be negative"):
            build_dependency_graph("A", "1.0.0", -1, self.loader)


class TestGraphFileTests(unittest.TestCase):
    """Check the uppercase-name test file required by the assignment."""

    def test_loads_direct_test_dependencies(self) -> None:
        result = load_test_dependencies(str(TEST_GRAPH), "A")
        self.assertEqual(
            result, [Dependency("B"), Dependency("C")]
        )

    def test_rejects_lowercase_package_names(self) -> None:
        import json
        import tempfile

        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "graph.json"
            path.write_text(
                json.dumps({"A": ["lowercase"]}), encoding="utf-8"
            )
            with self.assertRaisesRegex(
                DependencyError, "uppercase Latin"
            ):
                load_test_dependencies(str(path), "A")

    def test_rejects_lowercase_package_keys(self) -> None:
        import json
        import tempfile

        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "graph.json"
            path.write_text(
                json.dumps({"lowercase": ["A"]}), encoding="utf-8"
            )

            with self.assertRaisesRegex(
                DependencyError, "package names must use uppercase Latin"
            ):
                load_test_dependencies(str(path), "lowercase")


if __name__ == "__main__":
    unittest.main()
