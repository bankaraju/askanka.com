"""CLI entry point for Anka Terminal.

Usage:
    python -m pipeline.terminal              # start on port 8501, open browser
    python -m pipeline.terminal --port 9000  # custom port
    python -m pipeline.terminal --no-open    # don't auto-open browser
"""
import argparse
import threading
import time
import webbrowser


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
