from .cli import main

if __name__ == "__main__":
    from kb_distillery.ops import wrap

    # every writing subcommand ends in one kb(...) commit on main (--no-commit to skip)
    raise SystemExit(wrap.run(main, table=wrap.INGEST, begin_table=wrap.INGEST_BEGIN))
