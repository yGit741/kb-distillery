"""`python -m kb_distillery.proposals nightly --kb <path> [--backend batch] [--dry-run]`, `... collect --kb <path> BATCH`
and `... demo --kb examples/demo` (seed the demo's local proposals; fixtures, no model call)."""
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
    d = sub.add_parser("demo", help="seed a kb's .local/ with demo proposals, flags and a chat thread (fixtures only)")
    d.add_argument("--kb", default="examples/demo")
    a = ap.parse_args(argv)
    try:
        if a.cmd == "demo":
            from kb_distillery.proposals import demo
            out = demo.seed(a.kb)
            print(f"seeded {len(out['proposals'])} proposals and {len(out['flags'])} flags under {a.kb}/.local")
            return 0
        if a.cmd == "nightly" and a.dry_run:
            cands = nightly.scan(a.kb)
            for x in cands:
                print(f"{x['id']}  {x['kind']:<9}  {','.join(x['slugs'])}  {x['detail']}")
            print(f"{len(cands)} request(s) would be sent; nothing was called")
            known = {r.get("coherence_id") for r in nightly.list_suggestions(a.kb)}
            print(f"{len([w for w in nightly._coherence_pairs(a.kb) if w['id'] not in known])} coherence suggestion(s) "
                  f"would be written (0 LLM)")
            return 0
        out = nightly.submit(a.kb, a.backend) if a.cmd == "nightly" else nightly.collect(a.kb, a.batch)
    except Exception as e:  # noqa: BLE001  (a CLI prints the failure, it does not trace)
        print(f"error: {e}", file=sys.stderr)
        return 1
    print(json.dumps(out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
