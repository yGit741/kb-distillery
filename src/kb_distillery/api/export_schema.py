"""OpenAPI -> web/src/api/schema.d.ts.

    python -m kb_distillery.api.export_schema           write the generated types (pixi run api-schema)
    python -m kb_distillery.api.export_schema --check   fail if the committed file is stale (pixi run api-schema-check)
"""
import argparse
import json
import os
import subprocess
import sys
import tempfile

from kb_distillery.paths import CHECKOUT_ROOT

OUT = os.path.join("web", "src", "api", "schema.d.ts")


def openapi_json():
    from kb_distillery.api.app import create_app
    return json.dumps(create_app(legacy=False).openapi(), indent=2, sort_keys=True) + "\n"


def generate(root):
    """The TypeScript text openapi-typescript produces for the current API."""
    with tempfile.TemporaryDirectory() as tmp:
        spec, out = os.path.join(tmp, "openapi.json"), os.path.join(tmp, "schema.d.ts")
        with open(spec, "w", encoding="utf-8") as f:
            f.write(openapi_json())
        subprocess.run(["npm", "exec", "--prefix", os.path.join(root, "web"), "--", "openapi-typescript",
                        spec, "-o", out], check=True, cwd=root, stdout=subprocess.DEVNULL)
        with open(out, encoding="utf-8") as f:
            return f.read()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    root = CHECKOUT_ROOT          # the frontend is code: it lives with the explorer, not the vault
    target = os.path.join(root, OUT)
    text = generate(root)
    if args.check:
        have = open(target, encoding="utf-8").read() if os.path.isfile(target) else None
        if have != text:
            print(f"{OUT} is stale: run `pixi run api-schema` and commit it", file=sys.stderr)
            return 1
        print(f"{OUT} is up to date")
        return 0
    os.makedirs(os.path.dirname(target), exist_ok=True)
    with open(target, "w", encoding="utf-8") as f:
        f.write(text)
    print(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
