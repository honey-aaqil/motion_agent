"""CLI entrypoint for canary sabotage test suite."""
import sys
from pathlib import Path
from src.pipeline import run_sabotage_suite

if __name__ == "__main__":
    p = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path.cwd()
    sys.exit(0 if run_sabotage_suite(p).get("passed") else 1)
