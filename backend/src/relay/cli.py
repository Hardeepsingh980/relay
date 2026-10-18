"""Command line: `uv run relay <command>`."""

from __future__ import annotations

import argparse
import json
import sys


def main(argv: list[str] | None = None) -> int:
    from . import tenants

    ap = argparse.ArgumentParser(prog="relay", description="Relay company brain")
    ap.add_argument("--tenant", choices=sorted(tenants.TENANTS), default=None,
                    help="sample company (default: $RELAY_TENANT or cheerio)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("seed", help="generate the synthetic exports into data/<tenant>")
    b = sub.add_parser("build", help="build the FalkorDB graph from the exports")
    b.add_argument("--extractor", choices=["seed", "gemini"], default=None)
    sub.add_parser("reset", help="restore the working graph to the pristine build")
    sub.add_parser("eval", help="check the graph against the planted story")
    sv = sub.add_parser("serve", help="run the API server")
    sv.add_argument("--port", type=int, default=8020)
    sv.add_argument("--reload", action="store_true")
    m = sub.add_parser("mcp", help="run the Relay MCP server for the tenant (stdio, or --http)")
    m.add_argument("--http", action="store_true", help="serve streamable HTTP instead of stdio")
    m.add_argument("--port", type=int, default=8721)
    args = ap.parse_args(argv)
    t = tenants.get(args.tenant)

    if args.cmd == "seed":
        print(json.dumps(t.generator().generate(t.data_dir)["counts"], indent=2))
    elif args.cmd == "build":
        from .ingest.pipeline import build
        print(json.dumps(build(extractor=args.extractor, tenant=t.id), indent=2))
    elif args.cmd in ("reset", "eval"):
        from . import db
        from .ingest.pipeline import demo_graph, reset
        token = db.use_graph(demo_graph(t))
        try:
            if args.cmd == "reset":
                reset()
                print(f"{t.name} graph reset")
            else:
                from .evaluate import run_eval
                return 0 if run_eval() else 1
        finally:
            db.reset_graph(token)
    elif args.cmd == "serve":
        import uvicorn
        uvicorn.run("relay.api:app", host="0.0.0.0", port=args.port, reload=args.reload)
    elif args.cmd == "mcp":
        from .health.mcp_server import main as mcp_main
        mcp_main(t.id, http=args.http, port=args.port)
    return 0


if __name__ == "__main__":
    sys.exit(main())
