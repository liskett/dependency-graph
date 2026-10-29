"""Tests for command-line configuration and validation."""

import contextlib
import io
import unittest
from pathlib import Path

from src.config import parse_config


PROJECT_ROOT = Path(__file__).resolve().parents[1]
TEST_GRAPH = PROJECT_ROOT / "tests" / "data" / "test_graph.json"


class ConfigTests(unittest.TestCase):
    """Check valid configuration and the expected input errors."""

    def parse_quietly(self, args: list[str]):
        """Parse arguments while suppressing argparse error output."""
        with contextlib.redirect_stderr(io.StringIO()):
            return parse_config(args)

    def base_args(self) -> list[str]:
        """Return the minimum valid arguments for a real repository."""
        return [
            "--package", "serde",
            "--repository", "https://crates.io",
            "--version", "1.0.0",
        ]

    def test_valid_real_repository(self) -> None:
        config = self.parse_quietly(self.base_args())
        self.assertEqual(config.package, "serde")
        self.assertFalse(config.test_mode)
        self.assertEqual(config.max_depth, 5)
        self.assertEqual(config.output, "dependency_graph.svg")

    def test_valid_test_repository(self) -> None:
        args = [
            "--package", "A",
            "--repository", str(TEST_GRAPH),
            "--test-mode",
            "--version", "1.0.0",
            "--max-depth", "0",
        ]
        config = self.parse_quietly(args)
        self.assertTrue(config.test_mode)
        self.assertEqual(config.max_depth, 0)

    def test_rejects_invalid_package_name(self) -> None:
        args = self.base_args()
        args[1] = "bad package"
        with self.assertRaises(SystemExit):
            self.parse_quietly(args)

    def test_rejects_invalid_version(self) -> None:
        args = self.base_args()
        args[5] = "1.0"
        with self.assertRaises(SystemExit):
            self.parse_quietly(args)

    def test_rejects_invalid_repository_url(self) -> None:
        args = self.base_args()
        args[3] = "not-a-url"
        with self.assertRaises(SystemExit):
            self.parse_quietly(args)

    def test_rejects_missing_test_file(self) -> None:
        args = [
            "--package", "A",
            "--repository", "missing.json",
            "--test-mode",
            "--version", "1.0.0",
        ]
        with self.assertRaises(SystemExit):
            self.parse_quietly(args)

    def test_rejects_negative_depth(self) -> None:
        args = self.base_args() + ["--max-depth", "-1"]
        with self.assertRaises(SystemExit):
            self.parse_quietly(args)

    def test_rejects_non_integer_depth(self) -> None:
        args = self.base_args() + ["--max-depth", "deep"]
        with self.assertRaises(SystemExit):
            self.parse_quietly(args)

    def test_rejects_non_svg_output(self) -> None:
        args = self.base_args() + ["--output", "graph.png"]
        with self.assertRaises(SystemExit):
            self.parse_quietly(args)


if __name__ == "__main__":
    unittest.main()
