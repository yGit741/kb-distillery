"""Load against throughput: one line per real gate run, and the report that reads them.

Every gate `ship` really runs (not a reused one, not a mocked one) appends a line to `kb-gate-timings.tsv` in the git
*common* dir, shared by all worktrees like the gate slot: when it started, the branch, the gate, how long it took,
its exit code, and the machine at the start (1-minute load, percent of memory free, pytest workers, day or night).

`ship night report` groups those lines by load band and shows how much slower the same work became in each. That is
the evidence for the night limit: parallel work is worth adding only up to the band where gates stop slowing down
faster than work is added. Two kinds of gate are read:

- constant-work gates (`ruff`, `lint-imports`: the same files every time), whose duration is compared to their own
  median in the quietest band, so the slowdown is that of the machine and not of the change under test;
- the `tests` gate, shown as plain median seconds (its size follows the commit, so it is only a rough guide).
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
MAX_BYTES = 1_000_000            # then the file is moved to <FILE>.1 and a new one starts
CONSTANT = ("ruff", "lint-imports")
DEFAULT_HOURS = 16.0
BANDS = (0.5, 1.0, 2.0)          # load per core: under half, up to the core count, up to twice, and over


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


def _path(root):
    return os.path.join(common_dir(root), FILE)


def record(root, gate, secs, rc, load, mem, workers="", mode="day", branch="", now=None):
    """Append one run. Never raises: a timing line is not worth a failed gate."""
    with contextlib.suppress(OSError, ValueError, subprocess.SubprocessError):
        path = _path(root)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        if os.path.exists(path) and os.path.getsize(path) > MAX_BYTES:
            os.replace(path, path + ".1")
        row = (f"{(time.time() if now is None else now):.0f}", branch, gate, f"{secs:.1f}", str(rc), f"{load:.1f}",
               "" if mem is None else f"{mem:.0f}", str(workers), mode)
        with open(path, "a", encoding="utf-8") as f:
            f.write("\t".join(c.replace("\t", " ").replace("\n", " ") for c in row) + "\n")


def read(root, since=0.0):
    """The recorded runs from `since` (epoch seconds) on, oldest first; malformed lines are skipped."""
    rows = []
    try:
        with open(_path(root), encoding="utf-8") as f:
            for line in f:
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
    except OSError:
        pass
    return rows


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


def report(root, hours=None, now=None, cores=None):
    """The table `ship night report` prints: runs, slowdown of constant work and median tests gate per load band."""
    now = time.time() if now is None else now
    hours = DEFAULT_HOURS if hours is None else float(hours)
    cores = cores or os.cpu_count() or 1
    rows = [r for r in read(root, since=now - hours * 3600) if r["rc"] == 0]
    if not rows:
        return f"gate timings: no successful gate run in the last {hours:g} hours ({_path(root)})"
    span = max((rows[-1]["ts"] - rows[0]["ts"]) / 3600, 1 / 60)
    by_band = {}
    for r in rows:
        by_band.setdefault(band_of(r["load"], cores), []).append(r)
    quietest = min(by_band)
    base = {}
    for gate in CONSTANT:
        secs = [r["secs"] for r in by_band[quietest] if r["gate"] == gate and r["secs"] > 0]
        if secs:
            base[gate] = statistics.median(secs)
    lines = [f"gate timings, last {hours:g} hours: {len(rows)} gate runs over {span:.1f} h "
             f"({len(rows) / span:.1f} per hour), {cores} cores",
             f"{'load at start':<22}{'runs':>6}{'night':>7}{'constant work':>16}{'tests gate (median)':>22}"]
    slow = {}
    for band in sorted(by_band):
        got = by_band[band]
        ratios = [r["secs"] / base[r["gate"]] for r in got if r["gate"] in base]
        tests = [r["secs"] for r in got if r["gate"] == "tests"]
        if ratios:
            slow[band] = statistics.median(ratios)
        lines.append(f"{band_label(band, cores):<22}{len(got):>6}{sum(r['mode'] == 'night' for r in got):>7}"
                     f"{(f'{slow[band]:.1f}x' if band in slow else '-'):>16}"
                     f"{(f'{statistics.median(tests):.0f} s' if tests else '-'):>22}")
    lines.append(f"constant work: {' and '.join(CONSTANT)} take the same effort every run; 1.0x is their median in the "
                 f"quietest band seen ({band_label(quietest, cores)}).")
    busy = [b for b in sorted(slow) if slow[b] >= 2.0]
    if busy:
        lines.append(f"saturation: from {band_label(busy[0], cores)} the same work took {slow[busy[0]]:.1f}x as long. "
                     "More parallel work past that point slows everything; keep the night limit at or under it.")
    elif len(slow) > 1:
        lines.append(f"no saturation seen: the busiest band ({band_label(max(slow), cores)}) ran the same work at "
                     f"{slow[max(slow)]:.1f}x. The night limit can stay or go up.")
    else:
        lines.append("one load band only: not enough spread to judge the night limit yet.")
    return "\n".join(lines)
