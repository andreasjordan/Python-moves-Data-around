# SIBLING-FINDINGS.md

Work for [PowerShell moves Data around](https://github.com/andreasjordan/PowerShell-moves-Data-around),
written down on this side. There are two kinds of entry:

- **Findings (1–8, 11–13)** — things found here that have to be fixed there. Nothing in them is a
  Python problem. 1–8 came out of porting the demos; 11–13 came out of reviewing the setup chain, so
  they are all in `01_setup.ps1`, `04_docker_compose.sh` and `docker/`.
- **Things to build there (9–10)** — where this repository has gone first and the PowerShell one is
  meant to follow. These are not defects; they are a plan.

For the design decisions of the port itself, see `DIFFERENCES.md`.

**This file lives in the Python repository**, so a session opened in the PowerShell repository will not
see it on its own. Point that session at this file, or copy it across.

Each finding says where the problem is, how to see it, and what to do. The **Here** line says whether
the Python repository — which inherited `docker/` verbatim — is already fixed, so the two do not drift
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

**Here:** **fixed.** Finding 4 was fixed first, so this was safe to do. `05_sample_data_setup.py` skips
each download when its files are already present, and `--force` fetches them again. Three things worth
copying when this is done there:

- **Check the three Geodata artifacts separately.** They come from three different sites; deleting one
  should not re-fetch the other two. The old code deleted all of them up front, which made a
  per-artifact check impossible without restructuring.
- **Download to `<name>.part` and rename only when the file is complete**, comparing the size against
  `Content-Length` first. All four hosts send it. This closes a second, quieter bug: a download cut off
  halfway used to leave a file that looks perfectly good and fails much later, inside demo 3, as a
  `JSONDecodeError` that says nothing about a download.
- **A coarse check is the right one here.** "Are there any `*.xml`" does not notice a half-extracted
  archive, and should not try to — `--force` is the answer to that, and a setup script that models
  partial states stops being readable.

A useful side effect: `05` now runs on Windows when the data is already there, because every download
is skipped and `7za` — which is not on the Windows PATH — is never reached.

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

## 8. `photoservice-app.ps1` writes an order event with no order

**Where:** `docker/photoservice-app.ps1`, the `NewPayment` and `NewShipment` blocks

**What:** both blocks pick the order to work on with a query that may legitimately return nothing:

```powershell
OrderId = Invoke-PgQuery -Query 'SELECT id FROM order_header WHERE payment_uuid IS NULL ORDER BY RANDOM() LIMIT 1' -As SingleValue
```

If every order has already been paid for — the payment loop runs once a second and can catch up with
the order loop, which also runs once a second — `$payment.OrderId` is `$null`. The code then carries on
regardless: the `UPDATE` matches no row, and the `INSERT INTO order_event` writes a row whose
`order_id` is `NULL`.

**Effect:** small but real. `order_event` accumulates rows that belong to no order, and any transfer or
join built on that table has to cope with them. The `NewShipment` block has the same hole.

**How to see it:** let the application run for a while and then

```sql
SELECT COUNT(*) FROM order_event WHERE order_id IS NULL;
```

**Fix:** skip the block when the query returns nothing — three lines, one per block.

**Here:** `docker/photoservice-app.py` guards both blocks with `if order_id is not None:`, with a
comment naming this finding.

---

# Things to build there

Not defects. This is where the Python repository went first and the PowerShell one is meant to follow,
so that the two can be shown side by side again.

## 9. Remove MinIO

**Where:** `lib/*-Mio*.ps1`, `docker/`, `05_sample_data_setup.ps1`, `demo/02_stackexchange.ps1`,
`demo/04_photoservice.ps1`, `docker/photoservice-app.ps1`

**What:** MinIO comes out of the sibling too, for the reasons already recorded in `DIFFERENCES.md`
here — it changed its licence, and uploading and downloading files is a different question from the one
every other provider in these repositories answers.

**What that touches:**

- The five functions: `Connect-MioInstance`, `Get-MioFile`, `Get-MioFileList`, `Set-MioFile`,
  `Remove-MioFile`.
- The `minio` service in `docker/docker-compose.yaml`, plus `minio-init.sh` and the two policy files.
- The upload block in `05_sample_data_setup.ps1`.
- The bucket sections at the end of `demo/02_stackexchange.ps1`.
- In `demo/04_photoservice.ps1`: *"Transfer data from logging (or kafka)"* and the
  *"Bonus: Import Logging from files on MinIO"* section. The first of those does **not** simply
  disappear — see entry 10, which is where it goes.
- `photoservice-app.ps1` writes its logging archive to the bucket. That has to become the Kafka
  producer of entry 10, or the application stops emitting events at all.

**Worth thinking about before deleting:** the hand-rolled AWS SigV4 signing in `Connect-MioInstance` is
the most interesting code in either repository, precisely because no SDK hides it. Deleting it removes
something genuinely good. Keeping it somewhere outside the demo — a gist, a blog post, an appendix — is
worth five minutes of thought before `git rm`.

**Here:** done, completely. No demo uses it, the user-facing documentation does not mention it, and the
`minio` service, `minio-init.sh`, both policy files and the `.env` block have been deleted. Only the
internal markdowns still discuss it, as the record of why. Use this side as the worked example of what
to remove.

## 10. Port the event streaming demo back

**Where:** new — the counterpart of `demo/06_eventstreaming.ipynb` and the `kfk` functions here

**What:** this repository now has a Kafka demo, served by Redpanda, and it is the only thing here with
no PowerShell counterpart. It exists because dropping MinIO also dropped the event streaming story,
which was collateral damage from a decision about object storage — and the sibling's own section title,
*"Transfer data from logging (or kafka)"*, says what the real answer always was.

**The good news, and it decides the approach:** the .NET client `Confluent.Kafka` wraps **librdkafka**,
which is the same C library the Python `confluent-kafka` package wraps. The two demos would therefore
be near-identical in shape rather than merely analogous — which is the whole point of these two
repositories.

Better still, the sibling already has the mechanism for this. `Import-PgLibrary` and `Import-OraLibrary`
download ADO.NET DLLs from nuget.org at runtime; **`Import-KfkLibrary` would follow that pattern
exactly**, with no new idea required.

**What to build, following the naming convention there:**

| Here | There |
| --- | --- |
| `connect_kfk_producer` | `Connect-KfkProducer` |
| `connect_kfk_consumer` | `Connect-KfkConsumer` |
| `write_kfk_topic` | `Write-KfkTopic` |
| `read_kfk_topic` | `Read-KfkTopic` |

Two connect functions rather than one, because Kafka has no single connection object — a producer and a
consumer are different clients. That is worth keeping on both sides.

Plus: the `redpanda` and `redpanda-console` services in `docker/docker-compose.yaml` (copy them from
here), the producer calls in `photoservice-app.ps1`, and a `demo/06_eventstreaming.ps1`.

**Four things learned the hard way here, all of which transfer:**

1. **Advertise two listeners.** The application container reaches the broker as `redpanda:9092` on the
   compose network; the demo reaches it from Windows as `127.0.0.1:19092`. A broker advertises the
   address a client should come back on, so it has to advertise both. Getting this wrong is the classic
   Kafka-in-Docker trap.
2. **Reading a live topic without a bound never returns.** A stopping rule of "n seconds with no new
   message" never fires while the shop is producing. Ask the broker for the high watermark and read
   exactly that many. This hung a kernel here, and interrupting a process that is inside librdkafka is
   unreliable — it had to be killed.
3. **`auto.offset.reset` only applies to a consumer group that has no committed offset.** There is no
   "start again" setting; starting again means a new group id. In a demo that gets re-run constantly
   this shows up as "the cell returned nothing the second time" rather than as an error.
4. **The application truncates its tables at startup and staggers its work over twenty minutes.** A
   demo run inside that window shows an empty topic and zero counts, and looks broken when it is not.

**Here:** done and shipped in `8b186bc`. The notebook has been stepped through end to end and its
outputs are committed, the four lessons above came out of that run, and the `kfk` functions are in
`lib/`. Nothing here is waiting on anything — this entry is now purely a work list for the other side.

---

## 11. The password is not configured in `docker/.env`

**Where:** `docker/sqlserver-init.sh`, and the sentence in `README.md` that says otherwise

**What:** `Passw0rd!` appears 22 times across 15 files in `docker/`. `.env` feeds four container
environment variables; everything else has it as a literal. `sqlserver-init.sh` is the clearest case —
it hard-codes the password six times inside a container that already has `MSSQL_SA_PASSWORD` in its
environment.

**Effect:** changing `docker/.env` does not change the password. It changes what SQL Server, Oracle,
PostgreSQL and MongoDB are started with, while every `CREATE USER` statement and every `sqlcmd` call
keeps the old one — so the setup breaks in places that look unrelated to what was edited. The README of
both repositories says the password "is configured in `docker/.env`", which is what makes this a trap
rather than a nuisance.

**Fix:** `-P "$MSSQL_SA_PASSWORD"` in `sqlserver-init.sh`. Leave the `CREATE USER` statements alone —
making those interpolate needs an entrypoint that rewrites SQL, and the visible literal is part of the
teaching. Then say in the README which files still hold it.

**Here:** fixed in `sqlserver-init.sh`, and `04_docker_compose.sh` sources `docker/.env` for its
probes rather than repeating the literal. The `CREATE USER` statements are unchanged on purpose and the
README now names them.

---

## 12. `06_test_connections.ps1` checks the wrong machine

**Where:** `01_setup.ps1`, the `06` step

**What:** every setup step is run inside WSL2, including the connection test. The demos are run from
Windows.

**Effect:** the setup can finish completely green while the machine that runs the demo cannot reach a
single database. Whatever `06` proves, it proves about an environment no demo ever uses. In this
repository the two runtimes had already drifted twice — `pymongo` and `confluent-kafka` were added to
the WSL2 install and to the Windows one at different times, by hand.

**Fix:** run `06` a second time from Windows at the end of `01_setup.ps1`. The script is the same one;
only the interpreter under it changes. Install the modules there in the same step, so the Windows list
stops being a prose block in the README that somebody has to remember.

**Here:** fixed. `01_setup.ps1` starts with a `pip install` on Windows and ends with a second
`06_test_connections.py` there.

Doing it produced a second list of packages, one per side, which is exactly the drift this repository
had already suffered twice. So the lists went into `requirements.txt`, with a
`requirements-windows.txt` that is `-r requirements.txt` plus the one package only Windows needs.
**The equivalent there is a single list of module names** for `Install-Module` — the sibling has no
`requirements.txt` idiom, but it has the same problem the moment it grows a Windows-side install, and
one array in one file solves it the same way.

**Two things learned doing it, both of which transfer:**

1. **Nothing after the containers start may abort the script.** The last line of `01_setup.ps1` is the
   `wsl` shell that keeps the containers alive; a `throw` above it skips that line, WSL2 idles out, and
   twenty minutes of container startup is gone. This happened on the first run. The Windows check now
   remembers its failure, lets the shell open, and throws after it returns.
2. **Wait for the port forwarding before checking connections from Windows.** `127.0.0.1:1521` is
   docker's published port inside WSL2 and a `wslrelay` listener on Windows, and the relay does not
   publish every port at the same moment. On the first clean install, four forwards were up and 1521
   was not — which failed the check while Oracle was running and answering inside WSL2. The error names
   Oracle and means the network.

---

## 13. The docker daemon is not waited for either

**Where:** `04_docker_compose.sh` and `start_containers.ps1`. Extends finding 4.

**What:** finding 4 is about waiting for the *databases*. This is one layer below it: nothing waits for
the *daemon*. `02_wsl2_setup.sh` starts docker, but `01_setup.ps1` runs `wsl --shutdown` immediately
afterwards, and `start_containers.ps1` runs after a reboot. In both cases docker comes back only
because systemd starts it, and `docker compose up` runs seconds after WSL2 boots.

**Effect:** intermittent, and it looks like a compose problem rather than a timing one.

**Second half of this, and the more useful half:** when a wait does fail, it says nothing. The probes
have to discard stderr — for most of the wait, "that user does not exist yet" is the correct answer —
so the give-up path prints one line with no cause. And it keeps probing for the full timeout even when
the container has already exited, so a container killed by its `mem_limit` is indistinguishable from a
slow one. Fifteen minutes of that, in front of an audience, then one line.

**Fix:** `service docker start` and a `docker info` poll before `docker compose up`; check
`docker compose ps --status running` on each round of the wait and stop early if the container is gone;
print `docker compose logs --tail 50` for that service on the failure path.

**Here:** fixed, all three. `wait_for` also takes the compose service name rather than a display name
now, so the failure message names what you would type next.
