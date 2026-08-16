"""Runs every verify script and prints one summary line each.

Each script is started as its own process, because they end in complete_verify(), which calls
sys.exit() - importing them would end this one at the first summary.

The whole run takes something like ten to fifteen minutes, most of it Oracle: 12220 rows in
02_stackexchange and 258 geometries one at a time in 03_geodata.
"""

import argparse
import subprocess
import sys
import time
from pathlib import Path

parser = argparse.ArgumentParser()
# A substring of the script name, so --only 06 or --only kafka runs just that one
parser.add_argument("--only")
# Where the per-script reports go. Each gets <name>.txt, written with buffering=1 so that a long run
# can be watched from another window.
parser.add_argument("--report-folder")
args = parser.parse_args()

here = Path(__file__).resolve().parent
scripts = sorted(p for p in here.glob("[0-9][0-9]_*.py"))

# lib_grid.py is named rather than globbed, because it is not a scenario and so has no number - the
# glob above is deliberately only the NN_ files that pair with demo/NN_*.ipynb. It runs last and takes
# seconds. See verify/README.md.
scripts.append(here / "lib_grid.py")

if args.only:
    scripts = [p for p in scripts if args.only in p.name]

if not scripts:
    print(f"No verify script matches [{args.only}]")
    sys.exit(1)

if args.report_folder:
    Path(args.report_folder).mkdir(parents=True, exist_ok=True)

results = []
for script in scripts:
    print(f"\n################ {script.name} ################", flush=True)

    command = [sys.executable, str(script)]
    if args.report_folder:
        command += ["--report-path", str(Path(args.report_folder) / (script.stem + ".txt"))]

    started = time.time()
    completed = subprocess.run(command)
    results.append((script.name, completed.returncode == 0, int(time.time() - started)))

print("\n################ summary ################")
for name, passed, seconds in results:
    print(f"{'PASS' if passed else 'FAIL'}  {name:<28} {seconds:>5} s")

failed = [r for r in results if not r[1]]
print()
if failed:
    print(f"{len(failed)} of {len(results)} verify scripts reported a failure")
    sys.exit(1)
print(f"all {len(results)} verify scripts passed")
sys.exit(0)
