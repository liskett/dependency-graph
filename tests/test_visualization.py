"""Tests for Mermaid text and standalone SVG visualization."""

import contextlib
import io
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from xml.etree import ElementTree as element_tree

from src.cargo import DependencyError
from src.config import parse_config
from src.visualization import save_visualization, to_mermaid, to_svg


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "tests" / "data" / "versioned_graph.json"
SVG_NS = "{http://www.w3.org/2000/svg}"


class VisualizationTests(unittest.TestCase):
    """Verify graph structure, escaping, cycles, and SVG output."""

    def setUp(self) -> None:
        self.graph = {
            "A@1.0.0": ["B@1.0.0", "C@1.0.0"],
            "B@1.0.0": ["C@1.0.0"],
            "C@1.0.0": ["A@1.0.0"],
            "D@1.0.0": [],
        }

    def test_mermaid_contains_every_node_and_cycle(self) -> None:
        text = to_mermaid(self.graph, "A@1.0.0")
        self.assertTrue(text.startswith("flowchart LR\n"))
        for name in self.graph:
            self.assertIn(f'["{name}"]', text)
        self.assertEqual(text.count(" --> "), 4)
        self.assertIn("n2 --> n0", text)

    def test_mermaid_is_deterministic(self) -> None:
        graph = dict(reversed(list(self.graph.items())))
        self.assertEqual(
            to_mermaid(self.graph, "A@1.0.0"),
            to_mermaid(graph, "A@1.0.0"),
        )

    def test_mermaid_escapes_special_characters(self) -> None:
        graph = {"A<&@1.0.0": []}
        text = to_mermaid(graph, "A<&@1.0.0")
        self.assertIn("A&lt;&amp;@1.0.0", text)

    def test_svg_contains_all_nodes_and_edges(self) -> None:
        root = element_tree.fromstring(to_svg(self.graph, "A@1.0.0"))
        nodes = root.find(f"{SVG_NS}g[@id='nodes']")
        edges = root.find(f"{SVG_NS}g[@id='edges']")
        self.assertIsNotNone(nodes)
        self.assertIsNotNone(edges)
        self.assertEqual(len(nodes.findall(f"{SVG_NS}rect")), 4)
        self.assertEqual(len(edges.findall(f"{SVG_NS}path")), 4)
        labels = [text.text for text in nodes.findall(f"{SVG_NS}text")]
        self.assertEqual(set(labels), set(self.graph))

    def test_svg_root_uses_distinct_fill(self) -> None:
        root = element_tree.fromstring(to_svg(self.graph, "A@1.0.0"))
        rectangles = root.findall(f".//{SVG_NS}g[@id='nodes']/{SVG_NS}rect")
        self.assertNotEqual(
            rectangles[0].get("fill"), rectangles[1].get("fill")
        )

    def test_svg_escapes_special_characters(self) -> None:
        graph = {"A<&@1.0.0": []}
        svg = to_svg(graph, "A<&@1.0.0")
        self.assertIn("A&lt;&amp;@1.0.0", svg)
        element_tree.fromstring(svg)

    def test_svg_draws_self_cycle(self) -> None:
        graph = {"A@1.0.0": ["A@1.0.0"]}
        root = element_tree.fromstring(to_svg(graph, "A@1.0.0"))
        self.assertEqual(len(root.findall(f".//{SVG_NS}g[@id='edges']/*")), 1)

    def test_missing_root_is_rejected(self) -> None:
        with self.assertRaisesRegex(DependencyError, "Root package"):
            to_mermaid(self.graph, "Z@1.0.0")

    def test_dangling_edge_is_rejected(self) -> None:
        with self.assertRaisesRegex(DependencyError, "missing dependency"):
            to_svg({"A@1.0.0": ["Z@1.0.0"]}, "A@1.0.0")

    def test_saves_both_formats(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / "graph.svg"
            text = save_visualization(self.graph, "A@1.0.0", str(output))
            self.assertTrue(output.exists())
            self.assertEqual(
                output.with_suffix(".mmd").read_text().strip(), text
            )
            element_tree.parse(output)

    def test_rejects_unwritable_destination(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / "missing" / "graph.svg"
            with self.assertRaisesRegex(DependencyError, "Could not save"):
                save_visualization(self.graph, "A@1.0.0", str(output))

    def test_rejects_non_svg_destination(self) -> None:
        with self.assertRaisesRegex(DependencyError, "SVG"):
            save_visualization(self.graph, "A@1.0.0", "graph.png")

    def test_disconnected_dangling_edge_is_rejected(self) -> None:
        graph = {
            "A@1.0.0": [],
            "B@1.0.0": ["Z@1.0.0"],
        }
        with self.assertRaisesRegex(DependencyError, "missing dependency"):
            to_mermaid(graph, "A@1.0.0")

    def test_back_edge_uses_lane_below_nodes(self) -> None:
        graph = {
            "A@1.0.0": ["B@1.0.0"],
            "B@1.0.0": ["A@1.0.0"],
        }
        root = element_tree.fromstring(to_svg(graph, "A@1.0.0"))
        paths = root.findall(f".//{SVG_NS}g[@id='edges']/{SVG_NS}path")
        self.assertEqual(len(paths), 2)
        self.assertIn(" L ", paths[1].get("d"))
        boxes = root.findall(f".//{SVG_NS}g[@id='nodes']/{SVG_NS}rect")
        lowest = max(
            int(box.get("y")) + int(box.get("height"))
            for box in boxes
        )
        coordinates = paths[1].get("d").split()
        self.assertGreater(int(coordinates[5]), lowest)

    def test_same_level_edge_is_vertical(self) -> None:
        graph = {
            "A@1.0.0": ["B@1.0.0", "C@1.0.0"],
            "B@1.0.0": [],
            "C@1.0.0": ["B@1.0.0"],
        }
        root = element_tree.fromstring(to_svg(graph, "A@1.0.0"))
        paths = root.findall(f".//{SVG_NS}g[@id='edges']/{SVG_NS}path")
        self.assertIn(" L ", paths[-1].get("d"))


class VisualizationCliTests(unittest.TestCase):
    """Exercise CLI visualization for three distinct test packages."""

    def run_cli(
        self, package: str, version: str, depth: int, output: Path
    ) -> subprocess.CompletedProcess:
        """Run a versioned test graph without writing inside the repository."""
        return subprocess.run(
            [
                sys.executable, "-m", "src.main",
                "--package", package, "--version", version,
                "--repository", str(DATA), "--test-mode",
                "--max-depth", str(depth), "--visualize",
                "--output", str(output),
            ],
            cwd=ROOT, capture_output=True, text=True, check=False,
        )

    def test_three_package_examples(self) -> None:
        for package, version in (
            ("A", "1.0.0"), ("B", "2.0.0"), ("D", "1.0.0")
        ):
            with self.subTest(package=package):
                with tempfile.TemporaryDirectory() as directory:
                    svg = Path(directory) / f"{package}.svg"
                    result = self.run_cli(package, version, 5, svg)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertIn("flowchart LR", result.stdout)
                    self.assertIn(f"{package}@{version}", result.stdout)
                    self.assertTrue(svg.exists())
                    self.assertTrue(svg.with_suffix(".mmd").exists())
                    element_tree.parse(svg)

    def test_depth_zero_creates_single_svg_node(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            svg = Path(directory) / "root.svg"
            result = self.run_cli("A", "1.0.0", 0, svg)
            self.assertEqual(result.returncode, 0, result.stderr)
            root = element_tree.parse(svg).getroot()
            nodes = root.find(f"{SVG_NS}g[@id='nodes']")
            self.assertEqual(len(nodes.findall(f"{SVG_NS}rect")), 1)

    def test_rejects_conflicting_output_modes(self) -> None:
        args = [
            "--package", "A", "--version", "1.0.0",
            "--repository", str(DATA), "--test-mode",
            "--visualize", "--show-load-order",
        ]
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):
                parse_config(args)

    def test_visualization_reports_output_failure(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "missing" / "graph.svg"
            result = self.run_cli("A", "1.0.0", 1, output)
            self.assertEqual(result.returncode, 1)
            self.assertIn("Could not save visualization", result.stderr)


if __name__ == "__main__":
    unittest.main()