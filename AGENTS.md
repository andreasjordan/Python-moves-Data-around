# AGENTS.md

Instructions for AI coding agents working in this repository.

## What this repository is

A teaching and demo repository that accompanies talks and videos: infrastructure as code, sample data
and demo code showing how Python can move data around. It is deliberately **not production code**
(see `README.md`).

It is the sibling of [PowerShell moves Data around](https://github.com/andreasjordan/PowerShell-moves-Data-around),
and it was built by porting that repository scenario by scenario. The two are presented side by side in
one session, so **a Python function is expected to read like a recognisable translation of its
PowerShell counterpart, not like idiomatic-at-any-cost Python.** Where Python genuinely wants something
different — a DataFrame instead of an array of objects, a context manager instead of `finally` — that
difference is itself part of the talk and worth making visible.

**Prime directive:** optimize every change for *readability while being shown on a projector*, not for
robustness, genericity or production hardening. If a change makes the code shorter and clearer, it is
probably right. If it adds abstraction, indirection or defensive layers, it is probably wrong.

Two rules about writing things down:

- **When something is wrong in the sibling repository and you cannot reach it, append an entry to
  `SIBLING-FINDINGS.md`.** **If both repositories are open** — a VS Code workspace holding the two of
  them — fix it in place instead, and commit per repository. Say which of the two situations you are in
  before the first change on the other side.
- **When a design decision is made, append an entry to `DIFFERENCES.md`** — what the sibling does, what
  Python forced, the evidence, the decision, and what was rejected. That is the one place where the
  rejected alternatives are written down. Keep the scope: behaviour of a function belongs in
  `lib/README.md`, rules belong here, narration belongs in the notebooks.

## Current state — read this before assuming anything works

All six scenarios are complete and every scenario of the sibling is ported. What is left out is a short
list of bonus sections, each for a stated reason — see "What is not ported".

| Area | State |
| --- | --- |
| `demo/01_timesheets.ipynb` | Excel in, SQL Server, and an Excel report with two charts back out. |
| `demo/02_stackexchange.ipynb` | The XML files into SQL Server, PostgreSQL and Oracle, streaming table to table, and a MongoDB bonus section at the end. Complete apart from the sibling's Azure SQL bonus. |
| `demo/03_geodata.ipynb` | GPX and GeoJSON into SQL Server, PostgreSQL/PostGIS and Oracle Spatial, through WKT. Complete apart from the Mauttabelle bonus. **The `ORA-13199` counts near the end are not reproducible** — re-running prints different numbers, so the narration deliberately names no single count. |
| `demo/04_photoservice.ipynb` | JPEGs into PostgreSQL `bytea` and on into SQL Server `VARBINARY(MAX)`, then incremental transfers against the running application, transactions, and CDC. **The order counts are not reproducible** — the application keeps writing. |
| `demo/05_projectstatus.ipynb` | One Excel form into SQL Server, where four of the eight rows are rejected for four different reasons. **Reproducible**, unlike the other five — the sample data is fixed, so the narration quotes its counts. |
| `demo/06_eventstreaming.ipynb` | The outbox table, then the same events on a Kafka topic, offsets, and a replay that rebuilds the target from the log alone. **The counts are not reproducible** — the shop keeps producing. It no longer grows *across* runs: the application empties the topic when it starts. **Needs the application to have been running for about two minutes**, and the notebook says so at the top: before then the topic holds nothing but `Added customer` and every count is zero. A run inside that window looks broken and is not. |
| `lib/` | Twenty-three functions. The grid in `lib/README.md` says which cells are deliberately empty. |
| The charts in `Report.xlsx` | **Open, and parked on purpose.** The pie and bar chart that the last cells of `demo/01_timesheets.ipynb` create are correct but do not look good enough yet. Do not polish them as a side effect of another task — see below. |
| The setup chain | Ported to Python; `01_setup.ps1` is the only remaining PowerShell file, because it is what Windows starts. It **builds only** — it stops the containers again at the end, so it can be run in this repository and then in the sibling, in either order. |
| `06_test_connections.py` | One block per scenario and per provider. **Run twice by `01_setup.ps1`** — once inside WSL2 and once on Windows, because the notebooks run on the Windows interpreter and nothing else checks that one. |
| `docker/photoservice-app.py` | The shop that keeps inventing customers and orders, running as the `photoservice` service on a stock `python:3.13-slim` image. It mounts `lib/` and installs its drivers when the container starts. **It is the source of everything the second half of scenario 4 transfers and of every event demo 6 reads**, so both are empty unless it is running — and it staggers its work over the first two minutes: the first order at 60 s, the first payment at 90 s, the first shipment at 120 s. `docker compose restart photoservice` is the cheap reset: it truncates its PostgreSQL tables, drops its MongoDB collection, empties the Kafka topic and restarts that clock. Keep the schedule in step with the sibling's `photoservice-app.ps1`. |
| The outbox is a real transaction | `photoservice-app.py` writes the `UPDATE order_header` and the `INSERT INTO order_event` with `commit=False` and one `pg_connection.commit()` after both, for payments and for shipments. **Do not split them again** — the invariant is checked by `verify/06_eventstreaming.py`, in both directions and with a precondition that there were rows to compare. |
| The topic is emptied at startup | `remove_kfk_topic` is called next to the collection drop. The application restarts its ids at 1, so a topic that outlives the tables holds several customers with `id = 1` and demo 6's replay dies on a primary key violation. See the Kafka section of `DIFFERENCES.md`. |
| `/etc/localtime` is mounted read only | `created_at` and `updated_at` are naive local timestamps, and this image's `/etc/localtime` points at UTC, so without the mount the shop stores times two hours behind the wall clock. The sibling mounts the same file for the same reason — the two applications have to agree on what the column means. |
| `docker/` Redpanda | The `redpanda` service serves the Kafka API on `19092` from Windows and `redpanda:9092` on the compose network — it advertises both, and getting that wrong is the classic Kafka-in-Docker trap. `redpanda-console` is on `8080`, there for the same reason pgAdmin is. |
| `05_sample_data_setup.py` | Timesheets, the StackExchange download, the Geodata downloads and the ProjectStatus Excel. PhotoService needs no block — its photos are committed. |
| Oracle's first start | **About two minutes, not fifteen.** The image ships a prebuilt XE and starts it; there is no database-creation phase. The 15 minutes in `wait_for` is a timeout margin, not a measurement. Do not repeat a duration you have not measured. |

Do not "discover" these as new findings and do not fix them as a side effect of an unrelated task.

### The chart formatting in the Timesheets report

The charts are the one part of the Timesheets scenario that is not finished. They render and the
numbers are right, but the appearance has not been settled. When that is picked up, these are the
known approximations, so nobody has to work them out again:

- The sizes are guesses. The sibling passes pixels to `Export-Excel` (300x300 for the pie, 1000x300
  for the bar); openpyxl wants centimetres, so `height`/`width` are set to 10x10 and 26x10.
- The bar chart has about 25 dates as categories, which is where the axis labels get crowded.
- Neither chart has data labels, and the pie chart has no percentages.
- The sibling styles both blocks as an Excel table (`TableStyle Light18`) and uses `AutoSize`. Here the
  column widths are four hard-coded numbers and there is no table style at all.

The data layout is deliberate and should survive any restyling: both results share one worksheet, the
first 19 rows are left free for the charts, and the second block starts at column E. Reading a block
back needs `nrows`, because the two blocks have a different number of rows.

## What is not ported

Three bonus sections of the sibling, each left out for a reason. Do not treat them as a backlog.

- The **Azure SQL bonus** at the end of the sibling's `demo/02_stackexchange.ps1`, and the **MongoDB →
  Azure SQL JSON bonus** at the end of its `demo/04_photoservice.ps1`. Both need Azure resources, the
  `Az` module, a firewall rule and two environment variables, so neither is local. Nobody has decided
  whether they belong.
- The **Mauttabelle** bonus at the end of `demo/03_geodata.ps1`, which scrapes `balm.bund.de` for the
  newest zip file, unpacks it and reads a 137530-row Excel. It is the most realistic ETL in the sibling
  and also the most fragile — it breaks whenever that page changes — and the decision was to skip it
  rather than carry a scraper.

**MinIO is not a remaining step — it is gone**, for reasons recorded in `DIFFERENCES.md`. The container,
its init script and its policy files are deleted, there is no `mio` column in `lib/`, and the
user-facing documentation does not mention it. Do not offer to bring any of it back.

The sibling's `04_photoservice_transfer_01.ps1` loop also has no counterpart and does not need one: it
is the same transfer as the notebook, wrapped in a `while` loop to run unattended.

## The setup chain, and what is load-bearing in it

The setup runs Python **inside WSL2**, from a pyenv installation that belongs to the default user
(uid 1000), not to root. Two things follow, and both have bitten this repository:

- A script started by `01_setup.ps1` is **not interactive**, and `~/.bashrc` returns immediately when
  it is not. The pyenv initialisation therefore lives in `~/.profile`, and steps 05 and 06 are started
  with `bash -lc` so that a login shell reads it. Never move that initialisation back into `~/.bashrc`
  alone.
- Steps that need Python must **not** run `--user root`. `/root` is `drwx------`, so root's home is
  invisible to the user that owns the pyenv installation.

`04_docker_compose.sh` does not return until the demo databases exist. Four things in it exist because
the failure each one prevents is silent or misleading. Do not simplify them away.

**It waits for the demo databases, not for the server.** `06_test_connections.py` used to fail with an
`08001` handshake error because it ran about four seconds after `docker compose up`. All four databases
have their own wait. Oracle's is a shell function rather than a one-liner, because `sqlplus` takes its
query on stdin.

**Do not check the container log for the init script's "complete" message instead.** `docker logs`
keeps the output of earlier runs, so it matches immediately after a restart. Query `sys.databases`.

**It waits for the docker daemon first.** `02` starts it, but `01_setup.ps1` then runs `wsl --shutdown`,
and `start_demo.ps1` runs after a reboot — so in both cases the daemon has to come up again, and it only
does because systemd starts it. That is a race right after WSL2 boots.

**`wait_for` gives up when the container has stopped**, instead of sitting out the full 5 or 15 minutes,
and the failure path prints `docker compose logs --tail 50`. The probe itself sends stderr to
`/dev/null` — it has to, because "the user does not exist yet" is the normal state for most of the wait
— so without that a failure explains nothing at all. A container killed by its `mem_limit` otherwise
looks exactly like one that is merely slow.

`04` also sources `docker/.env`, so the passwords in the probes are not another copy of the literal.
That file is valid shell as well as a Compose env file, which is why this works.

### The setup owns WSL2, not your machine

**The setup installs into WSL2 and into this repository's working tree. It installs nothing on the
host and changes no host configuration.** WSL2 itself, the Windows Python, the packages in
`requirements-windows.txt` and the Microsoft ODBC Driver 18 are the user's to install.

`00_check_host.ps1` is how that rule stays usable. It checks what the user has to provide, names
**every** missing piece at once with the command that installs it, and stops the setup. It changes
nothing, so it is safe to run at any time. This repository runs **nothing** on the host except that
check.

Four things worth knowing before touching it:

- **It has no dependencies, deliberately**, and it is PowerShell rather than Python for the same
  reason `01_setup.ps1` is: it runs before the Python side is known to work, and a missing `python`
  is one of the things it reports.
- **It follows the `-r requirements.txt` include** rather than reading the shared list separately, so
  `requirements-windows.txt` stays the one list for this side.
- **It normalises package names per PEP 503 and strips extras**, because `psycopg[binary]` is listed
  by pip as `psycopg`, and `confluent-kafka` and `confluent_kafka` are the same package.
- **It reads the ODBC driver out of the registry** rather than calling `Get-OdbcDriver`, because it
  imports nothing. The name it looks for is the one hard-coded in `lib/connect_sql_instance.py` and
  the two have to match. This is the one prerequisite pip cannot install.

**It checks the default WSL2 distribution by starting it and asking Linux a question**
(`wsl -e uname -r`), not by parsing `wsl --list --verbose`. That output is UTF-16LE on Windows and
reading it is a well known trap; an answer that comes from inside the distribution has no such
problem, and it proves the thing that matters — that a default distribution exists and starts.

**No minimum Python version is asserted.** The repository has never named one, and inventing a floor
would be a rule nobody has decided. The version is printed instead. What *is* checked is that `python`
answers at all: on Windows it is often the Microsoft Store stub, which is on the PATH and does nothing.

### Every step announces itself, and says what it cost

`Write-Step` in `01_setup.ps1` prints a banner before each step with the wall-clock time it started,
the slow ones say roughly how long they take, and each step is closed off with what it actually took.
The last line reports the total. This exists because **a quiet stretch is indistinguishable from a
hung script**: `04_docker_compose.sh` is silent for about two minutes while it waits for Oracle. The
Windows port wait prints one line per port for the same reason — a forward that lags the others by
minutes looks exactly like a hang.

The measured `took` lines exist because the estimates have been wrong: Oracle's first start was
written down as a quarter of an hour and is about two minutes. A run now reports its own timing
rather than leaving it to be remembered. Note that the durations are floored, not rounded — casting a
`TimeSpan`'s `TotalMinutes` with `[int]` rounds, so 59 seconds would print as `1:59`.

**The clock is local time and the container logs are UTC.** That difference is what makes a failure
here and the container log behind it look unrelated at a glance.

`02_wsl2_setup.sh` and `03_python_setup.sh` have the same idea in shell: a `step` function that echoes
one timestamped line per block, and a wrapper around the noisy command that sends **stdout** to
`/dev/null` and keeps **stderr**. So a failure still says why and `set -e` still stops the script,
while several hundred lines of progress nobody reads do not reach the terminal.

**The step lines are load-bearing rather than decoration.** Without them, quietening the command
would replace that output with a silent multi-minute stretch, which is the very thing the banners
exist to prevent.

In `02` it is `apt_get()`, and it is `apt-get` rather than `apt` throughout, because `apt` warns about
its unstable CLI on stderr — the stream being kept. In `03` it is `pip_install()`, which costs the
`Successfully installed …` line; `requirements.txt` is deliberately unpinned so that record was never
reproducible anyway, and `00_check_host.ps1` prints the versions on the Windows side.

**`03_pwsh_setup.ps1` in the sibling has no counterpart to this, and that is not drift.** It prints
one line per module it actually installs and nothing else — the `Import-*Library` functions log at
`Verbose`, which is suppressed. There is nothing there to silence.

**pyenv's own output is deliberately left alone.** Its installer clones four git repositories, which
is about thirty lines — but git writes progress to **stderr**, so the redirect used for apt would not
silence it anyway, and discarding stderr is the one thing that file does not do. `ACCEPT_EULA=Y` is
exported on its own line rather than prefixed to the call, because `apt_get` is a shell function and
a prefix would not reach the `apt-get` behind it.

**Do not quieten a failure path.** `04_docker_compose.sh` prints `docker compose logs --tail 50` when
a wait gives up precisely because a silent probe explains nothing, and that is the opposite trade
from this one.

### `01_setup.ps1` builds, `start_demo.ps1` runs

The two are deliberately separate, and the split is what lets **one WSL2 installation serve both
repositories**. Neither repository names a distribution — no `wsl` call anywhere passes `-d` — so both
use the default one.

- `01_setup.ps1` ends with `docker compose stop`. It builds the volumes, proves the connections from
  both sides, and leaves nothing running.
- `start_demo.ps1` starts a demo, holds the WSL2 shell open, and is what you run after a reboot or when
  switching repositories.
- `04_docker_compose.sh` **stops the sibling project's containers** before `docker compose up`, found by
  the `com.docker.compose.project` label so that no file from the other repository is needed. Both
  entry points call `04`, so both get it.

**Why stopping the other stack is not optional, and why a port conflict is the least of it.** Both
repositories publish the same ports *and* use the same password *and* create the same database names.
A bind error would at least be loud; instead the other stack answers every connection, so a run that
starts while the sibling's containers are up succeeds against the wrong volumes.

It is `docker stop`, never `down`: the other repository's volumes survive, so switching costs a minute
rather than another Oracle start. One cost of the split, known and not worth fixing: installing both
repositories pays for Oracle's first start twice, because the volumes are per compose project.

Switching also restarts the PhotoService container, which truncates its tables and restarts its clock,
so demos 4 and 6 are empty for the first two minutes afterwards.

**Nothing after `04` should abort `01_setup.ps1` before the stop.** The Windows `06` records its failure
in a variable and throws after the containers are down; anything added there should do the same.

**But something has to hold WSL2 open while a Windows-only step runs.** WSL2 terminates the distribution
a few seconds after its last process exits, and every container goes with it, so the Windows half of the
run — the port wait and `06_test_connections.py` — is covered by a background `wsl sleep` started before
it and stopped after `docker compose stop`. Do not remove it because the containers "are obviously still
running": that is the bug.

### The port forwarding arrives late, and not for all ports at once

**This looks exactly like a broken database.** On one clean install the Windows `06` connected to SQL
Server on 1433 twice and then failed on Oracle:

```
oracledb.exceptions.OperationalError: DPY-6005: cannot connect to database
[WinError 10061] ... da der Zielcomputer die Verbindung verweigerte
```

Seconds earlier the **same script had connected to the same Oracle database from inside WSL2**, and
`wait_for oracle` had already confirmed the demo user exists. `WinError 10061` is a refusal at connect
time: nothing was listening on the *Windows* side of the forward. Oracle never said no. Measured
afterwards with the containers still up: all seven ports had a `wslrelay` listener, every one accepted a
connection, and `06` passed from Windows end to end.

**Why one port lags the others is not established** — do not write down a mechanism for it without
evidence. Ruled out: there is no `.wslconfig`, no firewall rule for either port, no Hyper-V
excluded-port range covering 1433 or 1521, and no Windows process holding 1521.

`01_setup.ps1` therefore waits for all five database ports to accept a connection from Windows before it
runs `06` there. The wait is silent and costs 0.1 s when the forwards are already up.

Two things follow:

- **A single connection failure from Windows is not evidence that a container is broken.** Check
  whether Windows has a listener for that port first — and check the container log too, because a
  container that WSL2 idled out and a forward that has not appeared yet are indistinguishable from the
  driver's error message. The container log is in UTC while the script output is local time.
- **`07_check_ports.ps1` is the diagnostic.** For each published port it prints whether
  `Get-NetTCPConnection -State Listen` finds a listener and whether a TCP connect succeeds. Run it from
  a second PowerShell window. It is safe for an agent to run: it opens and closes TCP connections and
  starts nothing.

## Adding a dependency

`pip install` is on the deny list in `.claude/settings.json`, so an agent cannot install anything. The
owner has to. What an agent **can** and must do, in the same turn as the code that needs it:

**Add it to `requirements.txt`. That is the whole procedure.** `03_python_setup.sh` installs that file
inside WSL2, and `00_check_host.ps1` reads it — through the `-r` include in
`requirements-windows.txt` — to check the Windows side. Then tell the owner to re-run `01_setup.ps1`:
it installs the package inside WSL2 and names it as missing on Windows, with the `pip install` line
that fixes it.

`requirements-windows.txt` is `-r requirements.txt` plus `notebook`, and a package belongs in it only
if Windows needs it and WSL2 does not. `notebook` is the only one today, because no notebook is ever
run inside WSL2. Do not add anything else there without a reason of the same kind.

Do not wait to be asked.

**Nothing enumerates the packages except `requirements.txt`**: `README.md` prints the `pip install -r`
command rather than a list, and the `Loading model` section below points here. **Do not reintroduce a
second copy of the list anywhere**, however convenient it looks — two lists have drifted apart twice
already.

## The sample data on disk

`data/` holds the inputs for the scenarios. Everything generated or downloaded is gitignored, so a
fresh clone has only the `README.md` files, `sample.json` and the PhotoService photos.

`05_sample_data_setup.py` creates or downloads the rest. The Excel files are rebuilt from `sample.json`
every run, which costs a second. **The four downloads are skipped when the files are already there** —
about 15 MB from three sites, most of it `countries.geojson`. `python 05_sample_data_setup.py --force`
fetches them again.

The three Geodata artifacts are checked one at a time, so deleting one does not re-fetch the other two.
The StackExchange check is "are there any `*.xml`", which is coarse on purpose: a half-extracted archive
is not a state worth modelling in a setup script, and `--force` is the answer to it.

Two practical notes for an agent that needs the data present:

- `05` extracts the Berlin GPX archive with `7za`, which exists in WSL2. On Windows the equivalent is
  `C:\Program Files\7-Zip\7z.exe`, which is installed but not on the PATH. **This does not block
  running `05` on Windows** when the data is already there: every download is skipped and `7za` is
  never reached. With `--force`, or on a fresh clone, it is.
- A download that is cut off cannot leave a truncated file behind. `download()` writes to `<name>.part`,
  compares the size against `Content-Length` — all four hosts send it — and renames only then.
  `countries.geojson` should be **14643643 bytes / 258 features**, which is the quickest way to confirm
  the file by hand.

## Demo notebooks are stepped through, never run

A notebook is opened in VS Code and executed **cell by cell**, telling a story as it goes. The markdown
cells between the code are the narration.

- Never run a notebook, and never run "Run All".
- Never merge cells to make them run in one go, and never restructure one into a `.py` script.
- **The outputs are not committed.** Every notebook here is stored cleared: no `outputs`,
  `execution_count: null`. The reader runs it to see results, exactly as they must on the PowerShell
  side, which has never had output to look at. It also keeps the files short and every session starting
  from the same place. **So never commit a notebook with outputs in it.** If a run leaves them behind,
  clear them before committing.
- Cells that only put a variable name on the last line, imports repeated in a later cell, and code
  commented out on purpose (`os.startfile`, the `DROP TABLE`) are **pedagogical, not dead code**.
  Do not flag or remove them.

When you do change a notebook, edit the JSON minimally and touch only the cells the task is about. Do
not reformat the file — a whole-file rewrite loses the diff.

**If you do need to rewrite a notebook wholesale, match the file rather than a house style.** These
files are not all written the same way, and the differences are real: `json.dumps(nb, indent=1,
ensure_ascii=False)` reproduces them, but `01_timesheets.ipynb` has **no final newline**
(`.editorconfig` turns that off for `*.ipynb`) and `03_geodata.ipynb` is **CRLF**. Check that a round
trip reproduces the file byte for byte *before* writing anything; if it does not, stop rather than
normalise it.

### How to actually edit these notebooks

**The `Edit` tool refuses `.ipynb` outright**, and tells you to use `NotebookEdit`. So to change one
cell, use `NotebookEdit`, or a **raw exact-match replacement in Python**: read the file as text,
`assert raw.count(OLD) == 1`, replace, write back. Get `OLD` by printing the raw JSON slice around the
cell id first, so the escaping is exactly right. The assert is the safety rail — without it a near-miss
silently writes nothing or, worse, twice.

Do **not** load the JSON and re-dump it casually — see the byte-for-byte round-trip check above.

Adding cells to the *end* of a notebook, or building a new notebook, is fine with `Write` or a small
generator script. When inserting several cells with `NotebookEdit`, insert them in **reverse order** all
anchored to the same existing `cell_id`; you do not know the ids of cells you have not created yet.

Also: `Path.write_text` on Windows turns `\n` into `\r\n`, so a generated notebook lands with CRLF.
Git normalises it to LF on commit, so it does not matter — but do not go chasing the warning.

### The working rhythm for a notebook change

An agent cannot run a notebook, so a notebook change is finished in two steps and the second one is the
owner's:

1. Write or edit the cells. New cells have **no outputs** — never hand-write an output.
2. Say so, and stop. The owner steps through the notebook in VS Code to check that it still runs.

What still has to be checked by hand is the **narration**: a markdown cell that quotes a number the code
no longer produces is invisible, because there is no output next to it to contradict it.

Scripts that *are* meant to run: the numbered scripts in the repository root, `07_check_ports.ps1` and
`start_demo.ps1`. `demo/import_xls_timesheet.py` and `demo/import_gpx_file.py` only define a function
and are imported.

## Repository map

| Path | What it is |
| --- | --- |
| `00_check_host.ps1` | Checks that this machine has what the setup will not install: `python`, the packages in `requirements-windows.txt`, the Microsoft ODBC Driver 18, and a WSL2 default distribution with `apt-get`. Names every missing piece at once with the command that fixes it, and changes nothing. `01_setup.ps1` runs it first; it is also safe to run alone. |
| `01_setup.ps1` … `06_test_connections.py` | One-time setup, started from Windows, shells into WSL2. `01_setup.ps1` orchestrates the rest and stays PowerShell because Windows starts it; `02` and `03` are shell scripts, `05` and `06` are Python. It **builds only** — it stops the containers again at the end. |
| `07_check_ports.ps1` | **Not part of the setup sequence** — `01_setup.ps1` does not run it. A read-only diagnostic for when the Windows half cannot reach a database: per published port, whether Windows has a `wslrelay` listener and whether a connection gets through. |
| `requirements.txt`, `requirements-windows.txt` | The one list of Python packages, and the Windows-only addition to it. Nothing else enumerates the packages. |
| `start_demo.ps1` | Starts the demo: stops the sibling repository's containers, starts this repository's, and holds WSL2 open. `01_setup.ps1` builds, this runs. |
| `data/<scenario>/` | Sample data per scenario. Generated and downloaded artifacts are gitignored; only `README.md` and `sample.json` (plus the photos) are committed. |
| `demo/` | The notebooks, plus the helper modules a notebook imports. |
| `docker/` | `docker-compose.yaml`, the per-scenario database init SQL/sh/js, and the PhotoService application. |
| `lib/` | The data access layer. One function per file. |
| `verify/` | The known-good numbers as runnable scripts, one per scenario, plus `invoke_verify.py` and `verify_common.py`. Needs the containers up. **Not a test suite** — see `verify/README.md`. |
| `DIFFERENCES.md` | Why the port looks the way it does, including the rejected alternatives. |
| `SIBLING-FINDINGS.md` | The cross-repository work queue. Currently empty. |

## The lib/ naming grid

Every module is `<verb>_<prefix>_<noun>.py` and holds **exactly one public function of the same name**.
This mirrors the sibling's `<Verb>-<Prefix><Noun>` one-function-per-file layout, so the two can be shown
next to each other:

| PowerShell | Python |
| --- | --- |
| `lib/Connect-SqlInstance.ps1` → `Connect-SqlInstance` | `lib/connect_sql_instance.py` → `connect_sql_instance` |
| `lib/Write-PgTable.ps1` → `Write-PgTable` | `lib/write_pg_table.py` → `write_pg_table` |

The prefixes are `sql` (SQL Server), `ora` (Oracle), `pg` (PostgreSQL), `mdb` (MongoDB) and `kfk`
(Kafka). The sibling also has `mio` (MinIO), which is not ported. Helper functions that are not part of
the public surface are prefixed with `_` and live in the same file as their caller.

**There is exactly one exception, and it is deliberate:** each `get_*_data_reader` imports
`_prepare_query_and_params` from its own `invoke_*_query`, rather than carrying a fourth, fifth and
sixth copy of that regex. Do not "fix" it by copying the helper back, and do not generalise it into a
shared module either — the reasoning is in `DIFFERENCES.md`.

`lib/README.md` has the index of what exists and which cells of the grid are still empty.

**Sibling rule:** the `sql`, `ora` and `pg` implementations of a verb family are near-identical by
design. Before changing `lib/xxx_sql_yyy.py`, read `xxx_ora_yyy.py` and `xxx_pg_yyy.py`. Either apply
the same change to all siblings, or say explicitly why that provider has to differ. Unexplained
divergence between siblings is a bug. **This rule also reaches across repositories:** if the sibling
PowerShell function has a parameter, a guard clause or a `finally` block and the Python one does not,
that is a finding unless the difference is inherent to the language.

## Function contract

```python
def connect_sql_instance(
    instance,
    database=None,
    username=None,
    password=None,
    pooled_connection=False,
    enable_exception=False
):
```

- Plain functions. **No type hints, no dataclasses, no classes.** The sibling's parameter block is a
  `param()` with attributes; here it is a plain signature with defaults, and that comparison is easier
  to make when nothing else is in the way.
- `snake_case` parameters, one per line, keyword arguments at the call site. Positional calls into
  `lib/` are not used anywhere and should not start.
- Parameter names are the sibling's, lower-cased: `-Instance` → `instance`, `-BatchSize` →
  `batch_size`, `-TruncateTable` → `truncate_table`.
- **Every function ends its parameter list with `enable_exception=False`**, the port of
  `[switch]$EnableException`. It is the only error-handling switch in the library:

  ```python
  except Exception as e:
      message = f"<Step> failed: {str(e)}"
      if enable_exception:
          raise Exception(message)
      else:
          print(f"[ERROR] {message}")
          return None
  ```

  The `return None` matters — without it execution continues into code that assumes the failed step
  worked. A function that raises unconditionally, or that has no `enable_exception` at all, does not
  meet the contract.
- **Messages go through the stdlib `logging` module**, which is the counterpart of the sibling's
  PSFramework. Every file opens with

  ```python
  logger = logging.getLogger("lib." + __name__)
  ```

  The `"lib."` prefix is load-bearing: there is no package here, so `__name__` is bare
  (`write_sql_table`) and there would otherwise be no common parent to configure. It gives one
  handle for the whole library, and keeps psycopg, pymongo and confluent-kafka from logging their
  own internals into the same file.

  Three levels, and the split is deliberate:

  | Level | What | Counterpart |
  | --- | --- | --- |
  | `logger.debug` | the running commentary — opening a connection, creating a cursor, truncating | `Write-PSFMessage -Level Verbose` |
  | `logger.info` | bulk-load progress and the line that says it finished | `Write-Progress -Id 1`, which the audience sees |
  | `logger.error` | the failure path of the `enable_exception` contract | `Stop-PSFFunction` |

  **Nothing in `lib/` calls `print()`.** Notebooks print whatever reads well, and the setup and
  verify scripts print their own progress — that is the counterpart of `-Level Host`.

  `demo/configure_logging.py` is what a notebook calls to see any of it. Without it the messages
  are dropped, which is why the `06_test_connections.py` and `verify/` output is quiet.
- **No emoji in `lib/`.** `demo/import_xls_timesheet.py` prints `📄` and `↳`; that is fine in Jupyter,
  which is UTF-8, but the same code raises `UnicodeEncodeError` in a `cp1252` Windows console.
- Cursors, readers and files are closed on every path — `try/finally`, or a `with` block where the
  driver supports it.
- Long-running bulk operations print progress per batch: rows done, percentage, rows/sec.
- Runnable scripts do not swallow errors; an exception should stop the script.

## Loading model

There is **no package, no `__init__.py`, no `setup.py`/`pyproject.toml` — that is deliberate**, so the
audience sees plain functions in plain files. `lib/` is put on `sys.path` and the functions are imported
by name, which is the closest thing Python has to the sibling's dot-sourcing:

```python
import sys
from pathlib import Path

sys.path.append(str(Path("../lib").resolve()))

from connect_sql_instance import connect_sql_instance
from invoke_sql_query import invoke_sql_query
from write_sql_table import write_sql_table
```

The relative `../lib` means a notebook only resolves it correctly when the working directory is `demo/`,
which is what VS Code and Jupyter do. Modules that live next to the notebook (`import_xls_timesheet`)
are imported directly, without the `sys.path` dance.

Runtime dependencies are in `requirements.txt`, which is the only place they are listed — see
`Adding a dependency` above. They are installed with plain `pip` into whatever interpreter is there;
there is **no virtual environment**, which `README.md` calls "quick and dirty", and adding one is a
separate decision nobody has taken.

Two things pip cannot do, and both matter. SQL Server needs the
[Microsoft ODBC Driver 18](https://learn.microsoft.com/sql/connect/odbc/) — the driver name is
hard-coded in `connect_sql_instance.py`, `02_wsl2_setup.sh` installs it inside WSL2, and on Windows it
is a manual step in `README.md`. Oracle and PostgreSQL need nothing of the kind: `oracledb` runs in
thin mode and speaks the Oracle protocol itself, so there is no Instant Client.

## Deliberate decisions — do not "fix" these

- The password `Passw0rd!` is hard-coded in `docker/.env`, the init SQL, the notebooks and the setup
  scripts. These are throwaway local containers and the password being visible is part of the teaching.
  It is not a security finding. Do not parameterize it, do not move it to a vault, do not add
  `python-dotenv`.
- **`docker/.env` is not the single source of it, and the README says so.** The `CREATE USER`
  statements in the init SQL still hold it as a literal — deliberately, because making those
  interpolate needs an entrypoint that rewrites SQL, and a visible `CREATE USER … 'Passw0rd!'` on a
  slide says what it does.
- `127.0.0.1` rather than `localhost`, to force IPv4.
- `TrustServerCertificate=yes` in the connection string — local containers with self-signed
  certificates.
- **The shop stores local time**, and the `/etc/localtime` mount is what makes that true. UTC would be
  the better default anywhere else; here the demo is read off a wall clock, and an order placed at
  18:23 that pgAdmin shows as 16:23 costs a minute of explaining that has nothing to do with moving
  data. Do not remove the mount, and do not replace it with a `TZ` variable.
- **SQLAlchemy and ORMs are deliberately not used.** Hand-written DB-API code *is* the demo, exactly as
  the sibling uses hand-written ADO.NET rather than dbatools. Never propose replacing it. `pandas` is
  fine — it is the data container, not the database layer — but `pandas.read_sql` /
  `DataFrame.to_sql` hide the very thing being demonstrated.
- No tests, no CI, no packaging, no type hints, no docstring standard.
- Cleared notebook outputs, see above.

## Verifying a change

The containers are probably not running, and starting them costs a WSL2 boot and several minutes.

**Whether an agent may drive the lab is a per-machine decision**, because it depends on whether that
WSL2 installation is disposable. It is recorded in `.claude/settings.local.json`, which is **not**
committed — do not put it in the shared `settings.json`, which would grant it on the machine of
everyone who clones this repository. **If your `settings.local.json` does not grant it, the containers
are off limits** — verify statically and say so, rather than starting anything.

Three limits remain, and the first one holds on every machine:

- **Never execute a notebook.** `jupyter`, `nbconvert` and `nbclient` are denied in the *shared*
  `settings.json`, and "Run All" is never the answer. The notebooks are committed with their outputs
  cleared and must stay that way. Lab access does not loosen this in the slightest.
- **`wsl --unregister` needs the owner**, because putting the distribution back needs an elevated
  session.
- **`docker compose down -v` needs asking first.** It costs about two minutes, not the quarter of an
  hour it is sometimes assumed to — the Oracle image ships a prebuilt database. So the cost is not
  time, it is **whatever state somebody has not saved**: a notebook half stepped through, photos loaded
  into PostgreSQL by scenario 4. Ask, and say what will go. `docker compose stop` is the right thing
  for merely switching repositories.

  One consequence worth taking advantage of: the init SQL under `docker/` only runs on empty volumes,
  so **editing it and rebuilding beats writing a migration**.

**Hold WSL2 open before you start anything, and keep holding it.** WSL2 terminates the distribution a
few seconds after its last process exits, and every container goes with it — so a stack started by one
tool call is gone before the next one runs. Start a detached keepalive first and leave it running:

```powershell
$p = Start-Process -FilePath wsl -ArgumentList 'sleep', '36000' -PassThru -WindowStyle Hidden
```

**Do not run `start_demo.ps1` itself.** Its last line is an interactive `wsl` shell whose only job is to
be that keepalive, and it will hang a non-interactive session. Run `04_docker_compose.sh` directly — it
is the part that does the work:

```powershell
wsl --cd $repositoryRoot --user root ./04_docker_compose.sh
```

`07_check_ports.ps1` is safe at any time and is the quickest way to find out whether the containers are
up at all. Static checks are worth running first, because they cost nothing:

```bash
# Syntax check — works with nothing installed beyond Python
python -m compileall -q lib demo

# Style and rule check — needs `pip install ruff` first
python -m ruff check .

# Notebook still parses as a notebook
python -c "import json,sys; nb=json.load(open(sys.argv[1],encoding='utf-8')); print(len(nb['cells']),'cells')" demo/01_timesheets.ipynb
```

Read-only inspection (`docker ps`, `docker compose logs`, `git`) is fine. Note that `docker` lives
inside WSL2 and is **not** on the Windows PATH, so reaching it would mean running `wsl` — ask the owner
about container state instead of starting anything.

`ruff` is a development tool, not a runtime dependency: it is **not** in `requirements.txt` and
`01_setup.ps1` should not start installing it. If a machine reports `No module named ruff`, that is the
expected state until somebody runs `pip install ruff`; say so rather than reporting the check as
passing.

**Run it from the repository root.** `ruff check .` with the working directory somewhere else, or with
an absolute path as the target, stops the `[lint.per-file-ignores]` globs from matching — `demo/*.ipynb`
is relative — and the notebooks then report dozens of `E501`s that are deliberately ignored. The count
jumping into the tens is the symptom.

**The baseline is `All checks passed!` and exit 0.** Anything at all is new. That is the whole value of
the check being clean rather than nearly clean — nobody has to remember which findings are the expected
ones, and a real defect cannot hide in a list of tolerated noise.

So a new finding is one of two things: code that should change, or a decision that is not written down
yet. The `ignore` list in `ruff.toml` is long and every entry names the decision behind it — **do not
add a bare code to it.** An entry without a reason is worse than the finding it silences. When the
exemption belongs to one call site rather than to the repository, use `# noqa: <code>` there with the
reason above it, as `05_sample_data_setup.py` does for `S310`; a global ignore would also silence the
next occurrence, which is the one you would want to hear about.

**Set `PYTHONIOENCODING=utf-8` on anything that prints repository content.** The console is `cp1252`
and the sample data is not ASCII — a StackExchange display name is `ypercubeᵀᴹ`, `import_gpx_file`
prints `📄`. Without it an inspection script dies with `UnicodeEncodeError` partway through, which
looks like a broken notebook and is not one.

### But static checks are not enough

Every real defect found in `lib/` was found by **running Python against the live containers** — never by
reading the code. `compileall` was green every single time.

When the containers are up, drive the real `lib/` functions the way a notebook would. The pattern that
has paid off:

- Import from `lib/` and `demo/` via `sys.path`, exactly as a notebook does. Do not reimplement the
  logic in the test — the point is to exercise the shipped function.
- **Pass the repository root in as an argument.** The scratchpad is not inside the repository, so the
  obvious `while not (root / "lib").is_dir(): root = root.parent` never terminates — `Path("C:/").parent`
  is `Path("C:/")`, and the script spins at 100% CPU looking like a hung database connection.
- **Have the script write its own report file**, with `buffering=1`. PowerShell holds redirected output
  until the process exits, so `> file` shows nothing at all while a long run is in progress.
- Print `PASS`/`FAIL` per check and a summary at the end. Create and drop your own tables, and clean up.
- Run it in the background. A GeoJSON import or an Oracle round trip takes minutes.

**Compare values against the source, column by column. A row count is not a check.** The worst bug in
the port reported `OK - 12220 rows in 0.27 s` while silently discarding the milliseconds of every
timestamp. Checking `CreationDate` alone would have confirmed the bug as correct, because every value in
that column happens to end in `.000`. Only comparing `LastAccessDate` per row against the file exposed
it.

**And do not trust a passing check that could have got lucky.** `FETCH FIRST 3 ROWS ONLY` reported the
Oracle geometry read-back as working; over the whole table it fails for a fifth of the rows.

**Watch for a confound in your own script.** One round of measurements "proved" that
`oracledb.defaults.fetch_lobs = False` had no effect. It had reused the SQL text of the previous query,
so oracledb's statement cache served the old fetch metadata. Vary the SQL, or pass `stmtcachesize=0`.

**Before believing a `PASS`, ask what the check would print if the thing under test were absent.**
A check that compares failure *counts* while the membership moves, a check that compares MD5 hashes that
are `None` on both sides, and a check that asserts a row count copied out of this file rather than out of
the data all read as green. Assert the preconditions too — that the source is not `None`, that the column
has real values in it — or the comparison is measuring nothing.

If a change really cannot be verified — containers down, driver missing — say so plainly rather than
claiming it works.

### `verify/` is these numbers, made runnable — start there

The table below exists as scripts. **Run those instead of writing new ones**, and add to them rather
than starting again in the scratchpad:

```
python verify/invoke_verify.py            # all six, ten to fifteen minutes
python verify/invoke_verify.py --only 06  # one scenario
```

`verify/README.md` says what each script covers, what it changes, and why two numbers are printed
rather than asserted. It is **not** a test suite: no pytest, no CI, no fixtures, and `01_setup.ps1`
does not call it. The sibling has the same folder with the same six scenarios. A throwaway check takes
its bugs with it, which is the argument for the folder.

### Known-good numbers

Reproduce these rather than inventing a new check. Both repositories were driven through their own
shipped functions and agreed on every one:

| What | Number |
| --- | --- |
| `Users.xml` | 12220 rows; **12179** carry real milliseconds in `LastAccessDate`, while **all 12220** `CreationDate` values end in `.000` — which is why that column alone proves nothing |
| StackExchange import | 0 of 12220 differ on either timestamp column, on SQL Server, PostgreSQL and Oracle, **with no tolerance** |
| Timesheets | **94** rows from the three `Department*.xlsx`, 3 departments, 4 people — the same 94 as the sibling, although `-DataOnly` there and `dropna` here keep different intermediate counts |
| `countries.geojson` | 14643643 bytes, **258** features; PostGIS converts 258/258 with 0 invalid |
| Oracle `TO_WKTGEOMETRY` | non-deterministic on purpose — seen at 26, 31, 39, 40, 42 and 64 failures over the same 258 rows. **Do not "fix" this or write down a mechanism**; `DIFFERENCES.md` has four rejected explanations. `verify/03_geodata.py` prints the count and deliberately does not assert it |
| ProjectStatus | 9 rows after `dropna`, **8** after the `NEW PROJECTS:` heading is skipped, 4 rejected for 4 distinct reasons (`Late july 2026` in a `DATETIME2`, a 79-character `Status` against a `VARCHAR(50)`, `DarkRed` against the `Color` CHECK constraint, and `unknown` in an `INT`), 5 land after the colour retry, 3 handed back |
| PhotoService photos | **24** images, **43.5 MB** — and check they are not `None` first, because the `photo` rows exist with a `NULL` image until scenario 4's first section loads them |

## Style

Four-space indentation, double quotes, f-strings, `snake_case`. Blank line between logical steps inside
a function, with a short comment naming the step — the comments are read aloud during the demo:

```python
# Build connection string
conn_parts = [
    "DRIVER={ODBC Driver 18 for SQL Server}",
    f"SERVER={instance}"
]
```

DataFrames are the canonical in-memory shape for data in flight, the counterpart to the sibling's
`[PSCustomObject]` arrays. Prefer a single chained `assign(...)[[columns]]` over building a frame
column by column — it fits on a slide.

**Do not reformat lines you are not otherwise changing.** That is about wrapping, quoting and moving
code around, not about whitespace — every tracked file outside `data/` is clean of trailing whitespace,
and every one but the notebooks ends with a newline. `.editorconfig` sets `trim_trailing_whitespace` and
`insert_final_newline` to keep it that way, so a stray trailing space in a diff is something you
introduced.

The notebooks are exempt on purpose: `.editorconfig` turns **both** settings off for `*.ipynb`, because
Jupyter owns that file and writes it without a final newline. Ruff still checks the cells, though, so
trailing whitespace *inside* a cell is a finding and has to be removed by hand — with the raw
exact-match replacement described above, not by letting an editor reformat the file.

## Adding or porting a demo scenario

A scenario touches all of these. Miss one and the repository is inconsistent.

1. `data/<name>/README.md` and, if the data is generated, `data/<name>/sample.json`
2. The generated or downloaded artifact pattern in `.gitignore`
3. The scenario block in `05_sample_data_setup.py`, and the connection block in
   `06_test_connections.py`
4. `docker/sqlserver-<name>.sql` (and the Oracle/Postgres equivalent if used), plus the mount in
   `docker/docker-compose.yaml` and the line in `docker/sqlserver-init.sh`
5. `demo/NN_<name>.ipynb`, with markdown narration between the code cells
6. Any `lib/` function the scenario needs, following the naming grid and the function contract
7. The entry in `lib/README.md`
8. **The `### <Name>` section under "Demo scenarios" in `README.md`**
