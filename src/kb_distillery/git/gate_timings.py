"""Load against throughput: one line per real gate run, and the report that reads them.

Every gate `ship` really runs (not a reused one, not a mocked one) appends a line to `kb-gate-timings.tsv` in the git
*common* dir, shared by all worktrees like the gate slot: when it started, the branch, the gate, how long it took,
its exit code, and the machine at the start (1-minute load, percent of memory free, pytest workers, day or night).

`ship night report` groups those lines by load band and shows how much slower the same work became in each. That is
the evidence for the night limit: parallel work is worth adding only up to the band where gates stop slowing down
faster than work is added. Two kinds of gate are read:

- constant-work gates (`ruff`, `lint-imports`: the same files every time), whose duration is compared to their own
  median in the quietest band that has enough of them, so the slowdown is that of the machine and not of the change
  under test. A day run is compared with day runs and a night run with night runs: day gates are niced, night
  gates are not, and mixing them would read the priority as load;
- the `tests` gate, shown as plain median seconds (its size follows the commit, so it is only a rough guide).

A band says nothing until it has MIN_RUNS constant-work runs: one slow run is not a verdict.
"""
import contextlib
import os
import statistics
import subprocess
import sys
import time

from kb_distillery.git.queue import common_dir

FILE = "kb-gate-timings.tsv"
FIELDS = ("ts", "branch", "gate", "secs", "rc", "load", "mem", "workers", "mode")
MAX_BYTES = 1_000_000            # then the file is moved to <FILE>.1 (still read) and a new one starts
CONSTANT = ("ruff", "lint-imports")
DEFAULT_HOURS = 16.0
BANDS = (0.5, 1.0, 2.0)          # load per core: under half, up to the core count, up to twice, and over
MIN_RUNS = 3                     # constant-work runs a band needs before its slowdown is shown or judged
SATURATED = 2.0                  # the same work taking this many times as long is the saturation point


def mem_free():
    """Percent of memory free, or None where it cannot be read."""
    try:
        if sys.platform == "darwin":
            out = subprocess.run(["sysctl", "-n", "kern.memorystatus_level"], capture_output=True, text=True,
                                 timeout=5, check=False).stdout
            return float(out.strip())
        with open("/proc/meminfo", encoding="utf-8") as f:
            info = {line.split(":")[0]: float(line.split()[1]) for line in f if ":" in line}
        return round(100.0 * info["MemAvailable"] / info["MemTotal"], 1)
    except (OSError, ValueError, KeyError, IndexError, subprocess.SubprocessError):
        return None


def machine():
    """(1-minute load, percent of memory free or None) right now."""
    try:
        load = os.getloadavg()[0]
    except OSError:
        load = 0.0
    return load, mem_free()


def snapshot(root):
    """(load, memory free, branch) at the start of a gate. Never raises: on any failure the cell is 0, None or ""."""
    try:
        load, mem = machine()
    except Exception:       # noqa: BLE001  a reading is never worth a failed gate
        load, mem = 0.0, None
    try:
        branch = subprocess.run(["git", "symbolic-ref", "--short", "-q", "HEAD"], cwd=root, capture_output=True,
                                text=True, timeout=10, check=False).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        branch = ""
    return load, mem, branch


def _path(root):
    return os.path.join(common_dir(root), FILE)


def record(root, gate, secs, rc, load, mem, workers="", mode="day", branch="", now=None):
    """Append one run. Never raises (a timing line is not worth a failed gate) and never creates the git dir: where
    `root` is not a repository there is nowhere to write, and nothing is written."""
    with contextlib.suppress(OSError, ValueError, subprocess.SubprocessError):
        path = _path(root)
        if not os.path.isdir(os.path.dirname(path)):
            return
        if os.path.exists(path) and os.path.getsize(path) > MAX_BYTES:
            os.replace(path, path + ".1")
        row = (f"{(time.time() if now is None else now):.0f}", branch, gate, f"{secs:.1f}", str(rc), f"{load:.1f}",
               "" if mem is None else f"{mem:.0f}", str(workers), mode)
        with open(path, "a", encoding="utf-8") as f:
            f.write("\t".join(c.replace("\t", " ").replace("\n", " ") for c in row) + "\n")


def read(root, since=0.0):
    """The recorded runs from `since` (epoch seconds) on, oldest first, the rolled-over file included; malformed
    lines are skipped."""
    rows = []
    with contextlib.suppress(OSError, subprocess.SubprocessError):
        path = _path(root)
        for name in (path + ".1", path):
            try:
                with open(name, encoding="utf-8") as f:
                    lines = f.readlines()
            except OSError:
                continue
            for line in lines:
                cells = line.rstrip("\n").split("\t")
                if len(cells) != len(FIELDS):
                    continue
                row = dict(zip(FIELDS, cells))
                try:
                    row["ts"], row["secs"], row["load"] = float(row["ts"]), float(row["secs"]), float(row["load"])
                    row["rc"] = int(row["rc"])
                except ValueError:
                    continue
                if row["ts"] >= since:
                    rows.append(row)
    return sorted(rows, key=lambda r: r["ts"])


