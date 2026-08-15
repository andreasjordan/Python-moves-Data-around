# Python moves Data around

This repository provides infrastructure as code, sample data and demo code to show how Python can move data around. It is intended to show the strengths and possibilities of Python as an ETL tool.

This is the siblings project for [PowerShell moves Data around](https://github.com/andreasjordan/PowerShell-moves-Data-around). I will try to build the same functionality - only using Python instead of PowerShell.

I will present this at the [IT-Tage 2026 in Frankfurt](https://www.ittage.informatik-aktuell.de/programm) in my session [Einfach statt komplex: Datenbankintegration mit PowerShell und Python](https://www.ittage.informatik-aktuell.de/programm/2026/einfach-statt-komplex-datenbankintegration-mit-powershell-und-python.html).


## Setup the environment

Currently, I do it "quick and dirty".

I have installed Python 3.14.6 on my Windows 11 system, without using virtual environments. I will later use and document a cleaner setup.

The packages are installed by `01_setup.ps1`, which also runs `06_test_connections.py` on Windows —
everything else in the setup happens inside WSL2, but this is the side the notebooks run on. It is the
same command you would run by hand:

```
python -m pip install -r requirements-windows.txt
```

`requirements.txt` is the list both sides share; `requirements-windows.txt` includes it and adds
`notebook`, which only Windows needs. Nothing is pinned and there is no virtual environment.

I have installed the "SQL Server ODBC driver" using these links:
- https://learn.microsoft.com/sql/connect/odbc/
- https://go.microsoft.com/fwlink/?linkid=2358430

Oracle needs nothing of that kind: `oracledb` runs in "thin mode" and speaks the Oracle network
protocol itself, so there is no Oracle Instant Client to install.

I use VS Code to work with Jupyter Notebooks.



## Current state

This repository is a work in progress. The [PowerShell moves Data around](https://github.com/andreasjordan/PowerShell-moves-Data-around)
repository is being ported scenario by scenario:

| Part | State |
| --- | --- |
| Timesheets demo | Done, see `demo/01_timesheets.ipynb` |
| StackExchange demo | Done, see `demo/02_stackexchange.ipynb` |
| Geodata demo | Done, see `demo/03_geodata.ipynb` |
| PhotoService demo | Done, see `demo/04_photoservice.ipynb` |
| ProjectStatus demo | Done, see `demo/05_projectstatus.ipynb` |
| Event streaming demo | Done, see `demo/06_eventstreaming.ipynb` |
| `lib/` | Twenty-two functions, for SQL Server, Oracle, PostgreSQL, MongoDB and Kafka |
| Containers | Complete — every scenario's databases are created, the PhotoService application runs as a container of its own, and Redpanda serves the Kafka demo. |
| Setup steps | Ported to Python. Only `01_setup.ps1` is still PowerShell, because that is what Windows starts. |

Every scenario of the sibling repository is now ported, apart from the bonus sections listed under the
demos below.



## Supported data sources and targets

Working today:

- Microsoft SQL Server
- Oracle database
- PostgreSQL
- MongoDB
- Apache Kafka, served by Redpanda
- Microsoft Excel
- XML files

- GPX files, GeoJSON files
- JPEG files, as binary data in the database itself



## Repository layout

| Path | Content |
| --- | --- |
| `01_setup.ps1` … `06_test_connections.py` | The setup steps. `01_setup.ps1` runs all of them. |
| `07_check_ports.ps1` | Not a setup step. Checks whether Windows can reach the container ports, for when something cannot connect. |
| `start_demo.ps1` | Starts the containers and keeps them running. This is what you run before a demo. |
| `data/` | One directory per scenario for the sample data. The generated and downloaded files are not part of the repository. |
| `demo/` | The demo notebooks, plus the helper modules a notebook imports. |
| `docker/` | The compose file, the database init scripts and the PhotoService application. |
| `lib/` | The functions that do the actual work. See [lib/README.md](lib/README.md) for an overview. |



## Running the demos

The notebooks are **not meant to be executed as a whole**. They are meant to be opened in Visual Studio
Code and then run cell by cell, so that you can look at the data and the results at every step. The
markdown cells in between are the story.

The outputs are committed on purpose, so that you can read through a demo without setting up a single
container.

A notebook expects the working directory to be `demo/`, which is what VS Code and Jupyter do by
default. That is how `sys.path.append(str(Path("../lib").resolve()))` finds the functions in `lib/`.



## Demo scenarios

### Timesheets

- Setup: Excel files will be created from sample data
- Excel files will be read into a pandas DataFrame
- Three ways to insert a row are compared: building the statement as a string, bind variables, bulk insert
- The DataFrame will be written into a SQL Server database
- An Excel report with two charts will be created from data in the SQL Server database
- The report will be read back in

The Excel files are created by `05_sample_data_setup.py` from `data/timesheets/sample.json`.


### StackExchange

- Setup: XML files will be downloaded from archive.org/download/stackexchange
- The files are read line by line, because every row is valid XML on its own
- Data from the XML files will be imported into a SQL Server database
- The same files will be imported into a PostgreSQL database, which needs a different approach
- And into an Oracle database, which needs a third approach again
- Data will be streamed from table to table, in all nine directions between the three systems
- As a bonus, the same data goes into MongoDB, which has no schema to convert against at all

Compared to the PowerShell version, one thing is missing: a bonus section that streams the same data
into an Azure SQL Database, which needs Azure resources rather than a local container, so it is not
part of this demo as it stands.



### Geodata

- Setup: GPX files will be downloaded from berlin.de and michael-mueller-verlag.de, and a GeoJSON file from datahub.io
- The GPX files are read into a DataFrame of type, name and WKT geometry
- WKT is the common currency: no driver here can hand a geometry to a database, so the text goes in and the database builds the geometry in the `VALUES` clause
- The same data goes into SQL Server, PostgreSQL with PostGIS and Oracle Spatial
- Reading a geometry column back gives three different answers on the three systems, and only one of them is an error
- For more than a handful of rows: bulk load the text into a staging table, then convert with one `INSERT ... SELECT`
- As a bonus, GeoJSON goes straight into PostgreSQL and Oracle - SQL Server only speaks WKT

Compared to the PowerShell version this leaves out the "Mauttabelle" bonus, which downloads a German
toll table by scraping a government website for the newest zip file.

### PhotoService

- Setup: the photos are committed to the repository, and a container runs the shop that keeps inventing customers and orders
- Twenty-four JPEGs go into a `bytea` column in PostgreSQL, and on into `VARBINARY(MAX)` in SQL Server
- Binary data needs no conversion code at all - only a smaller `batch_size`, because the rows are megabytes rather than bytes
- Then the harder half: transferring only the rows that are new, while the application keeps writing
- Two queries against a moving source do not see the same database. Name the upper bound, or read both inside one transaction
- An id finds new rows; only a timestamp - or Change Data Capture - finds rows that changed after they were transferred
- This is the scenario that made `lib/` grow `commit=False`, because a transaction in Python belongs to the connection and cannot be passed to a function

Compared to the PowerShell version this leaves out the bonus that streams MongoDB documents into an
Azure SQL Database, which needs Azure. Replaying the application's own events into a target is not
missing — it has a demo of its own, below.

### ProjectStatus

- Setup: one Excel file will be generated from `sample.json`, filled in the way eight project managers would fill in a form
- The rules live in the table: a primary key, three CHECK constraints, a `VARCHAR(50)` and a `DATETIME2`
- `write_sql_table` refuses the whole thing — one statement, one answer, and nothing is imported
- So the rows go in one at a time, and `enable_exception` turns a printed `[ERROR]` into something the loop can catch
- Four rows are rejected for four different reasons: a date column with `Late july 2026` in it, a status longer than the column, a colour the constraint does not allow, and `unknown` where a percentage belongs
- The failures are collected with the database's own message and written back out to an Excel file
- Then the loop fixes what can be fixed without guessing — the constraint name comes back in the error, so a bad colour can be retried

This is the scenario where the data is *wrong*, which none of the first four are.

### Event streaming

- Setup: a Redpanda container serves the Kafka API, and the PhotoService application produces an event whenever something happens
- Starts with the outbox you may already have: `order_event`, a table written in the same transaction as the change itself
- Then the same events on a topic, and the three problems a log solves that a table does not: polling, deleting, and a second reader
- The replay loop turns events back into rows — three kinds are inserts, two are updates
- Run the consuming cell twice and the second run sees only what is new, because the offset moved. Nothing had to ask the target what it already had
- Then the part a database comparison cannot do: a reader with a new `group_id` gets the whole history and rebuilds the target from nothing
- Redpanda Console is at `http://127.0.0.1:8080`, there for the same reason pgAdmin is

**This is the only part of this repository that is not a port.** The sibling repository has no Kafka,
so for this one demo there is nothing to show side by side — everything else here has a PowerShell
counterpart.

## Infrastructure

The repository is designed for and tested on a Windows 11 system with 32 GB of RAM. WSL2 is configured
with Docker to run the databases inside containers. The container setup is taken over unchanged from the
sibling repository.

These containers are used: SQL Server 2025, Oracle Database Express Edition 21c, PostgreSQL with
PostGIS, pgAdmin, MongoDB, Redpanda with its console, and one running the PhotoService application.
The exact image versions are pinned in `docker/docker-compose.yaml`.

The PhotoService container is the shop that keeps inventing customers and orders. It is the source of
the data that the PhotoService and event streaming demos move, so both of those need it running — and
it staggers its work over the first twenty minutes, so give it a little time before expecting anything
to be there.

Two of the containers have a web interface:

- pgAdmin: http://127.0.0.1:5050/browser/
- Redpanda Console: http://127.0.0.1:8080

All accounts use the same password. As this is a demo environment that only runs locally, the password
is part of the repository. `docker/.env` is where it is configured for the containers themselves, and
`04_docker_compose.sh` reads it from there — but the `CREATE USER` statements in the init SQL still
have it as a literal, so changing `docker/.env` alone is not enough to change it everywhere.


### Sharing one WSL2 installation with the sibling repository

Both repositories are meant to live in the same WSL2 installation. Neither one names a distribution, so
both use the default — install Ubuntu once, then run `01_setup.ps1` in each repository. The second run
finds the ODBC driver, docker and 7-Zip already there and only does its own half. Expect Oracle's first
start twice, though, once per repository: the volumes belong to the stack, not to the machine.

`01_setup.ps1` **sets the machine up, it does not start a demo.** It stops the containers again at the
end, which is what makes running it in both repositories possible: the other setup would otherwise find
these containers holding every port it wants.

**Switching in either direction is handled for you.** Both repositories now end their setup with
`docker compose stop`, and both stop the other one's containers before starting their own — found by the
`com.docker.compose.project` label, so neither needs a file from the other. Nothing has to be stopped by
hand any more.

To demo, run `start_demo.ps1`. Both repositories publish the same ports, so only one stack can run at a
time, and `start_demo.ps1` stops the other one for you before starting its own. That is a stop and not
a `down`, so the volumes on both sides survive — switching back and forth costs a minute, not another
Oracle start.

Why it stops the other stack rather than letting the ports collide: both repositories use the same
ports, the same password *and* the same database names. A port conflict would at least be loud. Instead
the other stack answers every connection, so a demo started while the sibling is up does not fail — it
succeeds against the wrong volumes.

To see which stack is currently running:

```
wsl --user root docker compose ls
```

**One thing to plan the running order of a session around.** Switching restarts the PhotoService
container, which truncates its tables and restarts its twenty-minute schedule — so demos 4 and 6 are
empty for twenty minutes after every switch, on whichever side you switch to. Until that schedule is
shortened, put those two demos last on each side and switch only once.


### Install WSL2

I use the Ubuntu 24.04 image by running `wsl --install -d Ubuntu-24.04` in an elevated Command Prompt or
PowerShell on a current Windows 11 system. To start from scratch, you can remove Ubuntu by running
`wsl --unregister Ubuntu-24.04`. At the end of the installation, Ubuntu starts automatically, and you
are prompted to create a Unix user account. The username and password do not matter.


### Clone or download the repository

Open a non-elevated PowerShell and navigate to a folder of your choice. In this guide, I will use
`C:\tmp`.

```
if (-not (Test-Path -Path C:\tmp)) {
    $null = New-Item -Path C:\tmp -ItemType Directory
}
Set-Location -Path C:\tmp
```

If you have git installed, you can just clone the repository:

```
git clone https://github.com/andreasjordan/Python-moves-Data-around.git
```

Or you can download and extract the repository:

```
[Net.WebClient]::new().DownloadFile('https://github.com/andreasjordan/Python-moves-Data-around/archive/refs/heads/main.zip', "$PWD\Python-moves-Data-around.zip")
Expand-Archive -Path $PWD\Python-moves-Data-around.zip -DestinationPath $PWD
Rename-Item -Path $PWD\Python-moves-Data-around-main -NewName Python-moves-Data-around
Remove-Item -Path $PWD\Python-moves-Data-around.zip
```


### Start the installation

To run all setup steps, simply execute `01_setup.ps1` in a non-elevated PowerShell. It shells into WSL2
for most of them, and finishes on the Windows side:

| Step | Runs as | What it does |
| --- | --- | --- |
| `pip install -r requirements-windows.txt` | you, on Windows | The packages the notebooks need. First, because it is the only step that costs nothing when it fails |
| `02_wsl2_setup.sh` | root, in WSL2 | Microsoft ODBC Driver 18, Docker, 7-Zip, and pyenv with Python 3.14.6 |
| `03_python_setup.sh` | you, in WSL2 | `pip install -r requirements.txt` |
| `04_docker_compose.sh` | root, in WSL2 | Waits for the docker daemon, starts the containers, and waits until SQL Server, PostgreSQL, MongoDB and Oracle have created the demo databases |
| `05_sample_data_setup.py` | you, in WSL2 | Creates the Excel files from `sample.json` and downloads the StackExchange and Geodata samples. A download is skipped when its files are already there; `--force` fetches them again |
| `06_test_connections.py` | you, in WSL2 | Opens a connection to every database a ported demo uses |
| `06_test_connections.py` again | you, on Windows | Waits until Windows can reach the container ports, then runs the same check from the side that runs the demos |
| `docker compose stop` | root, in WSL2 | Stops the containers again. The setup is finished; `start_demo.ps1` is what starts a demo |

The first and last rows are not an afterthought. The notebooks run on the Windows Python, not on the
one in WSL2, so without them the setup can finish green while a notebook still fails on a missing
package or the missing ODBC driver. And the two runs of `06` do not prove the same thing: the one in
WSL2 reaches the containers over the WSL2 loopback, while the one on Windows goes through the port
forwarding that Windows sets up, which is the only path a notebook ever takes. Those forwards do not
all appear at the same moment, which is why the last step waits for them first — a connection refused
from Windows usually means the forward is not there yet, not that the database is down.

The last three rows all run on the Windows side, so the script holds WSL2 open with a background `wsl`
process while they do. Without it WSL2 shuts the distribution down a few seconds after its last command
finishes and takes every container with it, and the connection test then fails against databases that
are no longer running — with a socket error that reads exactly like the missing port forward above, and
is nothing of the kind. If you ever have to tell the two apart, the container log settles it; note that
it is in UTC while the script's output is local time.

A failure in the connection test from Windows does not stop the script before the stop below — the
script reports the failure once the containers are down, and `start_demo.ps1` brings them back in a
minute if you want to look into it.

Python is installed with pyenv, which compiles it from source, so step 2 takes several minutes. It is
installed for your user account and not for root, which is why the later steps do not use `--user root`.

The whole run takes about half an hour, nearly all of it Oracle starting for the first time. That is
the price of the volumes, and it is paid once per repository — see
[Sharing one WSL2 installation with the sibling repository](#sharing-one-wsl2-installation-with-the-sibling-repository)
if you are installing both.


### Start the demo

Execute `start_demo.ps1` in a non-elevated PowerShell. It starts the containers, waits until the
databases answer, and then sits in a WSL2 shell. **If you exit that shell, WSL2 shuts down and takes
the containers with it**, so leave the window open for as long as you are demoing.

This keeps all data. It is a start, not a reset — the volumes survive, so every table a demo wrote last
time is still there. One thing to expect in `docker compose logs sqlserver` afterwards: its init script
runs on every start and its `CREATE LOGIN` / `CREATE DATABASE` statements are unconditional, so the log
fills with "already exists" errors. They are harmless and the databases are fine.

Run this after a reboot too, and whenever you are switching back from the sibling repository — it stops
that repository's containers first, because both publish the same ports.


### Reset the containers

A demo leaves data behind, and the next run of the same demo may not like it. There are two levels of
reset, and the cheap one is usually the one you want.

Both commands below are run from the repository directory, and both need the containers to be up —
they talk to the docker daemon inside WSL2. If WSL2 has been shut down, run `start_demo.ps1` first,
because that is what starts the daemon.

**Just the PhotoService application.** This is what demos 4 and 6 need, and it costs seconds:

```
wsl --cd "$PWD\docker" --user root docker compose restart photoservice
```

The application truncates its own PostgreSQL tables and drops its MongoDB collection when it starts, so
this puts it back to nothing. It also restarts the clock: the first order is scheduled ten minutes
later, the first payment at fifteen, the first shipment at twenty. **Give it twenty minutes before
expecting demos 4 and 6 to be interesting** — inside that window the tables and the Kafka topic are
nearly empty, which looks broken and is not.

Note what this does *not* touch: the SQL Server tables those demos transfer data *into*. Those are the
demo's own output, and the notebooks clean up after themselves.

**Everything, back to how the setup left it:**

```
wsl --cd "$PWD\docker" --user root docker compose down -v
.\start_demo.ps1
```

`-v` is the whole point — it removes the named volumes, and that is what actually deletes the data.
Without it you get the restart described above. With it, every container starts empty and re-runs its
init scripts, so all five scenarios' databases are created again exactly as the setup made them.

This costs another Oracle start, so budget about fifteen minutes. It does not re-download the images.


### When something cannot connect

Execute `07_check_ports.ps1` in a second PowerShell window, while the other one sits in its WSL2
shell. For every published port it says whether Windows has a listener for it and whether a connection
gets through:

```
1433   SQL Server         CONNECT   listener on ::1 (wslrelay)
1521   Oracle             CONNECT   listener on ::1 (wslrelay)
...
```

`NO LISTENER` means Windows has not published that container port yet. The database is very probably
running and answering fine inside WSL2 — the forward is what is missing, and the usual answer is to
wait a little. This is worth knowing because a driver reports it as an error about the *database*: the
Oracle driver says `DPY-6005: cannot connect to database`, which sounds like Oracle refused, when in
fact nothing was listening on this side to refuse.

If every port connects and a demo still cannot reach a database, the network is not the problem — run
`06_test_connections.py`, which asks the drivers rather than the sockets.
