"""Command-line configuration and validation."""

import argparse
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from urllib.parse import urlsplit


PACKAGE_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]*")
VERSION_PATTERN = re.compile(
    r"(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
    r"(?:-([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?"
    r"(?:\+([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?"
)
EMPTY = 0


@dataclass(frozen=True)
class AppConfig:
    """Store the application settings parsed from command-line arguments."""

    package: str
    repository: str
    test_mode: bool
    version: str
    output: str
    max_depth: int

    def as_dict(self) -> dict[str, str | bool | int]:
        """Return settings as a dictionary for readable console output."""
        return asdict(self)


def validate_package(value: str) -> str:
    """Validate the package name used by Cargo."""
    if not PACKAGE_PATTERN.fullmatch(value):
        raise argparse.ArgumentTypeError(
            "package must contain only letters, digits, '_' or '-'."
        )
    return value


def validate_version(value: str) -> str:
    """Validate a package version in MAJOR.MINOR.PATCH form."""
    if not VERSION_PATTERN.fullmatch(value):
        raise argparse.ArgumentTypeError(
            "version must use MAJOR.MINOR.PATCH, for example 1.2.3."
        )
    return value


def validate_output(value: str) -> str:
    """Require an output path with an SVG extension."""
    path = Path(value)
    if not value.strip() or path.name in {"", ".", ".."}:
        raise argparse.ArgumentTypeError("output path must not be empty.")
    if path.suffix.lower() != ".svg":
        raise argparse.ArgumentTypeError(
            "output file must have .svg extension."
        )
    return value


def validate_depth(value: str) -> int:
    """Parse a non-negative maximum graph depth."""
    try:
        depth = int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError(
            "max-depth must be a non-negative integer."
        ) from error
    if depth < EMPTY:
        raise argparse.ArgumentTypeError(
            "max-depth must be a non-negative integer."
        )
    return depth


def is_http_url(value: str) -> bool:
    """Return whether value is an absolute HTTP(S) URL."""
    parsed = urlsplit(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def build_parser() -> argparse.ArgumentParser:
    """Create the command-line parser for the application."""
    parser = argparse.ArgumentParser(
        description="Inspect and visualize Cargo package dependencies."
    )
    parser.add_argument(
        "--package",
        required=True,
        type=validate_package,
        help="name of the Cargo package to analyze",
    )
    parser.add_argument(
        "--repository",
        required=True,
        help="HTTP(S) registry URL or path to a test graph file",
    )
    parser.add_argument(
        "--test-mode",
        action="store_true",
        help="treat --repository as a local test file path",
    )
    parser.add_argument(
        "--version",
        required=True,
        type=validate_version,
        help="exact package version, such as 1.2.3",
    )
    parser.add_argument(
        "--output",
        default="dependency_graph.svg",
        type=validate_output,
        help="path for the SVG graph (default: dependency_graph.svg)",
    )
    parser.add_argument(
        "--max-depth",
        default=5,
        type=validate_depth,
        help="maximum dependency depth; 0 includes only the root package",
    )
    return parser


def parse_config(argv: list[str] | None = None) -> AppConfig:
    """Parse and validate arguments, returning an immutable config."""
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.test_mode:
        if not Path(args.repository).is_file():
            parser.error("in test mode, --repository must point to a file.")
    elif not is_http_url(args.repository):
        parser.error("--repository must be an absolute HTTP(S) URL.")

    return AppConfig(
        package=args.package,
        repository=args.repository,
        test_mode=args.test_mode,
        version=args.version,
        output=args.output,
        max_depth=args.max_depth,
    )