def band_of(load, cores):
    """Index of the load band (0 = quietest) for a 1-minute load on `cores` cores."""
    per_core = load / max(cores, 1)
    return sum(per_core >= edge for edge in BANDS)


def band_label(index, cores):
    edges = [edge * cores for edge in BANDS]
    if index == 0:
        return f"load under {edges[0]:g}"
    if index == len(edges):
        return f"load {edges[-1]:g} and over"
    return f"load {edges[index - 1]:g} to {edges[index]:g}"


def baselines(const, cores):
    """{(mode, gate): median seconds} from, for each mode, the quietest band that holds MIN_RUNS constant-work runs
    of that mode; and {mode: that band}. A mode without such a band has no baseline."""
    base, where = {}, {}
    for mode in sorted({r["mode"] for r in const}):
        mine = [r for r in const if r["mode"] == mode]
        for band in sorted({band_of(r["load"], cores) for r in mine}):
            here = [r for r in mine if band_of(r["load"], cores) == band]
            if len(here) >= MIN_RUNS:
                where[mode] = band
                for gate in CONSTANT:
                    secs = [r["secs"] for r in here if r["gate"] == gate]
                    if secs:
                        base[(mode, gate)] = statistics.median(secs)
                break
    return base, where


def _span(seconds):
    return f"{seconds / 3600:.1f} h" if seconds >= 3600 else f"{max(seconds / 60, 1):.0f} min"


def report(root, hours=None, now=None, cores=None):
    """The table `ship night report` prints: runs, slowdown of constant work and median tests gate per load band."""
    now = time.time() if now is None else now
    hours = DEFAULT_HOURS if hours is None else float(hours)
    cores = cores or os.cpu_count() or 1
    rows = [r for r in read(root, since=now - hours * 3600) if r["rc"] == 0]
    if not rows:
        return f"gate timings: no successful gate run in the last {hours:g} hours"
    seconds = rows[-1]["ts"] - rows[0]["ts"]
    rate = f", {len(rows) / (seconds / 3600):.1f} per hour" if seconds >= 3600 else ""     # a rate needs an hour of data
    const = [r for r in rows if r["gate"] in CONSTANT and r["secs"] > 0]
    base, where = baselines(const, cores)
    ratios = {}
    for r in const:
        if (r["mode"], r["gate"]) in base:
            ratios.setdefault(band_of(r["load"], cores), []).append(r["secs"] / base[(r["mode"], r["gate"])])
    slow = {band: statistics.median(v) for band, v in ratios.items() if len(v) >= MIN_RUNS}
    lines = [f"gate timings, last {hours:g} hours: {len(rows)} gate runs over {_span(seconds)}{rate}, {cores} cores",
             f"{'load at start':<22}{'runs':>6}{'night':>7}{'constant work':>16}{'tests gate (median)':>22}"]
    for band in sorted({band_of(r["load"], cores) for r in rows}):
        got = [r for r in rows if band_of(r["load"], cores) == band]
        tests = [r["secs"] for r in got if r["gate"] == "tests"]
        lines.append(f"{band_label(band, cores):<22}{len(got):>6}{sum(r['mode'] == 'night' for r in got):>7}"
                     f"{(f'{slow[band]:.1f}x' if band in slow else 'few runs'):>16}"
                     f"{(f'{statistics.median(tests):.0f} s' if tests else '-'):>22}")
    names = " and ".join(CONSTANT)
    if not base:
        lines.append(f"no baseline yet: no load band has {MIN_RUNS} runs of {names} (the gates whose effort is the "
                     "same every run), so nothing can be said about the night limit.")
        return "\n".join(lines)
    quiet = ", ".join(f"{mode} runs: {band_label(band, cores)}" for mode, band in sorted(where.items()))
    lines.append(f"constant work: {names} take the same effort every run. 1.0x is their median in the quietest band "
                 f"with {MIN_RUNS} such runs ({quiet}); day runs (low priority) and night runs (normal priority) are "
                 "each compared with their own kind.")
    busy = [b for b in sorted(slow) if slow[b] >= SATURATED]
    if busy:
        lines.append(f"saturation: from {band_label(busy[0], cores)} the same work took {slow[busy[0]]:.1f}x as long. "
                     "More parallel work past that point slows everything; keep the night limit at or under it.")
    elif len(slow) > 1:
        lines.append(f"no saturation seen: the busiest band with enough runs ({band_label(max(slow), cores)}) ran the "
                     f"same work at {slow[max(slow)]:.1f}x. The night limit can stay or go up.")
    else:
        lines.append(f"one load band with {MIN_RUNS} such runs: not enough spread to judge the night limit yet.")
    return "\n".join(lines)
