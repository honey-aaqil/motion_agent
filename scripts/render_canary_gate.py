"""CLI entrypoint for post-render canaries gate."""
import sys
from pathlib import Path
from src.pipeline import run_canary_gate

if __name__ == "__main__":
    p = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path.cwd()
    sys.exit(0 if run_canary_gate(p, {}).get("passed") else 1)
