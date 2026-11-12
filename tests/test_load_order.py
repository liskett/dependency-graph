"""Tests for the stage-four dependency loading-order display."""

import subprocess
import sys
import unittest
from pathlib import Path

from src.cargo import DependencyError
from src.load_order import dependency_load_order


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "data" / "versioned_graph.json"


class DependencyLoadOrderTests(unittest.TestCase):
    """Check BFS order, versions, cycles, and malformed graphs."""

    def test_repeated_dependencies_are_shown_once(self) -> None:
        graph = {
            "A@1.0.0": ["C@1.0.0", "B@1.0.0"],
            "B@1.0.0": ["D@1.0.0"],
            "C@1.0.0": ["B@1.0.0", "D@1.0.0"],
            "D@1.0.0": [],
        }
        self.assertEqual(
            dependency_load_order(graph, "A@1.0.0"),
            ["B@1.0.0", "C@1.0.0", "D@1.0.0"],
        )

    def test_cycle_does_not_repeat_root(self) -> None:
        graph = {
            "A@1.0.0": ["B@1.0.0"],
            "B@1.0.0": ["A@1.0.0"],
        }
        self.assertEqual(
            dependency_load_order(graph, "A@1.0.0"),
            ["B@1.0.0"],
        )

    def test_multiple_versions_are_distinct(self) -> None:
        graph = {
            "A@1.0.0": ["B@2.0.0", "B@1.0.0"],
            "B@1.0.0": [],
            "B@2.0.0": [],
        }
        self.assertEqual(
            dependency_load_order(graph, "A@1.0.0"),
            ["B@1.0.0", "B@2.0.0"],
        )

    def test_disconnected_nodes_are_excluded(self) -> None:
        graph = {"A@1.0.0": [], "B@1.0.0": []}
        self.assertEqual(dependency_load_order(graph, "A@1.0.0"), [])

    def test_unknown_root_is_rejected(self) -> None:
        with self.assertRaisesRegex(DependencyError, "Root package"):
            dependency_load_order({}, "A@1.0.0")

    def test_dangling_edge_is_rejected(self) -> None:
        with self.assertRaisesRegex(DependencyError, "missing dependency"):
            dependency_load_order(
                {"A@1.0.0": ["B@1.0.0"]}, "A@1.0.0"
            )


class LoadOrderCliTests(unittest.TestCase):
    """Exercise the full CLI on test repository cases."""

    def run_cli(self, version: str, depth: int) -> subprocess.CompletedProcess:
        """Invoke the CLI and capture its console output."""
        return subprocess.run(
            [
                sys.executable, "-m", "src.main",
                "--package", "A", "--version", version,
                "--repository", str(FIXTURE), "--test-mode",
                "--max-depth", str(depth), "--show-load-order",
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )

    def test_cyclic_graph_load_order(self) -> None:
        result = self.run_cli("1.0.0", 5)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            result.stdout.splitlines()[1:],
            ["1. B@1.0.0", "2. C@1.0.0", "3. D@1.0.0", "4. E@1.0.0"],
        )

    def test_versioned_graph_load_order(self) -> None:
        result = self.run_cli("2.0.0", 5)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            result.stdout.splitlines()[1:],
            [
                "1. B@2.0.0", "2. C@1.0.0", "3. D@2.0.0",
                "4. B@1.0.0", "5. D@1.0.0", "6. E@1.0.0",
                "7. A@1.0.0",
            ],
        )

    def test_depth_one(self) -> None:
        result = self.run_cli("1.0.0", 1)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            result.stdout.splitlines()[1:],
            ["1. B@1.0.0", "2. C@1.0.0"],
        )

    def test_depth_zero(self) -> None:
        result = self.run_cli("1.0.0", 0)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.splitlines()[-1], "(none)")

    def test_normal_graph_output_is_preserved(self) -> None:
        """Keep stage-three graph output unchanged without the new flag."""
        command = [
            sys.executable, "-m", "src.main",
            "--package", "A", "--version", "1.0.0",
            "--repository", str(FIXTURE), "--test-mode",
            "--max-depth", "1",
        ]
        result = subprocess.run(
            command, cwd=ROOT, capture_output=True,
            text=True, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Dependency graph:", result.stdout)
        self.assertIn("A@1.0.0 -> B@1.0.0, C@1.0.0", result.stdout)

    def test_invalid_root_version_fails(self) -> None:
        result = self.run_cli("9.0.0", 0)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("missing", result.stderr)


if __name__ == "__main__":
    unittest.main()
