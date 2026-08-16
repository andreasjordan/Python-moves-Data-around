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

Nothing.
