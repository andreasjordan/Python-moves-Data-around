# SIBLING-FINDINGS.md

Things found in [PowerShell moves Data around](https://github.com/andreasjordan/PowerShell-moves-Data-around)
while porting it to Python. They were found here, they have to be fixed there.

Nothing in this file is a Python problem. For the design decisions of the port, see `DIFFERENCES.md`.

**This file lives in the Python repository**, so a session opened in the PowerShell repository will not
see it on its own. Point that session at this file, or copy it across.

Each entry says where the problem is, how to see it, and what to do. The **Here** line says whether the
Python repository — which inherited `docker/` verbatim — is already fixed, so the two do not drift
without anyone noticing.

---

## 1. Two PostgreSQL tables have no owner

**Where:** `docker/postgres-stackexchange.sql`

**What:** the file creates 18 tables and hands out 16 owners. `Posts` and `Import_Posts` are never
given to the `stackexchange` user, so they stay owned by `postgres`.

**Effect:** the demo user cannot read or write them at all — not `SELECT`, not `INSERT`, not even
`CREATE TABLE (LIKE Posts)`. It is latent because `demo/02_stackexchange.ps1` only imports `Users` and
`Badges`, so nothing has ever touched `Posts`. Any future step that does will fail with
`permission denied for table posts`.

**How to see it:**

```
docker compose exec postgres psql -U stackexchange -d stackexchange -c "SELECT COUNT(*) FROM Posts"
```

**Fix:** add the two missing lines, next to the ones that are already there:

```sql
ALTER TABLE Posts OWNER TO stackexchange;
ALTER TABLE Import_Posts OWNER TO stackexchange;
```

**Careful:** the init scripts of the postgres image only run on an empty data directory. The fix does
nothing until the `postgres` volume is removed and the container recreated.

**Here:** fixed.

---

## 2. A placeholder error message shipped in `Write-PgTable`

**Where:** `lib/Write-PgTable.ps1`, in the `-DataReader` branch

**What:**

```powershell
Stop-PSFFunction -Message "???? failed: $($_.Exception.Message)" -EnableException $EnableException
```

**Effect:** a failure while streaming a data reader into PostgreSQL reports `???? failed: <message>`.
It is cosmetic, but it is the message the user sees for the failure mode that is hardest to debug, and
it is the only placeholder of its kind in `lib/`.

**How to see it:** `grep -n '????' lib/*.ps1`

**Fix:** name the step the same way every other `Stop-PSFFunction` in the file does, for example
`"Inserting rows failed: ..."`.

**Here:** not applicable — `write_pg_table` has no data reader branch yet.

---

## 3. `Write-PgTable` does not use `COPY`

**Where:** `lib/Write-PgTable.ps1`

**What:** it fills a `DataTable` and lets an `NpgsqlDataAdapter` with an `NpgsqlCommandBuilder`
generate the `INSERT` statements. PostgreSQL's own bulk path, `COPY`, is not used.

**Effect:** slower than it needs to be. This is a long-standing wish on the PowerShell side rather
than a defect.

**Evidence from the Python port**, `Users.xml`, 12220 rows into the same table on the same container:

| Approach | Result |
| --- | --- |
| `executemany`, converted values | 1.27 s |
| `executemany`, raw strings | 0.95 s |
| `COPY`, converted values | 0.30 s |
| `COPY`, raw strings | 0.14 s |

**Fix:** Npgsql exposes `BeginTextImport` and `BeginBinaryImport`. The text variant is the closer
match to what `import_pg_table` does here — it writes the values as text and lets PostgreSQL parse
them into the column types, which removes the type handling entirely. The binary variant is faster
again but needs the correct .NET type per column.

**Worth checking while there:** escaping. In the Python port, 24 of the 4512 rows of `Comments.xml`
contain a tab, a newline or a backslash in `Text`, and they round-trip byte-exact. That is the test
case for any `COPY` implementation.

**Here:** `write_pg_table` and `import_pg_table` use `COPY`. See the entry in `DIFFERENCES.md`.

---

## 4. `04_docker_compose.sh` does not wait for the databases

**Where:** `04_docker_compose.sh`

**What:** it runs `docker compose up -d` and returns immediately. Nothing checks that SQL Server has
finished starting and created the demo databases.

**Effect:** none today, and that is the interesting part. `05_sample_data_setup.ps1` spends minutes
downloading the StackExchange archive and the geodata, which always gives the containers enough time.
The wait is accidental. Anything that makes `05` faster — caching the downloads, skipping files that
already exist, see finding 5 — reintroduces the race, and it surfaces in `06_test_connections.ps1` as
a connection failure that looks like a network problem.

**Evidence from the Python port:** the Python `05` finishes in about two seconds, and `06` then failed
with `08001 ... error was encountered during handshakes before login`, roughly four seconds after
`docker compose up`. Reproduced deliberately before it was fixed.

**Fix:** make `04` return only once the demo databases exist. See `04_docker_compose.sh` in the Python
repository for a working version.

**Do not** wait by grepping the container log for the init script's `SQL Server configuration complete.`
message. `docker logs` keeps the output of earlier runs, so on a restarted container it matches
immediately — measured at one second, while the server was still starting. It looks like a fix and
silently keeps the race. Query `sys.databases` instead.

**Here:** fixed, and extended to PostgreSQL.

---

## 5. The sample data is downloaded again on every run

**Where:** `05_sample_data_setup.ps1`, the StackExchange and Geodata blocks

**What:** every run downloads the archive from archive.org and the GPX and GeoJSON files again, then
unpacks them over the existing ones.

**Effect:** a repeated setup is far slower than it needs to be, and it is unfriendly to archive.org.

**Fix:** skip the download when the extracted files are already there, with a switch to force it.

**Careful:** this is what hides finding 4. Fix 4 first, or fix both together.

**Here:** the same behaviour — the Python `05` also downloads every time. Not fixed on either side.

---

## 6. Informational: the import loop depends on case-insensitive property access

**Where:** `lib/Import-SqlTable.ps1`, `Import-OraTable.ps1`, `Import-PgTable.ps1`

**What:** the loop reads `$rowObject.$sourceColumnName`, where `$sourceColumnName` comes from the
target table. Against PostgreSQL those names arrive lower cased, because the tables are created
unquoted and PostgreSQL folds them — while the XML attributes are `Id`, `AboutMe`, `CreationDate`.
It works only because PowerShell finds a property regardless of case.

**Not a defect.** It is recorded because it is invisible, and because it is exactly what broke the
Python port: of the fourteen columns of the PostgreSQL `Users` table, **zero** match an attribute of
`Users.xml` by exact name. A case-sensitive lookup fills every column with `NULL`, reports the right
number of rows and returns success.

**Worth doing:** a comment at that line, so the next person to touch it knows the case handling is
load-bearing.

**Here:** both import functions lower case the keys and the column names before matching.

---

## 7. `03_geodata.ps1` says 27 features, the file has 258

**Where:** `demo/03_geodata.ps1`, and `05_sample_data_setup.ps1`

**What:** the demo reads `countries.geojson` and comments the feature count as

```powershell
$geoJSON.features.Count  # 27 - only the EU
```

but the line in `05_sample_data_setup.ps1` that would reduce the download to the EU is **commented
out**:

```powershell
# $geoJSON.features = $geoJSON.features | Where-Object { $_.properties.'ISO3166-1-Alpha-3' -in 'AUT','BEL',... }
```

**Effect:** cosmetic, but it misleads whoever reads the demo. Whatever is downloaded today is the full
set. Measured in the Python port against the same URL, `https://datahub.io/core/geo-countries/r/0.geojson`:
14.6 MB, **258 features**, largest geometry 1.5 MB of JSON (Canada). The comment describes a filter that
is no longer applied.

**How to see it:** run the two lines. `27` never appears.

**Fix:** either restore the filter in `05`, or correct the comment. Worth deciding which, because it
also changes how long the import takes and how big the largest bind parameter is — the Python port
found a 4000 character Oracle limit hiding behind exactly that parameter.

**Here:** the Python `05` downloads the file unfiltered, and the notebook prints the real count instead
of asserting one.
