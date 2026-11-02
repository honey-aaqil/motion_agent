"""Single-command launcher for Motion Agent Interactive Web GUI."""
from __future__ import annotations
import sys
import time
import webbrowser
from pathlib import Path
from src.pipeline import init_database, start_dashboard_server, run_supervisor_tick

def main() -> None:
    work_dir = Path("work").resolve()
    work_dir.mkdir(parents=True, exist_ok=True)
    db_path = work_dir / "dashboard_demo.db"
    conn = init_database(db_path)
    conn.close()

    port = 8000
    try:
        srv, th, url = start_dashboard_server(host="127.0.0.1", port=port, db_path=db_path)
    except OSError:
        srv, th, url = start_dashboard_server(host="127.0.0.1", port=0, db_path=db_path)

    print("=" * 64)
    print("  Motion Agent Interactive Web GUI & Supervisor")
    print(f"  URL: {url}")
    print("  Open this URL in any browser to access the GUI.")
    print("  Press Ctrl+C to stop the dashboard server.")
    print("=" * 64)

    try:
        webbrowser.open(url)
    except Exception:
        pass

    last_tick = 0.0
    try:
        while th.is_alive():
            now = time.time()
            if now - last_tick >= 5.0:
                _ = run_supervisor_tick(db_path)
                last_tick = now
            time.sleep(0.5)
    except KeyboardInterrupt:
        print("\nShutting down GUI dashboard...")
        srv.shutdown()
        srv.server_close()
        th.join(timeout=2.0)
        print("Dashboard stopped cleanly.")

if __name__ == "__main__":
    main()

