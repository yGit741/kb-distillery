"""Generic text rewrites for path and command references (docs, configs, strings in code).

Applied to tooling text only (never wiki/, think/, raw/ or vault data in meta/). Order matters:
commands first (they become `-m kb....`), then module names, then path prefixes (longest first).
"""
import re

from layout import DASHBOARD_TO_SERVICES, DASHBOARD_STAYS, PKG, TESTS, TEST_PACKAGE, TOP_MODULES, WHOLE_PACKAGES
from codemod import map_dotted

KB = PKG
_mods = "|".join(sorted(TOP_MODULES, key=len, reverse=True))
_pkgs = "|".join(WHOLE_PACKAGES)
_dash_data = "|".join(sorted(DASHBOARD_TO_SERVICES, key=len, reverse=True))


def _cmd_dotted(m):
    new = map_dotted("meta." + m.group("mod"))
    return f"{m.group('py')} -m {new}" if new else m.group(0)


def _cmd_script(m):
    name = m.group("name")
    return f"{m.group('py')} -m kb.{TOP_MODULES[name]}.{name}"


def _dotted(m):
    new = map_dotted("meta." + m.group("mod"))
    return new if new else m.group(0)


RULES = []


def rule(pattern, repl, flags=0):
    RULES.append((re.compile(pattern, flags), repl))


# 1. commands
rule(r"(?P<py>python3?|\$\{?PYTHON\}?) -m meta\.(?P<mod>[A-Za-z_][\w.]*)", _cmd_dotted)
rule(r"(?P<py>python3?) (?:\./)?meta/(?P<name>%s)\.py\b" % _mods, _cmd_script)
rule(r'sys\.executable, os\.path\.join\((?:\w+), (?:"meta", )?"(?P<name>%s)\.py"\)' % _mods,
     lambda m: f'sys.executable, "-m", "kb.{TOP_MODULES[m.group("name")]}.{m.group("name")}"')
# mock.patch("ship.changed_paths") / patch("graph_data.x"): bare module names inside patch() targets
_bare = "|".join(sorted(set(TOP_MODULES) | set(DASHBOARD_TO_SERVICES) | set(WHOLE_PACKAGES), key=len, reverse=True))
rule(r'(?P<pre>patch\(\s*["\'])(?P<mod>%s)(?P<rest>\.\w)' % _bare,
     lambda m: m.group("pre") + (map_dotted(m.group("mod")) or m.group("mod")) + m.group("rest"))
# 2. dotted module names (only known first components; `meta.get(` etc. are untouched)
rule(r"(?<![\w.])meta\.(?P<mod>(?:%s|%s|dashboard)(?:\.\w+)*)(?![\w(])" % (_mods, _pkgs), _dotted)
# os.path.join(ROOT, "meta", "dashboard", ...) style arguments (longest first)
for _old, _new in (('"meta", "share", "worker"', '"share"'),
                   ('"meta", "dashboard", "prompts"', '"backend", "src", "kb", "prompts"'),
                   ('"meta", "skills"', '"skills"'),
                   ('"meta", "githooks"', '"tools", "githooks"'),
                   ('"meta", "launchd"', '"tools", "launchd"'),
                   ('"meta", "dashboard"', '"backend", "src", "kb", "dashboard"'),
                   ('"meta", "share"', '"backend", "src", "kb", "share"'),
                   ('"meta", "ingest"', '"backend", "src", "kb", "ingest"'),
                   ('"meta", "distill"', '"backend", "src", "kb", "distill"'),
                   ('"meta", "report"', '"backend", "src", "kb", "report"')):
    rule(re.escape(_old), _new.replace("\\", "\\\\"))
rule(r'(?<=ROOT, )"meta", "migrations", "(?P<f>\d{4}_\w+\.py)"', lambda m: f'"backend", "src", "kb", "migrations", "{m.group("f")}"')
# 3. path prefixes
P = [
    (r"meta/dashboard/prompts", f"{KB}/prompts"),
    (r"meta/share/worker", "share"),
    (r"meta/share", f"{KB}/share"),
    (r"meta/(?P<pkg>%s)(?!/sync\.toml)(?=[/\s\"'`),:.]|$)" % _pkgs, lambda m: f"{KB}/{m.group('pkg')}"),
    (r"meta/dashboard/(?P<mod>%s)\.py" % _dash_data, lambda m: f"{KB}/services/{DASHBOARD_TO_SERVICES[m.group('mod')]}.py"),
    (r"meta/dashboard", f"{KB}/dashboard"),
    (r"meta/skills", "skills"),
    (r"meta/githooks", "tools/githooks"),
    (r"meta/launchd", "tools/launchd"),
    (r"meta/launch\.sh", "tools/launch.sh"),
    (r"meta/tests", TESTS),
    (r"meta/testdata", f"{TESTS}/testdata"),
    (r"meta/migrations/(?!applied\.tsv)", f"{KB}/migrations/"),
    (r"meta/(?P<name>%s)\.py\b" % _mods, lambda m: f"{KB}/{TOP_MODULES[m.group('name')]}/{m.group('name')}.py"),
    (r"meta/test_(?P<name>\w+)\.py", lambda m: f"{TESTS}/{TEST_PACKAGE[m.group('name')] + '/' if m.group('name') in TEST_PACKAGE else ''}test_{m.group('name')}.py"),
]
for pat, repl in P:
    rule(r"(?<![\w.\-])" + pat, repl)


def apply_rules(text):
    n = 0
    for rx, repl in RULES:
        text, k = rx.subn(repl, text)
        n += k
    return text, n
