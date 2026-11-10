"""Runs the regression suites of Wanderer CAD without opening Blender.

    pip install bpy numpy
    python scripts/run_tests.py              # every suite
    python scripts/run_tests.py prec undo    # only the suites whose name contains one of these words
    python scripts/run_tests.py -j 4         # 4 suites at a time
    python scripts/run_tests.py --bench      # also prints the per-mouse-move timings (t_rt)

Each suite runs in its own Python process with Blender's `bpy` module, drives the tools with simulated mouse and
keyboard events and measures the result (coordinates, volumes, undo / redo states, timings).
The add-on source tested is wanderer_cad/__init__.py (or the file named by the WANDERER_SRC environment variable).
Exit code 0 when every suite passes.
"""
import concurrent.futures
import os
import re
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TESTS = os.path.join(ROOT, "tests")
LIBS = {"harness.py", "prec_lib.py", "undo_lib.py", "t_one.py"}
BENCH = {"t_rt.py"}
VARIANTS = {"t_stressvar.py": ("units", "imperial", "xform", "persp", "cplane", "heavy")}
FAIL_LINE = re.compile(r"^(BAD|EXC|FAIL|NOUNDO|UNDO≠|REDO≠|SUIVI|FUITE|Traceback)")
COUNTS = re.compile(r"'(undo_bad|redo_bad|exc|follow|noundo)': (\d+)")


def verdict(rc, out):
    """(passed, short reason, summary line)."""
    lines = out.splitlines()
    bad = [ln for ln in lines if FAIL_LINE.match(ln)]
    last = ""
    for ln in lines:
        if "RESULTAT" in ln or "exceptions:" in ln or ln.strip() == "TOUT OK":
            last = ln.strip()
        for a, b in re.findall(r"RESULTAT[^\d]*(\d+) / (\d+)", ln):
            if a != b:
                bad.append(ln)
        if "RESULTAT" in ln and "ECHEC" in ln:
            bad.append(ln)
        for _k, n in COUNTS.findall(ln) if "RESULTAT" in ln else ():
            if int(n):
                bad.append(ln)
        mm = re.search(r"exceptions: (\d+)", ln)
        if mm and int(mm.group(1)):
            bad.append(ln)
    if rc != 0:
        return False, f"exit code {rc}", last
    if bad:
        return False, bad[0][:160], last
    return True, "", last


def run(job):
    name, extra = job
    t0 = time.time()
    try:
        p = subprocess.run([sys.executable, os.path.join(TESTS, name), "x"] + list(extra), cwd=TESTS,
                           capture_output=True, text=True, timeout=1800)
        rc, out = p.returncode, p.stdout + "\n" + p.stderr
    except subprocess.TimeoutExpired:
        rc, out = -1, "Traceback: timeout"
    ok, why, last = verdict(rc, out)
    return name + (" " + " ".join(extra) if extra else ""), ok, why, last, time.time() - t0, out


def main(argv):
    jobs_n, words, bench, verbose = 2, [], False, False
    it = iter(argv)
    for a in it:
        if a == "-j":
            jobs_n = max(1, int(next(it)))
        elif a == "--bench":
            bench = True
        elif a == "-v":
            verbose = True
        else:
            words.append(a)
    try:
        import bpy  # noqa: F401
    except ImportError:
        print("Blender's Python module is missing:  pip install bpy numpy")
        return 2
    jobs = []
    for f in sorted(os.listdir(TESTS)):
        if not (f.startswith("t_") and f.endswith(".py")) or f in LIBS or (f in BENCH and not bench):
            continue
        if words and not any(w in f for w in words):
            continue
        for v in VARIANTS.get(f, (None,)):
            jobs.append((f, (v,) if v else ()))
    failed = 0
    t0 = time.time()
    with concurrent.futures.ThreadPoolExecutor(max_workers=jobs_n) as ex:
        for name, ok, why, last, dt, out in ex.map(run, jobs):
            failed += not ok
            print(f"{'PASS' if ok else 'FAIL'}  {name:28s} {dt:6.1f} s  {(why or last)[:110]}")
            if verbose or not ok:
                for ln in out.splitlines():
                    if FAIL_LINE.match(ln) or (verbose and ln.strip()):
                        print("      " + ln[:200])
            elif name.split()[0] in BENCH:
                for ln in out.splitlines():
                    if "ms" in ln:
                        print("      " + ln[:200])
    print(f"\n{len(jobs) - failed} / {len(jobs)} suites passed in {time.time() - t0:.0f} s")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
