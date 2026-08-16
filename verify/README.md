# verify/

The known-good numbers of `AGENTS.md`, made runnable.

**This is not a test suite.** No pytest, no framework, no CI, no fixtures and no mocking, and
`01_setup.ps1` does not call any of it. These are plain scripts that drive the shipped `lib/`
functions against the live containers and print `PASS` or `FAIL` per fact. The sibling repository has
the same folder with the same six scenarios, so a number that changes on one side can be checked on
the other.

## Why this folder exists

`AGENTS.md` says *"Reproduce these rather than inventing a new check"* and then gives the numbers as
prose. Three things follow from that, and all three have happened:

- **The checks get rewritten every session, differently.** Whether a run is comparable to the last one
  becomes a matter of reading two transcripts.
- **The checks have bugs, and a throwaway check takes its bugs with it.** The bugs found while building
  this folder each read as a defect in the repository for a few minutes.
- **A recorded number can stop being true without anyone noticing.** Prose cannot fail; a script can.

## Running it

Everything needs the containers up — `start_demo.ps1`, or `04_docker_compose.sh` if you are an agent
and must not sit in an interactive shell.

```
python verify/invoke_verify.py                          # everything, ten to fifteen minutes
python verify/invoke_verify.py --only 06                # one scenario
python verify/invoke_verify.py --report-folder C:\tmp\v # a report file per script
```

A single script runs on its own and takes the same option:

```
python verify/02_stackexchange.py --report-path C:\tmp\stackexchange.txt
```

**Set `PYTHONIOENCODING=utf-8` if you redirect the output.** The console is `cp1252` and the sample
data is not ASCII — a StackExchange display name is `ypercubeᵀᴹ`. These scripts do not configure
logging, so the `lib/` messages are dropped and a run prints only its own `PASS`/`FAIL` lines. Call
`configure_logging` from `demo/` if you need to see what a function did.

**Why a report file exists at all:** a caller that redirects stdout may see nothing until the process
exits. `--report-path` writes with `buffering=1`, which matters for the two scripts that take minutes.

## What each script covers

| Script | Reproduces | Notes |
| --- | --- | --- |
| `01_timesheets.py` | 94 rows from three `Department*.xlsx`, 3 departments, 4 people | Seconds. SQL Server only. |
| `02_stackexchange.py` | `Users.xml` 12220 rows, 12179 with real milliseconds, 0 of 12220 differing on either timestamp column on all three providers with no tolerance | Minutes, mostly Oracle. Also covers `column_map` through Badges. |
| `03_geodata.py` | `countries.geojson` 14643643 bytes / 258 features, PostGIS 258/258 with 0 invalid | Minutes. The Oracle read-back is reported, **not** asserted — see below. |
| `04_photoservice.py` | 24 images, 43.5 MB, byte-identical by MD5 and length; the transfer's first pass carrying the backlog | Needs the shop running. |
| `05_projectstatus.py` | 9 rows → 8 after the heading → 4 rejected for 4 named reasons → 5 land after the colour retry → 3 handed back | Seconds. The only fully deterministic scenario. |
| `06_eventstreaming.py` | The five `kfk` functions, `auto.offset.reset` three ways, one application generation on the topic, whole-millisecond timestamps, and the replay compared to PostgreSQL column by column | **Stops and starts the shop** — see below. |

## Four rules these scripts follow

**Drive the shipped function, do not reimplement it.** The point is to exercise `lib/`. Where a
notebook's own helper is re-expressed — the row import in 05, the transfer body in 04 — it is because
the original is narration in a cell rather than a function, and the comment says so.

**Assert the preconditions, or the comparison measures nothing.** Every value comparison here is
preceded by a check that there was something to compare: that 12179 of 12220 `LastAccessDate` values
really do carry milliseconds, that no photo is `None` before the MD5s are taken, that payment uuids
were actually compared so the fold was doing work. **Before adding a `fact()`, ask what it would print
if the thing under test were absent.**

**Fold the column names.** PostgreSQL folds unquoted names to lower case and Oracle to upper, so one
query text comes back with three key spellings. PowerShell hides this because its property access is
case-insensitive, and a Python dict does not. `02_stackexchange.py` has a `lower_keys` helper for
exactly this.

**Do not assert a number nobody measured.** Two cases in particular:

- **Oracle's `SDO_UTIL.TO_WKTGEOMETRY` is non-deterministic on purpose.** It fails for a varying
  subset of the same 258 rows — seen at 26, 31, 39, 40, 42 and 64, and two consecutive runs have given
  26 and 64. `DIFFERENCES.md` lists four rejected explanations. `03_geodata.py` prints the count and
  asserts only that the failure is not total.
- **The PhotoService transfer timings depend on how long the shop has been running.** `04` asserts the
  shape and prints the milliseconds.

## What they change

They create `Verify_*` tables and drop them again. Beyond that:

- `02_stackexchange.py` uses the shipped `Users` and `Badges` tables rather than copies, because the
  `DATETIME2(3)` and `TIMESTAMP(3)` column types are part of what is being checked, and truncates them
  at the end.
- `04_photoservice.py` loads the images into the PostgreSQL `photo` table, which is what scenario 4's
  first section does.
- **`06_eventstreaming.py` stops the shop and starts it again.** Freezing the source is the only way
  to compare a replay against PostgreSQL without the two moving apart underneath. Starting it again
  truncates its tables and empties the topic, so scenarios 4 and 6 need their usual two minutes
  afterwards.

## Adding to it

One file per scenario, numbered to match `demo/NN_<name>.ipynb`. `verify_common.py` holds the helpers
and should stay the only shared module. Its `add_repository_paths()` resolves `lib/` and `demo/` from
`__file__` rather than from the working directory, which is the one deliberate difference from the
notebooks' `sys.path.append(str(Path("../lib").resolve()))` — a verify script may be started from
anywhere.

None of it follows the `lib/` function contract; that contract is for `lib/`, and these are runnable
scripts. `ruff` covers this folder like any other.
