# Python moves Data around

This repository provides infrastructure as code, sample data and demo code to show how Python can move data around. It is intended to show the strengths and possibilities of Python as an ETL tool.

This is the siblings project for [PowerShell moves Data around](https://github.com/andreasjordan/PowerShell-moves-Data-around). I will try to build the same functionality - only using Python instead of PowerShell.

I will present this at the [IT-Tage 2026 in Frankfurt](https://www.ittage.informatik-aktuell.de/programm) in my session [Einfach statt komplex: Datenbankintegration mit PowerShell und Python](https://www.ittage.informatik-aktuell.de/programm/2026/einfach-statt-komplex-datenbankintegration-mit-powershell-und-python.html).


## Setup the environment

Currently, I do it "quick and dirty".

I have installed Python 3.14.6 on my Windows 11 system and also installed the needed modules with pip without using virtual environments. I will later use and document a cleaner setup.

```
python -m pip install pyodbc
pip install pandas openpyxl
pip install notebook
pip install "psycopg[binary]"
pip install oracledb
pip install pymongo
```

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
| `lib/` | Eighteen functions, for SQL Server, Oracle, PostgreSQL and MongoDB |
| Containers | Complete, all scenarios' databases are created. The PhotoService container is disabled until that scenario is ported. |
| Setup steps | Ported to Python. Only `01_setup.ps1` is still PowerShell, because that is what Windows starts. |

The remaining scenarios — PhotoService and ProjectStatus — are described in the sibling repository and
will follow.



## Supported data sources and targets

Working today:

- Microsoft SQL Server
- Oracle database
- PostgreSQL
- MongoDB
- Microsoft Excel
- XML files

- GPX files, GeoJSON files

Planned, in the order the scenarios will be ported:

- JPEG files

Deliberately not planned: **MinIO**. The sibling repository uploads the sample files to it and reads
them back, signing the requests by hand. That is not being ported — MinIO changed its licence, and
uploading and downloading files is a different subject from getting rows into and out of a database,
which is what this repository is about.



## Repository layout

| Path | Content |
| --- | --- |
| `01_setup.ps1` … `06_test_connections.py` | The setup steps. `01_setup.ps1` runs all of them. |
| `start_containers.ps1` | Restarts the containers after a reboot. |
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

Compared to the PowerShell version, two things are missing. The upload to and download from MinIO is
not being ported at all, for the reasons above. And the PowerShell demo has a bonus section that
streams the same data into an Azure SQL Database, which needs Azure resources rather than a local
container, so it is not part of this demo as it stands.



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

## Infrastructure

The repository is designed for and tested on a Windows 11 system with 32 GB of RAM. WSL2 is configured
with Docker to run the databases inside containers. The container setup is taken over unchanged from the
sibling repository.

These containers are used: SQL Server 2025, Oracle Database Express Edition 21c, PostgreSQL with
PostGIS, pgAdmin, MongoDB, MinIO, and one running the PhotoService application. The exact image versions
are pinned in `docker/docker-compose.yaml`.

The MinIO container still starts, because `docker/` was taken over from the sibling unchanged, but no
demo here uses it any more. The PhotoService container is commented out until its scenario is ported.

Two of the containers have a web interface:

- MinIO: http://127.0.0.1:9001/login
- pgAdmin: http://127.0.0.1:5050/browser/

All accounts use the same password, which is configured in `docker/.env`. As this is a demo environment
that only runs locally, the password is part of the repository.

Both repositories use the same host ports, so only one of them can have its containers running at a
time.


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
for each of them:

| Step | Runs as | What it does |
| --- | --- | --- |
| `02_wsl2_setup.sh` | root | Microsoft ODBC Driver 18, Docker, 7-Zip, and pyenv with Python 3.14.6 |
| `03_python_setup.sh` | you | `pip install pandas openpyxl pyodbc psycopg oracledb pymongo` |
| `04_docker_compose.sh` | root | Starts the containers and waits until SQL Server, PostgreSQL, MongoDB and Oracle have created the demo databases |
| `05_sample_data_setup.py` | you | Creates `data/timesheets/*.xlsx` from `sample.json` |
| `06_test_connections.py` | you | Opens a connection to every database a ported demo uses |

Python is installed with pyenv, which compiles it from source, so step 2 takes several minutes. It is
installed for your user account and not for root, which is why the later steps do not use `--user root`.

At the end, the script enters WSL2 to keep all Docker containers running. If you exit, WSL2 will shut
down along with all containers.


### Restart the docker containers

To restart the containers, simply execute `start_containers.ps1` in a non-elevated PowerShell.
