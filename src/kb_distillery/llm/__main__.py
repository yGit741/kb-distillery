"""CLI for kb_distillery.llm: `pixi run llm -- ask "prompt" [--backend api] [--model haiku]`, `submit FILE`, `status ID`, `collect ID`.

FILE for submit is JSONL, one Request per line ({"prompt": ..., "id": ..., "model": ...}) or plain prompt lines."""
import argparse
import dataclasses
import json
import sys

from kb_distillery import llm


def _requests(path):
    out = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except ValueError:
                row = line
            out.append(llm.Request(**row) if isinstance(row, dict) else llm.Request(prompt=str(row)))
    return out


def _print(results):
    for r in results:
        print(json.dumps(dataclasses.asdict(r), ensure_ascii=False))
    total = sum(r.usd for r in results)
    bad = sum(not r.ok for r in results)
    print(f"# {len(results)} results, {bad} failed, usd {total:.6f}", file=sys.stderr)
    return 1 if bad else 0


def main(argv=None):
    ap = argparse.ArgumentParser(prog="kb_distillery.llm")
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("ask")
    a.add_argument("prompt")
    a.add_argument("--backend", choices=llm.BACKENDS)
    a.add_argument("--model", default="haiku")
    a.add_argument("--system", default="")
    a.add_argument("--max-tokens", type=int, default=1024)
    a.add_argument("--effort", default="low")
    s = sub.add_parser("submit")
    s.add_argument("file")
    st = sub.add_parser("status")
    st.add_argument("id")
    c = sub.add_parser("collect")
    c.add_argument("id")
    c.add_argument("--poll", type=int, default=30)
    c.add_argument("--wait", type=int, default=0, help="seconds to wait for the batch to end (0: check once)")
    args = ap.parse_args(argv)

    if args.cmd == "ask":
        return _print([llm.ask(args.prompt, backend=args.backend, model=args.model, system=args.system,
                               max_tokens=args.max_tokens, effort=args.effort)])
    if args.cmd == "submit":
        print(llm.submit(_requests(args.file)))
        return 0
    if args.cmd == "status":
        print(json.dumps(llm.status(args.id), indent=1))
        return 0
    return _print(llm.collect(args.id, poll_every=args.poll, wait_s=args.wait))


if __name__ == "__main__":
    sys.exit(main())
