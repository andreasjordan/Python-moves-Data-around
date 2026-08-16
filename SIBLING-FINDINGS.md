# SIBLING-FINDINGS.md

The cross-repository work queue between this repository and
[PowerShell moves Data around](https://github.com/andreasjordan/PowerShell-moves-Data-around).

An entry goes here when something is found on one side that has to be fixed on the other and that side
cannot be reached. Say plainly which direction the entry points — the file is read from both sides, and
`docker/` is shared verbatim, so a finding in it usually points both ways.

**If both repositories are open** — a VS Code workspace holding the two of them, so the other one is a
working directory and not just a path — fix it in place instead and commit per repository. This file is
then the queue for what is deliberately deferred, not a way of routing work across a wall.

For the design decisions of the port itself, see `DIFFERENCES.md`.

## Open

### `get_ora_data_reader` is missing the CLOB guard its counterpart has

**Direction: this repository.** Found while porting `Read-OraQuery`, and deliberately deferred rather
than fixed, because it is outside what that task was asked to change.

`Get-OraDataReader.ps1` declares a bind parameter longer than 4000 characters as a `CLOB`, the same way
`Invoke-OraQuery` does, or Oracle answers `ORA-01461: can bind a LONG value only for insert into a LONG
column`. On this side `invoke_ora_query` has that guard and the new `read_ora_query` has it, but
`get_ora_data_reader` does not — so a reader whose `parameter_values` carries a long string fails where
the other two work.

The fix is the same eight lines the other two carry: a `setinputsizes(**{name: oracledb.DB_TYPE_CLOB})`
for the parameters over 4000 characters, before `cursor.execute`. Nothing calls it that way today — the
PhotoService scenario passes an id — so this is latent rather than broken in a demo.

Worth deciding at the same time whether the three copies of that guard should stay three copies. They
are inline in the sibling too, which is the argument for leaving them alone.
