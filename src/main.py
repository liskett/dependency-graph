"""Application entry point for stage 1."""

from src.config import parse_config


def main() -> int:
    """Print validated settings as key-value pairs."""
    config = parse_config()
    print("Application configuration:")
    for key, value in config.as_dict().items():
        print(f"{key} = {value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
