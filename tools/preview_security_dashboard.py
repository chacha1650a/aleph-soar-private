"""Loopback-only dashboard preview with a new disposable SQLite database."""
import argparse
from contextlib import closing
from pathlib import Path
import sys
import tempfile
from wsgiref.simple_server import make_server

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services/ticket-store"))
from ticket_store.app import create_dashboard_app
from ticket_store import db, samples


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--samples", action="store_true", help="show explicitly synthetic sample tickets")
    parser.add_argument("--s12-comparison", action="store_true", help="include a clearly labelled synthetic comparison (requires --samples)")
    parser.add_argument("--port", type=int, default=8089)
    args = parser.parse_args()
    if args.s12_comparison and not args.samples:
        parser.error('--s12-comparison requires --samples')
    if not 1 <= args.port <= 65535:
        parser.error("port must be 1..65535")
    origin = f"http://127.0.0.1:{args.port}"
    with tempfile.TemporaryDirectory(prefix="haedam-dashboard-preview-") as folder:
        path = str(Path(folder) / "preview.db")
        app = create_dashboard_app(path, origin)
        app.config["TEMPLATES_AUTO_RELOAD"] = True
        app.jinja_env.auto_reload = True
        if args.samples:
            with closing(db.connect(path)) as conn:
                samples.load_samples(conn)
                if args.s12_comparison:
                    import json
                    from ticket_store.s12_measurements import import_comparison
                    examples = ROOT / 'contracts/s12-examples'
                    import_comparison(conn, json.loads((examples / 'comparison.sample.json').read_text(encoding='utf-8')),
                                      examples / 'before.sample.csv', examples / 'after.sample.csv')
        print(f"Dashboard preview: {origin}/" + ("?sample=1" if args.samples else ""), flush=True)
        print("Disposable DB; sample data only; no n8n/target service is started.", flush=True)
        try:
            with make_server("127.0.0.1", args.port, app) as server:
                server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
