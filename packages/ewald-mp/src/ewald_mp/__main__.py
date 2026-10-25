"""``python -m ewald_mp search Li-P-S --stable [--json]``."""
from __future__ import annotations

import argparse
import json
import sys


def main(argv=None) -> int:
    from .search import search

    ap = argparse.ArgumentParser(prog="ewald-mp", description="Search the Materials Project (your API key)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("search", help="a formula, Li-P-S, 'Li P S' or mp-149")
    s.add_argument("query", nargs="+")
    s.add_argument("--stable", action="store_true", help="only materials on the convex hull")
    s.add_argument("--limit", type=int, default=None)
    s.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    res = search(" ".join(args.query), limit=args.limit, **({"is_stable": True} if args.stable else {}))
    if args.json:
        json.dump([h.as_dict() for h in res], sys.stdout, indent=1)
        print()
    else:
        print(repr(res))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
