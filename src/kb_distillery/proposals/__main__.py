"""`python -m kb_distillery.proposals nightly --kb <path> [--backend batch] [--dry-run]` and `... collect --kb <path> BATCH`."""
import argparse
import json
import sys

from kb_distillery.proposals import nightly


def main(argv=None):
    ap = argparse.ArgumentParser(prog="kb_distillery.proposals")
    sub = ap.add_subparsers(dest="cmd", required=True)
    n = sub.add_parser("nightly", help="scan the kb and submit one batch of suggestion requests")
    n.add_argument("--kb", required=True)
    n.add_argument("--backend", default="batch", choices=["subscription", "api", "batch"])
    n.add_argument("--dry-run", action="store_true", help="print the candidates and the request count; call nothing")
    c = sub.add_parser("collect", help="turn a finished nightly batch into proposals and suggestions")
    c.add_argument("--kb", required=True)
    c.add_argument("batch")
    a = ap.parse_args(argv)
    try:
        if a.cmd == "nightly" and a.dry_run:
            cands = nightly.scan(a.kb)
            for x in cands:
                print(f"{x['id']}  {x['kind']:<9}  {','.join(x['slugs'])}  {x['detail']}")
            print(f"{len(cands)} request(s) would be sent; nothing was called")
            return 0
        out = nightly.submit(a.kb, a.backend) if a.cmd == "nightly" else nightly.collect(a.kb, a.batch)
    except Exception as e:  # noqa: BLE001  (a CLI prints the failure, it does not trace)
        print(f"error: {e}", file=sys.stderr)
        return 1
    print(json.dumps(out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
