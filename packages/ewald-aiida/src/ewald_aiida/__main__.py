"""``python -m ewald_aiida tree 1234`` / ``find --process PwRelaxWorkChain [--host nurion]``."""
from __future__ import annotations

import argparse
import json


def main(argv=None):
    parser = argparse.ArgumentParser(prog="ewald-aiida", description="Browse AiiDA results for EWALD (read-only).")
    parser.add_argument("--profile", help="AiiDA profile (default: the default profile)")
    parser.add_argument("--python", help="remote Python with aiida-core (default: the one verdi uses)")
    sub = parser.add_subparsers(dest="command", required=True)
    t = sub.add_parser("tree", help="provenance tree of a node: called processes and outputs")
    t.add_argument("node", help="PK, UUID, aiida:... or aiida://host/...")
    t.add_argument("--depth", type=int, default=4)
    f = sub.add_parser("find", help="recent processes")
    f.add_argument("--host", help="[user@]host[:port] whose AiiDA profile to search (default: this machine)")
    f.add_argument("--process", help="process label, %% wildcards allowed (PhonopyWorkChain, Pw%%)")
    f.add_argument("--limit", type=int, default=20)
    f.add_argument("--ok", action="store_true", help="only finished with exit status 0")
    f.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    from .browse import find, tree

    if args.command == "tree":
        print(tree(args.node, args.profile, depth=args.depth, python=args.python))
        return
    rows = find(args.process, args.profile, args.limit, True if args.ok else None, args.host, args.python)
    if args.json:
        print(json.dumps(rows, indent=1))
        return
    for r in rows:
        status = r["exit_status"] if r["exit_status"] is not None else ""
        print(f"{r['pk']:>8}  {r['process_label']:<28} {r['state'] or '':<9} {status:>4}  "
              f"{r['ctime'][:16]}  {r['uri']}  {r['label']}")


if __name__ == "__main__":
    main()
