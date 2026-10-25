"""``python -m ewald_optimade search LiFePO4 --db mp`` / ``python -m ewald_optimade databases``."""
from __future__ import annotations

import argparse
import json
import sys


def main(argv=None) -> int:
    from . import providers as P
    from .search import search

    ap = argparse.ArgumentParser(prog="ewald-optimade", description="Search OPTIMADE structure databases")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("search", help="list structures: a formula, Li-P-S, 'Li P S' or an OPTIMADE filter")
    s.add_argument("query", nargs="*")
    s.add_argument("--db", default=None)
    s.add_argument("--limit", type=int, default=None)
    s.add_argument("--json", action="store_true")
    sub.add_parser("databases", help="the known databases")
    args = ap.parse_args(argv)
    if args.cmd == "databases":
        for p in P.providers().values():
            print(f"{p.name:<20} {p.title:<45} {p.base_url}")
        return 0
    res = search(" ".join(args.query), db=args.db, limit=args.limit)
    if args.json:
        json.dump({"filter": res.filter, "total": res.total, "hits": [h.as_dict() for h in res]}, sys.stdout,
                  indent=1)
        print()
    else:
        print(repr(res))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
