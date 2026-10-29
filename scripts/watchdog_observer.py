"""CLI entrypoint for watchdog observer scheduled task."""
import sys
from pathlib import Path
from src.pipeline import run_watchdog_observer

if __name__ == "__main__":
    db_p = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path("work/project.db").resolve()
    out_h = Path(sys.argv[2]).resolve() if len(sys.argv) > 2 else Path("status.html").resolve()
    res = run_watchdog_observer(db_p, out_h)
    sys.exit(0 if res.get("status") == "OK" else 1)

