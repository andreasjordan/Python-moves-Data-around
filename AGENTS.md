# AGENTS.md

Instructions for AI coding agents working in this repository.

## What this repository is

A teaching and demo repository that accompanies talks and videos: infrastructure as code, sample data
and demo code showing how Python can move data around. It is deliberately **not production code**
(see `README.md`).

It is the sibling of [PowerShell moves Data around](https://github.com/andreasjordan/PowerShell-moves-Data-around),
and it is being built by porting that repository scenario by scenario. The two are presented side by
side in one session, so **a Python function is expected to read like a recognisable translation of its
PowerShell counterpart, not like idiomatic-at-any-cost Python.** Where Python genuinely wants something
different — a DataFrame instead of an array of objects, a context manager instead of `finally` — that
difference is itself part of the talk and worth making visible.

**Prime directive:** optimize every change for *readability while being shown on a projector*, not for
robustness, genericity or production hardening. If a change makes the code shorter and clearer, it is
probably right. If it adds abstraction, indirection or defensive layers, it is probably wrong.

## Current state — read this before assuming anything works

**Three scenarios are complete: Timesheets, StackExchange and Geodata.** StackExchange imports the
files into SQL Server, PostgreSQL, Oracle and MongoDB and streams between the three relational ones;
Geodata moves GPX and GeoJSON geometry into all three through WKT. MinIO was dropped on purpose and is
not coming — see `DIFFERENCES.md`.

**PhotoService is complete.** Binary JPEGs into PostgreSQL and on into SQL Server, incremental
transfers against the running application, transactions, and CDC. See "The PhotoService port" below.

**ProjectStatus is complete.** One Excel form into SQL Server, where four of the eight rows are
rejected and the scenario is about what you do next. It needed no new `lib/` function. See "The
ProjectStatus port" below.

**With that, every scenario of the sibling repository is ported.** What is left is a short list of
bonus sections that were each left out for a stated reason — see "What is left to port".

**And one thing here is no longer a port at all.** `demo/06_eventstreaming.ipynb`, the `kfk` column of
`lib/` and the Redpanda container have no counterpart in the sibling. They exist because dropping MinIO
had also dropped the event streaming story, which was collateral damage from a decision about object
storage. The events keep the sibling's `Add-LoggingEvent` shape and the replay loop is still a
translation of its loop, so the *section* is recovered rather than invented — but the two repositories
can no longer be shown side by side for it, because one side is empty. Recorded in `DIFFERENCES.md`
under Kafka. Stepped through end to end; the outputs are cleared before committing.

| Area | State |
| --- | --- |
| `demo/01_timesheets.ipynb` | Works, end to end, against a running SQL Server container. |
| `demo/02_stackexchange.ipynb` | Reading the XML files, importing them into SQL Server, PostgreSQL and Oracle, streaming table to table, and a MongoDB bonus section at the end. Stepped through end to end; the outputs are cleared before committing. Complete, apart from the sibling's Azure SQL bonus. |
| `demo/03_geodata.ipynb` | GPX and GeoJSON into SQL Server, PostgreSQL/PostGIS and Oracle Spatial, through WKT. Stepped through end to end; the outputs are cleared before committing. Complete apart from the Mauttabelle bonus, which was left out on purpose. **One caveat:** the `ORA-13199` counts near the end are not reproducible — re-running the notebook will print different numbers, so the narration deliberately names no single count. |
| `demo/04_photoservice.ipynb` | JPEGs into PostgreSQL `bytea` and on into SQL Server `VARBINARY(MAX)`, then incremental transfers against the running application, transactions, and CDC. Stepped through end to end; the outputs are cleared before committing. Complete, apart from the sibling's MinIO and Azure sections. **The order counts are not reproducible** — the application keeps writing, so every run prints different numbers, and no narration quotes one. |
| `demo/06_eventstreaming.ipynb` | The outbox table, then the same events on a Kafka topic, offsets, and a replay that rebuilds the target from the log alone. Stepped through end to end; the outputs are cleared before committing. Not a port — see above. **The counts are not reproducible** — the shop keeps producing, so the topic is bigger on every run. **Needs the application to have been running for about two minutes**, and the notebook says so at the top: the app truncates its tables at startup, so before then the topic holds nothing but `Added customer` and every count is zero. A run inside that window looks broken and is not. |
| `lib/` | Twenty-two functions: `connect`, `invoke`, `write`, `import` and `get_*_data_reader` for `sql`, `ora` and `pg`, `connect`, `write` and `read` for `mdb`, and two `connect`s plus `write` and `read` for `kfk`. The six `invoke_*_query` and `write_*_table` functions grew `commit=True` for PhotoService. |
| `demo/05_projectstatus.ipynb` | One Excel form into SQL Server, where four of the eight rows are rejected for four different reasons. Stepped through end to end; the outputs are cleared before committing. Complete. **Reproducible**, unlike the other four — the sample data is fixed, so the narration quotes its counts. |
| `docker/` | Complete. `sqlserver-projectstatus.sql` had been missing and was added, so all five scenarios' databases are created. `photoservice-app.ps1` has been replaced by `photoservice-app.py`. |
| The setup chain | Ported to Python, and **run start to finish against a clean install with no errors**, including the Windows half: the `pip install` that now opens the script and the second `06_test_connections.py` that closes it. `01_setup.ps1` is the only remaining PowerShell file, because it is what Windows starts. The Windows run failed the first time it existed, on a port-forwarding race — that is what added the wait in front of it, and the wait has now been through a clean run. Re-run after the build/run split below, and the `docker compose stop` that now ends `01_setup.ps1` works. **The two-repository flow has now been exercised in both directions** (2026-08-15): switching to this stack stopped all seven of the sibling's containers, switching back stopped all eight of these, both exiting 0. Both `06_test_connections.py` runs pass, inside WSL2 and on Windows. |
| The charts in `Report.xlsx` | **Open, and parked on purpose.** The pie and bar chart that the last cells of `demo/01_timesheets.ipynb` create are correct but do not look good enough yet. Do not polish them as a side effect of another task — see below. |
| `docker/photoservice-app.py` | The ported application, running as the `photoservice` service on a stock `python:3.13-slim` image. It mounts `lib/` and installs `pandas`, `psycopg[binary]`, `pymongo` and `confluent-kafka` when the container starts. It is the source of everything the second half of scenario 4 transfers **and of every event demo 6 reads**, so both are empty unless this container is running. `docker compose restart photoservice` is the cheap reset for those two demos — it truncates its own PostgreSQL tables, drops its MongoDB collection, and restarts the two-minute clock. Keep that schedule in step with the sibling's `photoservice-app.ps1`. See "Reset the containers" in `README.md`; a full `down -v` is almost never what is wanted here. |
| `docker/` Redpanda | The `redpanda` service serves the Kafka API on `19092` from Windows and `redpanda:9092` on the compose network — it advertises both, and getting that wrong is the classic Kafka-in-Docker trap. `redpanda-console` is on `8080`, there for the same reason pgAdmin is. |
| `05_sample_data_setup.py` | Timesheets, the StackExchange download, the Geodata downloads and the ProjectStatus Excel. PhotoService needs no block — its photos are committed. The sibling's upload of those files to MinIO has no counterpart and will not get one. |
| `06_test_connections.py` | Timesheets on SQL Server, StackExchange on SQL Server, Oracle, PostgreSQL and MongoDB, Geodata on SQL Server, Oracle and PostgreSQL, PhotoService on SQL Server, PostgreSQL and MongoDB, ProjectStatus on SQL Server. One block per scenario and per provider. **It is run twice by `01_setup.ps1`** — once inside WSL2 and once on Windows, because the notebooks run on the Windows interpreter and nothing else checks that one. Both runs pass on a clean install. |

Do not "discover" these as new findings and do not fix them as a side effect of an unrelated task.
They are known, and each one is a decision the repository owner has not made yet.

**When something is wrong in the sibling repository and you cannot reach it, append an entry to
`SIBLING-FINDINGS.md`** rather than fixing it there. That file is the work list for a session opened in
the PowerShell repository, and each entry records whether this repository — which inherited `docker/`
verbatim — is already fixed, so the two do not drift unnoticed.

**If both repositories are open** — a VS Code workspace holding the two of them, so the PowerShell
repository is a working directory and not just a path — then fix it in place instead, and commit per
repository. `SIBLING-FINDINGS.md` is then the queue for what is deliberately deferred, not a way of
routing work across a wall. Say which of the two situations you are in before the first change on the
other side.

**When a design decision is made, append an entry to `DIFFERENCES.md`** — what the sibling does, what
Python forced, the evidence, the decision, and what was rejected. That file is the record of *why* the
port looks the way it does, and it is the one place where the rejected alternatives are written down.
Keep the scope: behaviour of a function belongs in `lib/README.md`, rules belong here, narration
belongs in the notebooks.

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

The setup runs Python **inside WSL2**, from a pyenv installation that belongs to the default user
(uid 1000), not to root. Two things follow, and both have already bitten this repository once:

- A script started by `01_setup.ps1` is **not interactive**, and `~/.bashrc` returns immediately when
  it is not. The pyenv initialisation therefore lives in `~/.profile`, and steps 05 and 06 are started
  with `bash -lc` so that a login shell reads it. Never move that initialisation back into `~/.bashrc`
  alone.
- Steps that need Python must **not** run `--user root`. `/root` is `drwx------`, so root's home is
  invisible to the user that owns the pyenv installation.

`04_docker_compose.sh` does not return until SQL Server has created the demo databases. That wait is
load-bearing: `06_test_connections.py` used to fail with an `08001` handshake error because it ran
about four seconds after `docker compose up`. The sibling repository never noticed, because its `05`
spends minutes downloading sample data. Do not check the container log for the init script's
"complete" message instead — `docker logs` keeps the output of earlier runs, so it matches
immediately after a restart. All four databases have their own wait now. Oracle's is a shell
function rather than a one-liner, because `sqlplus` takes its query on stdin, and it gets 15 minutes
instead of 5, because Oracle takes far longer to start than the other two.

Three things around those waits are also load-bearing, and each one exists because the failure it
prevents is silent or misleading:

- **It waits for the docker daemon first.** `02` starts it, but `01_setup.ps1` then runs
  `wsl --shutdown`, and `start_demo.ps1` runs after a reboot — so in both cases the daemon has to
  come up again, and it only does because systemd starts it. That is a race right after WSL2 boots.
- **`wait_for` gives up when the container has stopped**, instead of sitting out the full 5 or 15
  minutes. A container killed by its `mem_limit` otherwise looks exactly like one that is merely slow.
- **The failure path prints `docker compose logs --tail 50`.** The probe itself sends stderr to
  `/dev/null` — it has to, because "the user does not exist yet" is the normal state for most of the
  wait — so without this a failure explains nothing at all.

`04` also sources `docker/.env`, so the passwords in the probes are not a fourth copy of the literal.
That file is valid shell as well as a Compose env file, which is why this works.

### `01_setup.ps1` builds, `start_demo.ps1` runs

The two are deliberately separate, and the split is what lets **one WSL2 installation serve both
repositories**. Neither repository names a distribution — no `wsl` call anywhere passes `-d` — so both
have always used the default one. What was missing was that the second setup to run had nowhere to put
its containers.

- `01_setup.ps1` ends with `docker compose stop`. It builds the volumes, proves the connections from
  both sides, and leaves nothing running. So it can be run in this repository and then in the sibling,
  in either order.
- `start_demo.ps1` is what starts a demo, holds the WSL2 shell open, and is what you run after a reboot
  or when switching repositories.
- `04_docker_compose.sh` **stops the sibling project's containers** before `docker compose up`, found by
  the `com.docker.compose.project` label so that no file from the other repository is needed. Both
  entry points call `04`, so both get it.

**Why stopping the other stack is not optional, and why a port conflict is the least of it.** Both
repositories publish the same ports *and* use the same password *and* create the same database names.
A bind error would at least be loud; instead the other stack answers every connection, so a run that
starts while the sibling's containers are up succeeds against the wrong volumes. On the sibling side
this is worse still — its `04` has no `set -e` and ends on `cd ..`, so a failed `docker compose up`
exits 0. Recorded as finding 14 in `SIBLING-FINDINGS.md`.

It is `docker stop`, never `down`: the other repository's volumes survive, so switching costs a minute
rather than another Oracle start.

**One cost of the split, known and not worth fixing:** installing both repositories pays for Oracle's
first start twice, because the volumes are per compose project.

Switching also restarts the PhotoService container, which truncates its tables and restarts its clock,
so demos 4 and 6 are empty for the first two minutes afterwards. That clock used to be twenty minutes,
which is what made switching expensive and what the old advice — put demos 4 and 6 last on each side
and switch only once — existed to work around. It was shortened on 2026-08-15 and the advice went with
it.

**Nothing after `04` should abort `01_setup.ps1`.** This used to be the most expensive rule in the
repository: the last line was the `wsl` shell that kept the containers alive, so a `throw` above it
idled WSL2 out and threw away twenty minutes of container startup. **The split defused that** — the
volumes now survive either way, and a `throw` only skips a tidy shutdown. The Windows `06` still
records its failure in a variable and throws after the stop, and anything added there should do the
same, but it is housekeeping now rather than a trap.

### The port forwarding arrives late, and it does not arrive for all ports at once

**This cost a full teardown once, and it looks exactly like a broken database.** On the first clean
install that ran the Windows `06`, it connected to SQL Server on 1433 twice and then failed on Oracle:

```
oracledb.exceptions.OperationalError: DPY-6005: cannot connect to database
[WinError 10061] ... da der Zielcomputer die Verbindung verweigerte
```

Seconds earlier the **same script had connected to the same Oracle database from inside WSL2**, and
`wait_for oracle` had already confirmed the demo user exists. `WinError 10061` is a refusal at connect
time: nothing was listening on the *Windows* side of the forward. Oracle never said no.

**Measured afterwards, with the containers still up:** all seven ports had a `wslrelay` listener on
`::1`, every one accepted a connection, and `06_test_connections.py` passed from Windows end to end
with exit 0 — same driver, same DSN, same everything. So the port forward for 1521 was simply not
there yet at the moment the check ran, while the other four were.

Ruled out on the way: there is no `.wslconfig` (so default NAT with `localhostForwarding`), no firewall
rule for either port, no Hyper-V excluded-port range covering 1433 or 1521, and no Windows process
holding 1521. **Why one port lags the others is not established** — do not write down a mechanism for
it without evidence.

**What was done about it:** `01_setup.ps1` waits for all five database ports to accept a connection
from Windows before it runs `06` there. That is the same idea as the waits in `04`, one boundary
further out — `04` waits for the databases inside WSL2, this waits for Windows to be able to see them.
The wait is silent and costs 0.1 s when the forwards are already up.

Two things follow for anything added here:

- **A single connection failure from Windows is not evidence that a container is broken.** Check
  whether Windows has a listener for that port first.
- **`07_check_ports.ps1` is the diagnostic that settled it**, and it is in the repository for that
  reason. For each published port it prints whether `Get-NetTCPConnection -State Listen` finds a
  listener and whether a TCP connect succeeds. Run it from a second PowerShell window while
  `start_demo.ps1` sits in its shell. It is safe for an agent to run: it opens
  and closes TCP connections and starts nothing.

## What is left to port

**All five scenarios are ported:** Timesheets, StackExchange, Geodata, PhotoService, ProjectStatus.
MinIO was dropped on purpose. There is no next scenario.

What is left is three bonus sections, each left out for a reason that is written down. Do not treat
them as a backlog — two of them need resources this repository does not have, and the third was a
judgement call.

### Also unported, and undecided

The **Azure SQL bonus** at the end of the sibling's `demo/02_stackexchange.ps1`. It streams a file and a
table into an Azure SQL Database, and needs Azure resources, the `Az` module, a firewall rule and two
environment variables — so it is not local. Nobody has decided whether it belongs. The **MongoDB → Azure
SQL JSON bonus** at the end of `demo/04_photoservice.ps1` is in the same position, for the same reason.

## The ProjectStatus port — finished

One Excel form into one SQL Server table, and the only scenario where the **data is wrong**. The first
four move data that already fits the target; this one is about what you do when four of the eight rows
do not.

**It needed no new `lib/` function and no change to an existing one** — `invoke_sql_query` with
`parameter_values` and `write_sql_table` covered it, which is what the notes here had predicted.

The shape of the demo, which is the sibling's: `write_sql_table` refuses the whole frame and imports
nothing; the rows then go in one at a time; `enable_exception` turns a printed `[ERROR]` into something
the loop can catch, so the failures can be named; the failures are collected with the database's own
message and written back out to an Excel file; and finally the loop retries the one failure it can fix
without guessing, recognising it by the constraint name that comes back in the error.

Four rows fail, for four different reasons, and it is worth knowing which so a changed run is
recognisable: `Late july 2026` in a `DATETIME2`, a `Status` of 79 characters against a `VARCHAR(50)`,
`DarkRed` against the `Color` CHECK constraint, and `unknown` in an `INT`. The colour is the one that
gets retried, so five rows end up in the table and three are handed back.

Two things Python forced, both in `DIFFERENCES.md`: a missing cell is `NaN`, a **float**, so it has to
become `None` before it is bound; and the bulk load fails in a different place than the sibling's, with
a byte-count message that names neither the column nor the row. The second one is left visible on
purpose — it makes the scenario's point better than a tidy message would.

Unlike the other four scenarios, **this one is reproducible**: the sample data is fixed, so the same
run produces the same numbers every time. The narration may quote them.

## The PhotoService port — finished

Binary JPEGs into PostgreSQL and on into SQL Server, then the harder half: transferring only what is
new while an application keeps writing to the source.

**It is the first scenario that needed a change to an existing `lib/` signature.** The six
`invoke_*_query` and `write_*_table` functions now take `commit=True`; with `commit=False` they neither
commit nor roll back, so several calls make up one unit of work. That is the port of the sibling's
`-Transaction`, which could not be ported as a parameter at all, and it is in `DIFFERENCES.md`. Before
it, every function in `lib/` committed unconditionally, so a transaction spanning two calls was
impossible. The three `get_*_data_reader` functions deliberately got nothing.

**The application is a container, and it is not optional.** `docker/photoservice-app.py` replaces the
sibling's `photoservice-app.ps1`, which was still PowerShell here and could never have run. It is the
source of every customer and order the second half of the notebook transfers, so **if that container is
not running, those cells have nothing to find.** It also needs a couple of minutes of runtime before the
notebook is interesting: the first order is scheduled 60 seconds after it starts, the first payment at
90, the first shipment at 120 — the sibling's schedule, kept, and shortened on both sides at once.

That schedule governs demo 6 as well, and more strictly, because that one reads the events rather than
the tables. Both demos want the container to have been up for about two minutes; restarting it resets
the clock **and** truncates the tables.

**Left out on purpose, and both follow from decisions already made:**

- The sibling's **MinIO logging bonus**, which loads the application's log archives into a `logging`
  table. It reads the bucket, so it went with the MinIO decision, and it is not coming back — it is a
  file-import demo and demo 2 already is one.
- The **MongoDB → Azure SQL JSON bonus**, which needs Azure.

The sibling's **"Transfer data from logging (or kafka)"** section is *not* in this list any more. It
went with MinIO too, and then came back as `demo/06_eventstreaming.ipynb` with Kafka underneath it
instead of a bucket.

**The `04_photoservice_transfer_01.ps1` loop of the sibling has no counterpart** and did not need one:
it is the same transfer as the notebook, wrapped in a `while` loop to run unattended.

## The Geodata port — finished, minus one bonus

GPX and GeoJSON into all three relational systems, through WKT. It needed **no new `lib/` function** —
`invoke_*_query` with `parameter_values` and `write_*_table` already covered it — but it did find three
real defects in functions the earlier scenarios had been using happily. All three are in
`DIFFERENCES.md`: the `::` operator being read as a named parameter, a failed statement leaving a
PostgreSQL connection unusable, and a missing `CLOB` declaration for bind parameters over 4000
characters.

`demo/import_gpx_file.py` is the only new module, next to `import_xls_timesheet.py`.

**Left out on purpose:** the sibling's **Mauttabelle** bonus, which scrapes
`balm.bund.de` for the newest zip file, unpacks it and reads a 137530-row Excel. It is the most
realistic ETL in the sibling and also the most fragile — it breaks whenever that page changes — and
the decision was to skip it rather than carry a scraper. If it is ever wanted, the sibling code is at
the end of `demo/03_geodata.ps1`.

## The StackExchange port — finished

The scenario was built in small steps, deliberately not in the order of the sibling's demo, so that
each step settled one design question: the sample data, reading the XML, the SQL Server import, the
PostgreSQL import, streaming table to table, Oracle, and MongoDB. All of it is done.

**MinIO is not a remaining step — it is gone.** It was dropped because MinIO changed its licence, and
because uploading and downloading files is not the question this repository asks. The full decision,
including what it costs, is in `DIFFERENCES.md`. The container, its init script and its policy files
have been deleted, the `mio` column has been removed from the grid in `lib/README.md`, and the
user-facing documentation no longer mentions it. Do not offer to bring any of it back.

The one part of the sibling's `demo/02_stackexchange.ps1` with no counterpart here is its **Azure SQL
Database bonus**, which streams a file and a table into an Azure SQL Database. That needs Azure
resources, the `Az` PowerShell module, a firewall rule and two environment variables, so it is not
local and not part of the demo as it is presented. It is unported, and nobody has decided whether it
should be.

## Adding a dependency

`pip install` is on the deny list in `.claude/settings.json`, so an agent cannot install anything. The
owner has to. What an agent **can** and must do, in the same turn as the code that needs it:

**Add it to `requirements.txt`. That is the whole procedure.** `03_python_setup.sh` installs that file
inside WSL2 and `01_setup.ps1` installs it on Windows, so both sides pick it up. Then tell the owner to
re-run `01_setup.ps1`, which is what actually installs it on both.

`requirements-windows.txt` is `-r requirements.txt` plus `notebook`, and a package belongs in it only
if Windows needs it and WSL2 does not. `notebook` is the only one today, because no notebook is ever
run inside WSL2. Do not add anything else there without a reason of the same kind.

Do not wait to be asked. The owner has had to prompt for this once ("You have not changed the
03_python_setup.sh - so I wait for that to change?") and it should not happen again.

**This used to be a four-step ritual across two `pip install` lines, `README.md` and this file, and it
failed twice** — `pymongo` and then `confluent-kafka` were each added to one side and not the other,
and each gap was closed only by an unrelated re-run of the setup. Nothing enumerates the packages any
more except `requirements.txt`: `README.md` prints the `pip install -r` command rather than a list, and
the `Loading model` section below points here. **Do not reintroduce a second copy of the list
anywhere**, however convenient it looks — that is the entire reason these files exist.

The Windows install is the **first** step of `01_setup.ps1`, before any WSL2 work. It is the only step
that costs nothing when it fails, and putting it last meant finding a broken Windows interpreter after
a quarter of an hour of Oracle starting up.

## The sample data on disk

`data/` holds the inputs for the scenarios. Everything generated or downloaded is gitignored, so a
fresh clone has only the `README.md` files, `sample.json` and the PhotoService photos.

`05_sample_data_setup.py` creates or downloads the rest. The Excel files are rebuilt from `sample.json`
every run, which costs a second. **The four downloads are skipped when the files are already there** —
about 15 MB from three sites, most of it `countries.geojson`. `python 05_sample_data_setup.py --force`
fetches them again. That was finding 5 in `SIBLING-FINDINGS.md`, fixed here and still open there.

The three Geodata artifacts are checked one at a time, so deleting one does not re-fetch the other two.
The StackExchange check is "are there any `*.xml`", which is coarse on purpose: a half-extracted archive
is not a state worth modelling in a setup script, and `--force` is the answer to it.

Two practical notes for an agent that needs the data present:

- `05` extracts the Berlin GPX archive with `7za`, which exists in WSL2. On Windows the equivalent is
  `C:\Program Files\7-Zip\7z.exe`, which is installed but not on the PATH. **This no longer blocks
  running `05` on Windows** when the data is already there: every download is skipped and `7za` is
  never reached. With `--force`, or on a fresh clone, it still is.
- A download that is cut off can no longer leave a truncated file behind. `download()` writes to
  `<name>.part`, compares the size against `Content-Length` — all four hosts send it — and renames only
  then. `countries.geojson` should be **14643643 bytes / 258 features**, which is still the quickest
  way to confirm the file by hand.

## Demo notebooks are stepped through, never run

`demo/01_timesheets.ipynb` is opened in VS Code and executed **cell by cell**, telling a story as it
goes. The markdown cells between the code are the narration.

- Never run the notebook, and never run "Run All".
- Never merge cells to make them run in one go, and never restructure it into a `.py` script.
- **The outputs are not committed, and that is deliberate as of 2026-08-15.** Every notebook here is
  stored cleared: no `outputs`, `execution_count: null`. The reader runs it to see results, exactly as
  they must on the PowerShell side, which has never had output to look at. It also keeps the files
  short and every session starting from the same place.
- **So never commit a notebook with outputs in it.** If a run leaves them behind, clear them before
  committing. This is the reverse of what this file said until 2026-08-15, and the reverse of what the
  older commits show.
- Cells that only put a variable name on the last line, imports repeated in a later cell, and code
  commented out on purpose (`os.startfile`, the `DROP TABLE`) are **pedagogical, not dead code**.
  Do not flag or remove them.

When you do change a notebook, edit the JSON minimally and touch only the cells the task is about. Do
not reformat the file — a whole-file rewrite loses the diff.

**If you do need to rewrite a notebook wholesale, match the file rather than a house style.** These
files are not all written the same way, and the differences are real: `json.dumps(nb, indent=1,
ensure_ascii=False)` reproduces them, but `01_timesheets.ipynb` has **no final newline** (`.editorconfig`
turns that off for `*.ipynb`) and `03_geodata.ipynb` is **CRLF**. Check that a round trip reproduces the
file byte for byte *before* writing anything; if it does not, stop rather than normalise it.

### How to actually edit these notebooks

Clearing the outputs took the whole set from 560 KB to 169 KB, and with that the worst of this problem
went away: `demo/03_geodata.ipynb` was about 26k tokens and refused by `Read`, and is now a fifth of
that. All six can be read directly.

One thing has not changed:

- **The `Edit` tool refuses `.ipynb` outright**, and tells you to use `NotebookEdit`.

So to change one cell, use `NotebookEdit`, or a **raw exact-match replacement in
Python**: read the file as text, `assert raw.count(OLD) == 1`, replace, write back. Get `OLD` by
printing the raw JSON slice around the cell id first, so the escaping is exactly right. The assert is
the safety rail — without it a near-miss silently writes nothing or, worse, twice.

Do **not** load the JSON and re-dump it casually. The right format is `indent=1, ensure_ascii=False`,
but two of these files carry their own conventions on top of that — see the byte-for-byte round-trip
check described above — and getting it wrong reformats the whole file and loses the diff.

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

Since the outputs are no longer committed, step 2 no longer produces anything to commit — the change is
complete once the cells are right, and the owner's run is a check rather than a second half. What still
has to be checked by hand is the **narration**: a markdown cell that quotes a number the code no longer
produces is now invisible, because there is no output next to it to contradict it. That has caught a
contradiction twice, and it was the committed outputs that made it catchable.

Scripts that *are* meant to run: the numbered scripts in the repository root (subject to the table
above), `07_check_ports.ps1` and `start_demo.ps1`. `demo/import_xls_timesheet.py` only defines a function and is
imported.

## Repository map

| Path | What it is |
| --- | --- |
| `01_setup.ps1` … `06_test_connections.py` | One-time setup, started from Windows, shells into WSL2. `01_setup.ps1` orchestrates the rest and stays PowerShell because Windows starts it; `02` and `03` are shell scripts, `05` and `06` are Python. It **builds only** — it stops the containers again at the end, so it can be run for both repositories in turn. |
| `07_check_ports.ps1` | **Not part of the setup sequence** — `01_setup.ps1` does not run it. A diagnostic for when the Windows half of the setup cannot reach a database: it prints, per published port, whether Windows has a `wslrelay` listener and whether a connection gets through. Read-only. |
| `requirements.txt`, `requirements-windows.txt` | The one list of Python packages, and the Windows-only addition to it. Both setup steps install from these; nothing else enumerates the packages. |
| `start_demo.ps1` | Starts the demo: stops the sibling repository's containers, starts this repository's, and holds WSL2 open. `01_setup.ps1` builds, this runs. |
| `data/<scenario>/` | Sample data per scenario. Generated and downloaded artifacts are gitignored; only `README.md` and `sample.json` (plus the photos) are committed. |
| `demo/` | The notebooks, plus the helper modules a notebook imports. |
| `docker/` | `docker-compose.yaml`, the per-scenario database init SQL/sh/js, and the PhotoService application. |
| `lib/` | The data access layer. One function per file. |

## The lib/ naming grid

Every module is `<verb>_<prefix>_<noun>.py` and holds **exactly one public function of the same name**.
This mirrors the sibling's `<Verb>-<Prefix><Noun>` one-function-per-file layout, so the two can be shown
next to each other:

| PowerShell | Python |
| --- | --- |
| `lib/Connect-SqlInstance.ps1` → `Connect-SqlInstance` | `lib/connect_sql_instance.py` → `connect_sql_instance` |
| `lib/Write-PgTable.ps1` → `Write-PgTable` | `lib/write_pg_table.py` → `write_pg_table` |

The prefixes are `sql` (SQL Server), `ora` (Oracle), `pg` (PostgreSQL), `mdb` (MongoDB) and `kfk`
(Kafka). The sibling also has `mio` (MinIO), which is not ported and is being removed there too.
Helper functions that are not part of the public surface are prefixed with `_` and live in the same
file as their caller.

**There is exactly one exception, and it is deliberate:** each `get_*_data_reader` imports
`_prepare_query_and_params` from its own `invoke_*_query`, rather than carrying a fourth, fifth and
sixth copy of that regex. Do not "fix" it by copying the helper back, and do not generalise it into a
shared module either — the reasoning is in `DIFFERENCES.md`.

`lib/README.md` has the index of what exists today and which cells of the grid are still empty.

**Sibling rule:** once a second provider exists, the `sql`, `ora` and `pg` implementations of a verb
family are near-identical by design. Before changing `lib/xxx_sql_yyy.py`, read `xxx_ora_yyy.py` and
`xxx_pg_yyy.py`. Either apply the same change to all siblings, or say explicitly why that provider has
to differ. Unexplained divergence between siblings is a bug. **This rule also reaches across
repositories:** if the sibling PowerShell function has a parameter, a guard clause or a `finally` block
and the Python one does not, that is a finding unless the difference is inherent to the language.

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
- Progress and diagnostics go through `print()` with a level tag, the stand-in for the sibling's
  `Write-PSFMessage`: `[VERBOSE]` inside `lib/`, `[ERROR]` on the failure path. Notebooks print
  whatever reads well. Do not introduce `logging` in `lib/` without being asked — there is a commented
  sketch at the bottom of `connect_sql_instance.py` and that decision is still open.
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
`Adding a dependency` above, and do not copy the list back into this file. They are installed with
plain `pip` into whatever interpreter is there; there is still **no virtual environment**, which
`README.md` calls "quick and dirty", and adding one is a separate decision nobody has taken.

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
- `127.0.0.1` rather than `localhost`, to force IPv4.
- `TrustServerCertificate=yes` in the connection string — local containers with self-signed
  certificates.
- **SQLAlchemy and ORMs are deliberately not used.** Hand-written DB-API code *is* the demo, exactly as
  the sibling uses hand-written ADO.NET rather than dbatools. Never propose replacing it. `pandas` is
  fine — it is the data container, not the database layer — but `pandas.read_sql` /
  `DataFrame.to_sql` hide the very thing being demonstrated.
- No tests, no CI, no packaging, no type hints, no docstring standard.
- Committed notebook outputs, see above.

## Verifying a change

The containers are probably not running, and starting them costs a WSL2 boot and several minutes.

**Whether an agent may drive the lab is a per-machine decision**, because it depends on whether that
WSL2 installation is disposable. It is recorded in `.claude/settings.local.json`, which is **not**
committed — do not put it in the shared `settings.json`, which would grant it on the machine of
everyone who clones this repository.

On the owner's machine it is granted: WSL2 serves only these two repositories and can be reinstalled,
so `wsl` and the setup scripts are allowed there. **If your `settings.local.json` does not grant it,
the containers are off limits** — verify statically and say so, rather than starting anything.

Three limits remain, and the first one holds on every machine:

- **Never execute a notebook.** `jupyter`, `nbconvert` and `nbclient` are denied in the *shared*
  `settings.json`, and "Run All" is never the answer. The outputs in `demo/*.ipynb` are committed on
  purpose and running the file replaces them. Lab access does not loosen this in the slightest.
- **`wsl --unregister` needs the owner**, because putting the distribution back needs an elevated
  session.
- **`docker compose down -v` is a twenty-minute mistake.** The `-v` deletes the volumes and getting
  them back means another Oracle start. `docker compose stop` keeps the data and costs a minute.

**Hold WSL2 open before you start anything, and keep holding it.** WSL2 terminates the distribution a
few seconds after its last process exits, and every container goes with it — so a stack started by one
tool call is gone before the next one runs. This is the same effect finding 16 in `SIBLING-FINDINGS.md`
describes, met from the other direction. Start a detached keepalive first and leave it running:

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
up at all. Static checks are still worth running first, because they cost nothing:

```bash
# Syntax check — works with nothing installed beyond Python
python -m compileall -q lib demo

# Style and rule check — needs `pip install ruff` first
python -m ruff check .

# Notebook still parses as a notebook, and the outputs are still there
python -c "import json,sys; nb=json.load(open(sys.argv[1],encoding='utf-8')); print(len(nb['cells']),'cells,',sum(len(c.get('outputs',[])) for c in nb['cells']),'outputs')" demo/01_timesheets.ipynb
```

Read-only inspection (`docker ps`, `docker compose logs`, `git`) is fine. Note that `docker` lives
inside WSL2 and is **not** on the Windows PATH, so reaching it would mean running `wsl` — ask the owner
about container state instead of starting anything.

`ruff` **is** installed in the Windows interpreter now (0.16.3, installed by hand on 2026-08-15). It is
not in `requirements.txt` and is not meant to be — it is a development tool, not a runtime dependency,
and `01_setup.ps1` should not start installing it. If a fresh machine reports `No module named ruff`,
that is the expected state until somebody runs `pip install ruff`; say so rather than reporting the
check as passing.

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

**Set `PYTHONIOENCODING=utf-8` on anything that prints notebook content.** The console is `cp1252` and
the committed outputs contain non-ASCII from the sample data — a StackExchange display name is
`ypercubeᵀᴹ`, `import_gpx_file` prints `📄`. Without it an inspection script dies with
`UnicodeEncodeError` partway through, which looks like a broken notebook and is not one. The `[VERBOSE]`
lines are also worth filtering out when reading a verification run; there are thousands of them.

### But static checks are not enough, and this is the lesson of the port so far

Every real defect found in `lib/` was found by **running Python against the live containers** — never by
reading the code. `compileall` was green every single time.

When the containers are up, write a throwaway script in the scratchpad directory that **drives the real
`lib/` functions the way a notebook would**, and run it. That is not on the forbidden list: it is
ordinary Python, it touches only demo tables, and it is the only thing that works. The pattern that has
paid off four times now:

- Import from `lib/` and `demo/` via `sys.path`, exactly as a notebook does. Do not reimplement the
  logic in the test — the point is to exercise the shipped function.
- **Pass the repository root in as an argument.** The scratchpad is not inside the repository, so the
  obvious `while not (root / "lib").is_dir(): root = root.parent` never terminates — `Path("C:/").parent`
  is `Path("C:/")`, and the script spins at 100% CPU looking like a hung database connection. That cost
  half an hour once.
- **Have the script write its own report file**, with `buffering=1`. PowerShell holds redirected output
  until the process exits, so `> file` shows nothing at all while a long run is in progress.
- Print `PASS`/`FAIL` per check and a summary at the end, so a partial failure is obvious.
- Create and drop your own tables, and clean up.
- Run it with `run_in_background: true`. A GeoJSON import or an Oracle round trip takes minutes.

**Compare values against the source, column by column. A row count is not a check.** This is how the
worst bug in the port was found and it is worth repeating: `import_ora_table` reported
`OK - 12220 rows in 0.27 s` while silently discarding the milliseconds of every timestamp. Checking
`CreationDate` alone would have confirmed the bug as correct, because every value in that column
happens to end in `.000`. Only comparing `LastAccessDate` per row against the file exposed it.

**And do not trust a passing check that could have got lucky.** `FETCH FIRST 3 ROWS ONLY` reported the
Oracle geometry read-back as working; over the whole table it fails for a fifth of the rows. Ask
whether the check could pass for the wrong reason.

**Watch for a confound in your own script.** One round of measurements "proved" that
`oracledb.defaults.fetch_lobs = False` had no effect. It had reused the SQL text of the previous query,
so oracledb's statement cache served the old fetch metadata. Vary the SQL, or pass `stmtcachesize=0`.

**Before believing a `PASS`, ask what the check would print if the thing under test were absent.**
Three checks passed for the wrong reason in a single session on 2026-08-15: one compared failure
*counts* while the membership moved underneath, one compared MD5 hashes that were `NULL` on both sides,
and one asserted a row count copied out of this file rather than out of the data. All three read as
green. Assert the preconditions too — that the source is non-`NULL`, that the column has real values in
it — or the comparison is measuring nothing.

If a change really cannot be verified — containers down, driver missing — say so plainly rather than
claiming it works.

### Known-good numbers, measured 2026-08-15 on both repositories

Reproduce these rather than inventing a new check. Both sides were driven through their own shipped
functions and agreed on every one:

| What | Number |
| --- | --- |
| `Users.xml` | 12220 rows; **12179** carry real milliseconds in `LastAccessDate`, while **all 12220** `CreationDate` values end in `.000` — which is why that column alone proves nothing |
| StackExchange import | 0 of 12220 differ on either timestamp column, on SQL Server, PostgreSQL and Oracle, **with no tolerance** since the `DATETIME2(3)` change |
| Timesheets | **94** rows from the three `Department*.xlsx`, 3 departments, 4 people — the same 94 as the sibling, although `-DataOnly` there and `dropna` here keep different intermediate counts |
| `countries.geojson` | 14643643 bytes, **258** features; PostGIS converts 258/258 with 0 invalid |
| Oracle `TO_WKTGEOMETRY` | non-deterministic on purpose — seen at 31, 39, 40, 42 and 64 failures over the same 258 rows. **Do not "fix" this or write down a mechanism**; `DIFFERENCES.md` has four rejected explanations |
| ProjectStatus | 9 rows after `dropna`, **8** after the `NEW PROJECTS:` heading is skipped, 4 rejected for 4 distinct reasons, 5 land after the colour retry, 3 handed back |
| PhotoService photos | **24** images, **43.5 MB** — and check they are not `NULL` first, because the `photo` rows exist with a `NULL` image until demo 4's first section loads them |

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
code around, not about whitespace — every tracked file outside `data/` is now clean of trailing
whitespace, and every one but the notebooks ends with a newline. `.editorconfig` sets
`trim_trailing_whitespace` and `insert_final_newline` to keep it that way, so a stray trailing space in
a diff is something you introduced.

The notebooks are exempt on purpose: `.editorconfig` turns **both** settings off for `*.ipynb`, because
Jupyter owns that file and writes it without a final newline. Ruff still checks the cells, though, so
trailing whitespace *inside* a cell is a finding and has to be removed by hand — with the raw
exact-match replacement described above, not by letting an editor reformat the file.

## Adding or porting a demo scenario

A scenario touches all of these. Miss one and the repository is inconsistent.

1. `data/<name>/README.md` and, if the data is generated, `data/<name>/sample.json`
2. The generated or downloaded artifact pattern in `.gitignore`
3. The scenario block in `05_sample_data_setup.py`, and the connection block in
   `06_test_connections.py` — the sibling's `05_sample_data_setup.ps1` still has the download and
   upload code for the scenarios that are not ported yet
4. `docker/sqlserver-<name>.sql` (and the Oracle/Postgres equivalent if used), plus the mount in
   `docker/docker-compose.yaml` and the line in `docker/sqlserver-init.sh` — for the ported scenarios
   these all already exist, since `docker/` came over complete
5. `demo/NN_<name>.ipynb`, with markdown narration between the code cells
6. Any `lib/` function the scenario needs, following the naming grid and the function contract
7. The entry in `lib/README.md`
8. **The `### <Name>` section under "Demo scenarios" in `README.md`**
