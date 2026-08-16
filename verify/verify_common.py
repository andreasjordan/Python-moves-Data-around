"""The helpers every verify script uses, in one module so that six copies cannot drift apart.

This is the one shared file in verify/ and it should stay the only one.

None of it follows the lib/ function contract. That contract is for lib/, and these are helpers of a
runnable script - no enable_exception, and print() straight to the console, because the output of a
verify run is meant to be read by a person.
"""

import sys

# Module-level state rather than a class, to stay in the style of the rest of the repository - see
# "No type hints, no dataclasses, no classes" in AGENTS.md. One verify script is one process, so
# there is never a second run to keep separate.
_state = {"name": None, "passed": 0, "failed": 0, "writer": None}


def start_verify(name, report_path=None):
    _state["name"] = name
    _state["passed"] = 0
    _state["failed"] = 0

    # A report file is optional. It exists because a caller that redirects stdout sees nothing until
    # the process exits, and the StackExchange and Geodata runs take minutes. buffering=1 is the
    # whole point.
    if report_path:
        # noqa on SIM115: the writer has to outlive this function - complete_verify() closes
        # it - so there is no "with" block to put it in.
        _state["writer"] = open(report_path, "w", encoding="utf-8", buffering=1)  # noqa: SIM115

    line("")
    line(f"=== verify: {name} ===")
    line("")


def line(text):
    print(text, flush=True)
    if _state["writer"]:
        _state["writer"].write(text + "\n")


def fact(name, ok, detail=""):
    """One thing that is either true of the running system or is not.

    The detail is not decoration: it is what tells you whether a PASS passed for the right reason,
    so pass the number that was compared rather than the word "ok".
    """
    if ok:
        _state["passed"] += 1
    else:
        _state["failed"] += 1

    line(f"{'PASS' if ok else 'FAIL'}  {name}{'  -- ' + str(detail) if detail else ''}")


def complete_verify():
    line("")
    line(f"=== {_state['name']}: {_state['passed']} passed, {_state['failed']} failed ===")

    if _state["writer"]:
        _state["writer"].close()
        _state["writer"] = None

    # The exit code is what lets invoke_verify.py report a total without parsing this output
    sys.exit(1 if _state["failed"] else 0)


def add_repository_paths():
    """Put lib/ and demo/ on sys.path, resolved from this file rather than from the working directory.

    The notebooks do `sys.path.append(str(Path("../lib").resolve()))`, which only works because
    Jupyter sets the working directory to demo/. A verify script may be started from anywhere, so it
    resolves the paths from __file__ instead. That is the one deliberate difference from the
    notebooks' loading model.
    """
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent
    for folder in ("lib", "demo"):
        path = str(root / folder)
        if path not in sys.path:
            sys.path.append(path)
    return root
