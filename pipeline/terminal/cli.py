"""CLI entry point for Anka Terminal.

Usage:
    python -m pipeline.terminal              # start on port 8501, open browser
    python -m pipeline.terminal --port 9000  # custom port
    python -m pipeline.terminal --no-open    # don't auto-open browser
"""
import argparse
import sys
import threading
import time
import webbrowser
from pathlib import Path

# Legacy modules (signal_tracker, kite_client, et al) use bare top-level
# imports like `from config import ...` that resolve only when pipeline/
# is on sys.path. Add it so /api/live_ltp can route through
# signal_tracker.fetch_current_prices.
_PIPELINE_DIR = Path(__file__).resolve().parent.parent
if str(_PIPELINE_DIR) not in sys.path:
    sys.path.insert(0, str(_PIPELINE_DIR))


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        prog="anka-terminal",
        description="Anka Terminal — Trading Intelligence Terminal",
    )
    parser.add_argument("--port", type=int, default=8501, help="Port to serve on (default: 8501)")
    parser.add_argument("--no-open", action="store_true", help="Don't auto-open browser")
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    url = f"http://localhost:{args.port}"

    if not args.no_open:
        def open_browser():
            time.sleep(1.5)
            webbrowser.open(url)
        threading.Thread(target=open_browser, daemon=True).start()

    print(f"\n  Anka Terminal running at {url}\n  Press Ctrl+C to stop.\n")

    import uvicorn
    uvicorn.run("pipeline.terminal.app:app", host="127.0.0.1", port=args.port, log_level="warning")
