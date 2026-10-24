from .cli import main

if __name__ == "__main__":
    from kb.ops import wrap

    # `apply` ends in one kb(distill) commit on main (--no-commit to skip)
    raise SystemExit(wrap.run(main, table=wrap.DISTILL))
