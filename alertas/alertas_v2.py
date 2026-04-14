"""CLI legacy wrapper for the refactored alert engine."""

try:
    from alertas.app.cli import main
except ModuleNotFoundError:
    from app.cli import main


if __name__ == "__main__":
    main()
