"""Tests for direct dependency collection without live network access."""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from urllib.error import HTTPError

from src.cargo import (
    Dependency,
    DependencyError,
    build_dependencies_url,
    build_versions_url,
    fetch_dependencies,
    load_test_dependencies,
    parse_dependencies,
    resolve_dependency_version,
    version_satisfies,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
TEST_GRAPH = PROJECT_ROOT / "tests" / "data" / "test_graph.json"


class DependencyUrlTests(unittest.TestCase):
    """Check endpoints for normal and preconfigured API repository URLs."""

    def test_builds_crates_io_endpoint(self) -> None:
        self.assertEqual(
            build_dependencies_url("https://crates.io", "serde", "1.0.0"),
            "https://crates.io/api/v1/crates/serde/1.0.0/dependencies",
        )

    def test_does_not_duplicate_api_prefix(self) -> None:
        result = build_dependencies_url(
            "https://example.org/api/v1/", "my-crate", "1.2.3"
        )
        self.assertEqual(
            result,
            "https://example.org/api/v1/crates/my-crate/1.2.3/dependencies",
        )

    def test_encodes_path_segments(self) -> None:
        result = build_dependencies_url(
            "https://crates.io", "crate name", "1.0.0+build"
        )
        self.assertIn("crate%20name/1.0.0%2Bbuild/dependencies", result)


class ParseDependenciesTests(unittest.TestCase):
    """Validate parsing of registry dependency records."""

    def test_parses_and_sorts_dependencies(self) -> None:
        payload = {
            "dependencies": [
                {"crate_id": "zeta", "req": "^2", "kind": "dev",
                 "optional": True},
                {"crate_id": "alpha", "req": "^1", "kind": None,
                 "optional": False},
            ]
        }
        result = parse_dependencies(payload)
        self.assertEqual(
            result,
            [
                Dependency("alpha", "^1", "normal", False),
                Dependency("zeta", "^2", "dev", True),
            ],
        )

    def test_accepts_no_dependencies(self) -> None:
        self.assertEqual(parse_dependencies({"dependencies": []}), [])

    def test_rejects_non_object_response(self) -> None:
        with self.assertRaises(DependencyError):
            parse_dependencies([])

    def test_rejects_missing_dependencies_list(self) -> None:
        with self.assertRaises(DependencyError):
            parse_dependencies({"crate": {}})

    def test_rejects_malformed_dependency(self) -> None:
        with self.assertRaises(DependencyError):
            parse_dependencies({"dependencies": [{"crate_id": "serde"}]})


class FetchDependenciesTests(unittest.TestCase):
    """Mock the HTTP response so tests do not depend on external services."""

    @patch("src.cargo.urlopen")
    def test_fetches_and_decodes_json(self, mocked_urlopen) -> None:
        response = Mock()
        response.read.return_value = json.dumps({
            "dependencies": [{
                "crate_id": "serde_derive",
                "req": "^1.0",
                "kind": None,
                "optional": True,
            }]
        }).encode("utf-8")
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        mocked_urlopen.return_value = response

        result = fetch_dependencies("https://crates.io", "serde", "1.0.0")

        self.assertEqual(result[0].name, "serde_derive")
        request = mocked_urlopen.call_args.args[0]
        self.assertEqual(
            request.full_url,
            "https://crates.io/api/v1/crates/serde/1.0.0/dependencies",
        )
        self.assertEqual(
            request.get_header("User-agent"),
            "dependency-graph-visualizer/0.1 (educational project)",
        )

    @patch("src.cargo.urlopen")
    def test_reports_missing_package_version(self, mocked_urlopen) -> None:
        url = "https://crates.io/api/v1/crates/unknown/1.0.0/dependencies"
        mocked_urlopen.side_effect = HTTPError(
            url, 404, "Not Found", None, None
        )
        with self.assertRaisesRegex(DependencyError, "was not found"):
            fetch_dependencies("https://crates.io", "unknown", "1.0.0")

    @patch("src.cargo.urlopen")
    def test_reports_invalid_json(self, mocked_urlopen) -> None:
        response = Mock()
        response.read.return_value = b"not JSON"
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        mocked_urlopen.return_value = response
        with self.assertRaisesRegex(DependencyError, "invalid JSON"):
            fetch_dependencies("https://crates.io", "serde", "1.0.0")


class TestGraphDependenciesTests(unittest.TestCase):
    """Check loading of direct edges from the local test graph."""

    def test_reads_direct_dependencies(self) -> None:
        result = load_test_dependencies(str(TEST_GRAPH), "A")
        self.assertEqual(result, [Dependency("B"), Dependency("C")])

    def test_removes_duplicate_edges_in_output(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            graph_path = Path(temp_dir) / "graph.json"
            graph_path.write_text(
                json.dumps({"A": ["B", "B"]}), encoding="utf-8"
            )
            self.assertEqual(
                load_test_dependencies(str(graph_path), "A"),
                [Dependency("B")],
            )

    def test_reports_missing_package(self) -> None:
        with self.assertRaisesRegex(DependencyError, "missing"):
            load_test_dependencies(str(TEST_GRAPH), "UNKNOWN")

    def test_reports_invalid_graph_shape(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            graph_path = Path(temp_dir) / "graph.json"
            graph_path.write_text("[]", encoding="utf-8")
            with self.assertRaisesRegex(DependencyError, "JSON object"):
                load_test_dependencies(str(graph_path), "A")


class DependencyVersionTests(unittest.TestCase):
    """Check registry version resolution and basic Cargo requirements."""

    def test_builds_versions_endpoint(self) -> None:
        self.assertEqual(
            build_versions_url("https://crates.io", "serde"),
            "https://crates.io/api/v1/crates/serde/versions",
        )

    def test_matches_caret_and_tilde_requirements(self) -> None:
        self.assertTrue(version_satisfies("1.9.0", "^1.2"))
        self.assertFalse(version_satisfies("2.0.0", "^1.2"))
        self.assertTrue(version_satisfies("0.2.8", "^0.2.3"))
        self.assertFalse(version_satisfies("0.3.0", "^0.2.3"))
        self.assertTrue(version_satisfies("1.2.9", "~1.2.3"))
        self.assertFalse(version_satisfies("1.3.0", "~1.2.3"))

    def test_matches_comparator_ranges(self) -> None:
        self.assertTrue(
            version_satisfies("1.4.0", ">=1.2, <2.0")
        )
        self.assertFalse(
            version_satisfies("2.0.0", ">=1.2, <2.0")
        )

    @patch("src.cargo.urlopen")
    def test_resolves_highest_compatible_non_yanked_version(
        self, mocked_urlopen
    ) -> None:
        response = Mock()
        response.read.return_value = json.dumps({
            "versions": [
                {"num": "1.2.0", "yanked": False},
                {"num": "1.9.0", "yanked": False},
                {"num": "1.8.0", "yanked": True},
                {"num": "2.0.0", "yanked": False},
            ]
        }).encode("utf-8")
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        mocked_urlopen.return_value = response

        version = resolve_dependency_version(
            "https://crates.io", "sample", "^1.0"
        )

        self.assertEqual(version, "1.9.0")
        request = mocked_urlopen.call_args.args[0]
        self.assertEqual(
            request.full_url,
            "https://crates.io/api/v1/crates/sample/versions",
        )

    @patch("src.cargo.urlopen")
    def test_reports_no_compatible_version(self, mocked_urlopen) -> None:
        response = Mock()
        response.read.return_value = json.dumps({
            "versions": [{"num": "2.0.0", "yanked": False}]
        }).encode("utf-8")
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        mocked_urlopen.return_value = response

        with self.assertRaisesRegex(DependencyError, "No stable"):
            resolve_dependency_version(
                "https://crates.io", "sample", "^1.0"
            )


if __name__ == "__main__":
    unittest.main()
